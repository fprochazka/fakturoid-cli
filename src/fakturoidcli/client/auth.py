"""OAuth2 client_credentials flow with a disk-cached access token."""

from __future__ import annotations

import httpx

from ..cache import get_cached_token, store_token
from ..config import ProfileConfig
from ..constants import (
    API_BASE_URL,
    HTTP_TIMEOUT_SECONDS,
    TOKEN_PATH,
    USER_AGENT_TEMPLATE,
)
from ..errors import ApiError, AuthenticationError, NetworkError, api_error_for

__all__ = ["TokenProvider"]


class TokenProvider:
    """Supplies the bearer token for a profile, fetching one when needed."""

    def __init__(self, profile: ProfileConfig, timeout: float = HTTP_TIMEOUT_SECONDS) -> None:
        self.profile = profile
        self.timeout = timeout

    @property
    def user_agent(self) -> str:
        """The User-Agent every request must carry."""
        return USER_AGENT_TEMPLATE.format(contact=self.profile.user_agent_contact)

    def get(self) -> str:
        """Return a valid access token, from the cache when one is still fresh."""
        cached = get_cached_token(self.profile.name, self.profile.client_id)
        if cached:
            return cached
        return self.refresh()

    def refresh(self) -> str:
        """Fetch a new access token and cache it.

        Returns:
            The new access token.

        Raises:
            AuthenticationError: If Fakturoid rejects the client credentials.
            NetworkError: If nothing reached the server.
        """
        url = f"{API_BASE_URL}{TOKEN_PATH}"
        try:
            response = httpx.post(
                url,
                json={"grant_type": "client_credentials"},
                auth=(self.profile.client_id, self.profile.client_secret),
                headers={
                    # A missing Accept makes the token endpoint answer 415.
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": self.user_agent,
                },
                timeout=self.timeout,
            )
        except httpx.RequestError as e:
            raise NetworkError(f"Could not reach {url}: {e}") from e

        if not response.is_success:
            raise self._token_error(response)

        try:
            payload = response.json()
        except ValueError as e:
            raise AuthenticationError(
                "The token endpoint did not answer with JSON",
                status_code=response.status_code,
                body_text=response.text,
                headers=dict(response.headers),
            ) from e

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AuthenticationError(
                "The token endpoint returned no access_token",
                status_code=response.status_code,
                body_text=response.text,
                headers=dict(response.headers),
            )

        store_token(
            self.profile.name,
            self.profile.client_id,
            access_token,
            int(payload.get("expires_in", 0)),
        )
        return access_token

    def _token_error(self, response: httpx.Response) -> ApiError:
        """Map a token-endpoint failure.

        A 400 here means the credentials themselves are unusable, so it reports
        as an authentication failure rather than as a bad request.
        """
        if response.status_code == 400:
            return AuthenticationError(
                "Fakturoid rejected the client credentials",
                status_code=400,
                body_text=response.text,
                headers=dict(response.headers),
            )
        return api_error_for(response.status_code, response.text, dict(response.headers))
