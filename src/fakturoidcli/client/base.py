"""HTTP client for the Fakturoid REST API v3.

One dispatch point carries the mandatory headers, refetches the access token
once on 401, maps every non-2xx onto the typed exception hierarchy, and honors
``--dry-run`` by describing the request instead of sending it.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import ProfileConfig
from ..constants import (
    API_BASE_URL,
    DEFAULT_PDF_INTERVAL_SECONDS,
    HTTP_TIMEOUT_SECONDS,
    PAGE_SIZE,
)
from ..errors import (
    AssetNotReadyError,
    ConfigError,
    FakturoidError,
    NetworkError,
    UsageError,
    api_error_for,
)
from ..output import output_json, write_download
from .auth import TokenProvider

__all__ = ["FakturoidClient"]

logger = logging.getLogger(__name__)

REDACTED = "Bearer <redacted>"


class FakturoidClient:
    """Sends requests to one Fakturoid account with one set of credentials."""

    def __init__(
        self,
        profile: ProfileConfig,
        *,
        slug: str | None = None,
        dry_run: bool = False,
        output_dir: Path | None = None,
        default_params: dict[str, Any] | None = None,
        timeout: float = HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self.profile = profile
        self.slug = slug
        self.dry_run = dry_run
        self.output_dir = output_dir
        # Query parameters from the global -f option, added to every request.
        self.default_params = dict(default_params or {})
        self.timeout = timeout
        self.request_count = 0
        self._tokens = TokenProvider(profile, timeout=timeout)
        self._http_client: httpx.Client | None = None

    # ---------------------------------------------------------------- paths

    def require_slug(self) -> str:
        """Return the account slug, or explain how to supply one.

        Raises:
            ConfigError: If no slug was given and the profile declares none.
        """
        if not self.slug:
            raise ConfigError(
                "No account slug. Pass --slug, set FAKTUROID_SLUG, or add default_slug to the profile. "
                "Run 'fakturoid api GET /user.json' to list the accounts these credentials can reach."
            )
        return self.slug

    def expand_path(self, path: str) -> str:
        """Turn a CLI path into an absolute API URL.

        A path starting with ``/`` is account-independent and is used verbatim,
        which is how ``/user.json`` is reached. Anything else is treated as
        account-relative and gets ``/accounts/<slug>/`` prepended. A full
        ``https://app.fakturoid.cz/api/v3/...`` URL passes through unchanged.

        Args:
            path: The path as typed on the command line.

        Returns:
            An absolute URL.
        """
        candidate = path.strip()

        if candidate.startswith(f"{API_BASE_URL}/"):
            return self._substitute_slug(candidate)
        if candidate.startswith(("http://", "https://")):
            raise UsageError(f"Only {API_BASE_URL} URLs are accepted, got: {candidate}")

        if candidate.startswith("/api/v3/"):
            candidate = candidate[len("/api/v3") :]

        if candidate.startswith("/"):
            return self._substitute_slug(f"{API_BASE_URL}{candidate}")

        slug = self.require_slug()
        return self._substitute_slug(f"{API_BASE_URL}/accounts/{slug}/{candidate.lstrip('/')}")

    def _substitute_slug(self, url: str) -> str:
        """Replace the ``:slug`` and ``{slug}`` placeholders, following glab."""
        if ":slug" not in url and "{slug}" not in url:
            return url
        slug = self.require_slug()
        return url.replace(":slug", slug).replace("{slug}", slug)

    def build_url(self, path: str, params: dict[str, Any] | None = None) -> httpx.URL:
        """Build the full URL, merging the global -f fields with the call's own."""
        url = httpx.URL(self.expand_path(path))
        merged = {**self.default_params, **{k: v for k, v in (params or {}).items() if v is not None}}
        if merged:
            url = url.copy_merge_params(merged)
        return url

    # -------------------------------------------------------------- headers

    def base_headers(self) -> dict[str, str]:
        """The headers every request carries.

        A missing User-Agent is answered with 400, and a missing Accept makes
        the token endpoint answer 415.
        """
        return {
            "User-Agent": self._tokens.user_agent,
            "Accept": "application/json",
        }

    def _http(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.Client(headers=self.base_headers(), timeout=self.timeout)
        return self._http_client

    # ------------------------------------------------------------ requests

    def describe_request(self, method: str, url: httpx.URL, json_body: Any | None) -> dict[str, Any]:
        """Describe the request a dry run would have sent.

        No token is fetched, so a dry run reaches the network zero times.
        """
        headers = {**self.base_headers(), "Authorization": REDACTED}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        return {
            "method": method,
            "url": str(url),
            "headers": headers,
            "body": json_body,
        }

    def _dispatch(self, method: str, url: httpx.URL, json_body: Any | None, token: str) -> httpx.Response:
        """Send one request, translating transport failures."""
        self.request_count += 1
        logger.debug("%s %s", method, url)
        try:
            return self._http().request(method, url, json=json_body, headers={"Authorization": f"Bearer {token}"})
        except httpx.RequestError as e:
            raise NetworkError(f"{method} {url} failed: {e}") from e

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> httpx.Response | None:
        """Send a request and return the successful response.

        Returns None in dry-run mode, after printing the request descriptor. A
        caller that reaches the network must therefore stop on None.

        Args:
            method: HTTP method.
            path: Account-relative path, absolute path, or full API URL.
            params: Query parameters, merged with the global -f fields.
            json_body: The request body, sent unfiltered and unreshaped.

        Returns:
            The 2xx response, or None in dry-run mode.

        Raises:
            ApiError: On any non-2xx answer.
            NetworkError: If nothing reached the server.
        """
        verb = method.upper()
        url = self.build_url(path, params)

        if self.dry_run:
            output_json(self.describe_request(verb, url, json_body))
            return None

        response = self._dispatch(verb, url, json_body, self._tokens.get())
        if response.status_code == 401:
            # A cached token can be revoked before its stated expiry, so one
            # refetch and one retry separate a stale token from bad credentials.
            response = self._dispatch(verb, url, json_body, self._tokens.refresh())

        if not response.is_success:
            raise api_error_for(response.status_code, response.text, dict(response.headers))

        return response

    # ------------------------------------------------------------- bodies

    @staticmethod
    def is_json(response: httpx.Response) -> bool:
        """Report whether the response carries a JSON body."""
        media_type: str = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        return media_type.endswith("json")

    @staticmethod
    def parse_json(response: httpx.Response) -> Any:
        """Parse a response body, mapping an empty 204 body onto ``{}``."""
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as e:
            content_type = response.headers.get("content-type", "unknown")
            raise FakturoidError(f"Expected a JSON response, got {content_type}") from e

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> Any | None:
        """Send a request and return the parsed JSON body, or None in dry-run mode."""
        response = self.request(method, path, params=params, json_body=json_body)
        if response is None:
            return None
        return self.parse_json(response)

    # --------------------------------------------------------- pagination

    def paginate(self, path: str, *, params: dict[str, Any] | None = None) -> list[Any] | None:
        """Walk every page and return one merged array, or None in dry-run mode.

        Pages are requested serially and the walk stops on the first short page.
        A failure on any page fails the whole command: a truncated array that
        looks complete is worse than an error.
        """
        merged: list[Any] = []
        page = 1
        while True:
            response = self.request("GET", path, params={**(params or {}), "page": page})
            if response is None:
                return None

            data = self.parse_json(response)
            if not isinstance(data, list):
                raise UsageError(f"--all needs an endpoint that returns an array, {path} returned an object")

            merged.extend(data)
            if len(data) < PAGE_SIZE:
                return merged
            page += 1

    # ----------------------------------------------------------- downloads

    def write_response_to_file(self, response: httpx.Response, *, resource: str, identifier: str) -> dict[str, Any]:
        """Write a non-JSON response body to disk and return its descriptor."""
        return write_download(
            response.content,
            resource=resource,
            identifier=identifier,
            content_type=response.headers.get("content-type", ""),
            output_dir=self.output_dir,
        )

    def download(
        self,
        path: str,
        *,
        resource: str,
        identifier: str,
        params: dict[str, Any] | None = None,
        wait_seconds: float = 0.0,
        interval_seconds: float = DEFAULT_PDF_INTERVAL_SECONDS,
    ) -> dict[str, Any] | None:
        """Fetch a binary document, write it to disk, and describe where it landed.

        The bytes never reach stdout. A 204 means the document is not generated
        yet, so the request repeats until ``wait_seconds`` runs out.

        Args:
            path: The download path.
            resource: The resource name used in the filename.
            identifier: The document identifier used in the filename.
            params: Query parameters.
            wait_seconds: How long to keep retrying a 204. Zero fails at once.
            interval_seconds: Delay between retries.

        Returns:
            The file descriptor, or None in dry-run mode.

        Raises:
            AssetNotReadyError: If the answer is still 204 when the wait runs out.
        """
        deadline = time.monotonic() + wait_seconds
        while True:
            response = self.request("GET", path, params=params)
            if response is None:
                return None

            if response.status_code != 204:
                return self.write_response_to_file(response, resource=resource, identifier=identifier)

            if time.monotonic() + interval_seconds > deadline:
                raise AssetNotReadyError(f"{path} is still not generated after {wait_seconds:g}s")
            time.sleep(interval_seconds)

    def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None
