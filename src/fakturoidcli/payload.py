"""Reading a request body from the command line or from a pipe.

Precedence, applied by every command that sends a body:

1. ``--payload`` wins. stdin is not read at all, even when it is a pipe.
2. Otherwise ``--input FILE`` is read, and ``--input -`` reads stdin.
3. Otherwise, if stdin is not a terminal, the whole of stdin is read.
4. Otherwise there is no body.

Invalid JSON from any source is a usage error, so nothing is sent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .errors import UsageError

__all__ = ["read_json_body", "require_json_body"]


def read_json_body(payload: str | None, input_ref: str | None = None) -> Any | None:
    """Read the request body, or return None when no source supplies one.

    An empty source means no body at all, so a command in a pipeline does not
    send ``null``.

    Args:
        payload: The ``--payload`` value.
        input_ref: The ``--input`` value: a file path, or ``-`` for stdin.

    Returns:
        The parsed body, or None.

    Raises:
        UsageError: If the body is not valid JSON.
    """
    if payload is not None:
        raw = payload
    elif input_ref is not None:
        raw = sys.stdin.read() if input_ref == "-" else Path(input_ref).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        return None

    if not raw.strip():
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise UsageError(f"Invalid JSON request body: {e}") from None


def require_json_body(payload: str | None, input_ref: str | None = None) -> Any:
    """Read a request body that the command cannot do without.

    Raises:
        UsageError: If no source supplied a body, or the body is not valid JSON.
    """
    body = read_json_body(payload, input_ref)
    if body is None:
        raise UsageError("No request body. Pass --payload '<json>' or pipe the JSON on stdin.")
    return body
