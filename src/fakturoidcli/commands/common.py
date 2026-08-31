"""Shared plumbing for the resource commands.

Every dedicated command is still a passthrough: the global ``-f key=value``
fields are merged into the query string by the client, and a request body is
sent exactly as it arrived.
"""

from __future__ import annotations

from typing import Any

from ..context import get_context
from ..output import output_json
from ..payload import require_json_body
from ..validation import load_schema, validate_payload

__all__ = ["emit", "run_get", "run_list", "run_write"]


def emit(data: Any | None) -> None:
    """Print a response body, unless the request was only described.

    The client returns None for a dry run, having already printed the request
    descriptor, so a second document must not follow it on stdout.
    """
    if data is not None:
        output_json(data)


def run_get(path: str, params: dict[str, Any] | None = None) -> None:
    """Fetch one document and print it."""
    ctx = get_context()
    emit(ctx.client.request_json("GET", path, params=params))


def run_list(path: str, params: dict[str, Any] | None = None) -> None:
    """Fetch a collection and print it, honoring the global --page and --all."""
    ctx = get_context()
    query = dict(params or {})

    if ctx.all_pages:
        emit(ctx.client.paginate(path, params=query))
        return

    emit(ctx.client.request_json("GET", path, params={**query, **ctx.pagination_params()}))


def run_write(
    method: str,
    path: str,
    *,
    payload: str | None,
    resource: str,
    action: str,
) -> None:
    """Validate a request body against its schema, send it, and print the answer.

    Args:
        method: POST for a create, PATCH for an update.
        path: The account-relative endpoint path.
        payload: The ``--payload`` value. stdin supplies the body when it is None.
        resource: The schema file to check the body against.
        action: The action within that schema, ``create`` or ``update``.
    """
    body = require_json_body(payload)
    validate_payload(body, load_schema(resource, action))

    ctx = get_context()
    emit(ctx.client.request_json(method, path, json_body=body))
