"""Exception hierarchy and the exit code each failure maps to."""

from __future__ import annotations

from enum import IntEnum

__all__ = [
    "ExitCode",
    "FakturoidError",
    "UsageError",
    "ConfigError",
    "NetworkError",
    "AssetNotReadyError",
    "ApiError",
    "AuthenticationError",
    "NotFoundError",
    "ValidationError",
    "PaymentRequiredError",
    "RateLimitError",
    "ServerError",
    "ClientError",
    "api_error_for",
]


class ExitCode(IntEnum):
    """Process exit codes. A caller in a loop branches on these."""

    SUCCESS = 0
    INTERNAL = 1
    USAGE = 2
    CONFIG = 3
    AUTH = 4
    NOT_FOUND = 5
    VALIDATION = 6
    CLIENT = 7
    RATE_LIMITED = 8
    SERVER = 9
    NETWORK = 10
    ASSET_NOT_READY = 11
    PAYMENT_REQUIRED = 12


class FakturoidError(Exception):
    """Base class for every failure this CLI reports with a dedicated exit code."""

    exit_code = ExitCode.INTERNAL


class UsageError(FakturoidError):
    """The command line itself is wrong, so nothing was sent."""

    exit_code = ExitCode.USAGE


class ConfigError(FakturoidError):
    """Credentials or the account slug could not be resolved."""

    exit_code = ExitCode.CONFIG


class NetworkError(FakturoidError):
    """Nothing reached the server: DNS, connection, TLS, or timeout."""

    exit_code = ExitCode.NETWORK


class AssetNotReadyError(FakturoidError):
    """The server answered 204 for a file that has not been generated yet."""

    exit_code = ExitCode.ASSET_NOT_READY


class ApiError(FakturoidError):
    """A non-2xx answer. The server's own body is carried through untouched."""

    exit_code = ExitCode.CLIENT

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        body_text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body_text = body_text
        self.headers = headers or {}


class AuthenticationError(ApiError):
    """401 that survived one token refetch, or 403."""

    exit_code = ExitCode.AUTH


class NotFoundError(ApiError):
    """404."""

    exit_code = ExitCode.NOT_FOUND


class ValidationError(ApiError):
    """422, whose body names the offending fields."""

    exit_code = ExitCode.VALIDATION


class PaymentRequiredError(ApiError):
    """402. The Fakturoid account is blocked for non-payment, not the request."""

    exit_code = ExitCode.PAYMENT_REQUIRED


class RateLimitError(ApiError):
    """429. A caller in a loop needs to back off rather than give up."""

    exit_code = ExitCode.RATE_LIMITED


class ServerError(ApiError):
    """5xx, including the 503 the search endpoints answer when they are busy."""

    exit_code = ExitCode.SERVER


class ClientError(ApiError):
    """Any other 4xx."""

    exit_code = ExitCode.CLIENT


_STATUS_MAP: dict[int, type[ApiError]] = {
    401: AuthenticationError,
    402: PaymentRequiredError,
    403: AuthenticationError,
    404: NotFoundError,
    422: ValidationError,
    429: RateLimitError,
}


def api_error_for(status_code: int, body_text: str = "", headers: dict[str, str] | None = None) -> ApiError:
    """Build the exception that matches an HTTP status code.

    Args:
        status_code: The response status code.
        body_text: The response body, kept verbatim for stderr.
        headers: The response headers, used to echo rate-limit state.

    Returns:
        The exception to raise, already carrying the body and the exit code.
    """
    error_class = _STATUS_MAP.get(status_code)
    if error_class is None:
        error_class = ServerError if status_code >= 500 else ClientError
    return error_class(
        f"HTTP {status_code}",
        status_code=status_code,
        body_text=body_text,
        headers=dict(headers or {}),
    )
