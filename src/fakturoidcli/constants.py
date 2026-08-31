"""Shared constants used across the application."""

__all__ = [
    "API_BASE_URL",
    "TOKEN_PATH",
    "HTTP_TIMEOUT_SECONDS",
    "TOKEN_EXPIRY_MARGIN_SECONDS",
    "PAGE_SIZE",
    "USER_AGENT_TEMPLATE",
    "DEFAULT_OUTPUT_DIR",
    "PRIVATE_DIR_MODE",
    "PRIVATE_FILE_MODE",
    "DEFAULT_PDF_WAIT_SECONDS",
    "DEFAULT_PDF_INTERVAL_SECONDS",
    "RATE_LIMIT_HEADERS",
]

API_BASE_URL = "https://app.fakturoid.cz/api/v3"

# OAuth2 client_credentials token endpoint, relative to the API base URL.
TOKEN_PATH = "/oauth/token"

HTTP_TIMEOUT_SECONDS = 60.0

# The API issues tokens with expires_in = 7200. Treating a token as expired a
# minute early absorbs clock skew between this machine and Fakturoid.
TOKEN_EXPIRY_MARGIN_SECONDS = 60

# Server-fixed page size. A page shorter than this is the last page.
PAGE_SIZE = 40

# A request without a User-Agent is answered with 400, so the contact is mandatory.
USER_AGENT_TEMPLATE = "fakturoid-cli ({contact})"

DEFAULT_OUTPUT_DIR = "/tmp/fakturoid"

# Downloaded documents are invoices and expense attachments, and /tmp is world
# readable on a shared machine.
PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600

DEFAULT_PDF_WAIT_SECONDS = 15.0
DEFAULT_PDF_INTERVAL_SECONDS = 1.5

RATE_LIMIT_HEADERS = ("X-RateLimit-Policy", "X-RateLimit")
