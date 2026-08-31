"""Output helpers. stdout carries JSON and nothing else.

Every human-facing line goes to stderr through plain ``print``. Rich wraps text
at 80 columns when the stream is not a TTY, which puts literal newlines inside
JSON string values and makes the output unparseable.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_OUTPUT_DIR,
    PRIVATE_DIR_MODE,
    PRIVATE_FILE_MODE,
    RATE_LIMIT_HEADERS,
)
from .errors import ApiError, FakturoidError, RateLimitError

__all__ = [
    "output_json",
    "stderr_line",
    "warn",
    "output_error",
    "output_error_body",
    "report_error",
    "download_filename",
    "write_download",
]

# A filename segment may only carry characters that survive a shell round trip.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def output_json(data: Any) -> None:
    """Print a JSON document to stdout.

    Uses plain print() so Rich never wraps long strings and breaks the JSON.
    ``ensure_ascii=False`` keeps Czech text readable.
    """
    print(json.dumps(data, indent=2, ensure_ascii=False))


def stderr_line(message: str) -> None:
    """Write one line of human-facing text to stderr."""
    print(message, file=sys.stderr)


def warn(message: str) -> None:
    """Report a condition that does not stop the command."""
    stderr_line(f"warning: {message}")


def output_error(message: str) -> None:
    """Report a failure."""
    stderr_line(f"error: {message}")


def output_error_body(body_text: str) -> None:
    """Write the server's own response body to stderr, unmodified and unwrapped."""
    text = body_text.rstrip("\n")
    if text:
        stderr_line(text)


def report_error(exc: FakturoidError) -> None:
    """Write a failure to stderr, leaving stdout empty."""
    if not isinstance(exc, ApiError):
        output_error(str(exc))
        return

    output_error(f"HTTP {exc.status_code}")
    output_error_body(exc.body_text)

    if isinstance(exc, RateLimitError):
        for header in RATE_LIMIT_HEADERS:
            value = exc.headers.get(header)
            if value:
                stderr_line(f"{header}: {value}")


def _safe_segment(value: str) -> str:
    """Reduce an identifier to characters that are safe in a filename."""
    cleaned = _UNSAFE_FILENAME_CHARS.sub("-", value).strip("-")
    return cleaned or "unknown"


def _extension_for(content_type: str) -> str:
    """Map a Content-Type to a file extension, falling back to .bin."""
    media_type = content_type.split(";", 1)[0].strip().lower()
    if not media_type:
        return ".bin"
    return mimetypes.guess_extension(media_type) or ".bin"


def download_filename(
    resource: str,
    identifier: str,
    content_type: str,
    now: datetime | None = None,
) -> str:
    """Build the on-disk name for a downloaded document.

    Args:
        resource: The resource the file belongs to, for example ``invoice``.
        identifier: The document identifier, for example its number or id.
        content_type: The response Content-Type, which decides the extension.
        now: The timestamp to stamp into the name. Defaults to the local clock.

    Returns:
        A name of the form ``<resource>-<identifier>-<timestamp>.<ext>``.
    """
    stamp = (now or datetime.now()).strftime("%Y%m%dT%H%M%S")
    return f"{_safe_segment(resource)}-{_safe_segment(identifier)}-{stamp}{_extension_for(content_type)}"


def write_download(
    content: bytes,
    *,
    resource: str,
    identifier: str,
    content_type: str,
    output_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Write a non-JSON response to disk and describe where it landed.

    Args:
        content: The response bytes.
        resource: The resource the file belongs to.
        identifier: The document identifier.
        content_type: The response Content-Type.
        output_dir: The target directory. Defaults to ``/tmp/fakturoid``.

    Returns:
        The descriptor printed on stdout: ``path``, ``content_type``, ``bytes``.
    """
    directory = Path(output_dir) if output_dir is not None else Path(DEFAULT_OUTPUT_DIR)
    existed = directory.exists()
    directory.mkdir(parents=True, exist_ok=True)
    if not existed:
        # mkdir applies the umask, so the mode is set explicitly.
        directory.chmod(PRIVATE_DIR_MODE)

    path = directory / download_filename(resource, identifier, content_type)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_FILE_MODE)
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)

    return {
        "path": str(path),
        "content_type": content_type.split(";", 1)[0].strip(),
        "bytes": len(content),
    }
