"""Raw Fakturoid API passthrough, modeled on ``glab api``.

It reaches any endpoint that has no dedicated command, and any endpoint
Fakturoid adds later. The request body is sent exactly as it arrives.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer

from ..context import get_context
from ..errors import UsageError
from ..output import output_json, stderr_line
from ..payload import read_json_body

__all__ = ["api_command"]

_ALLOWED_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD")


def _resolve_call(
    method_or_path: str,
    path: str | None,
    method_option: str | None,
    has_body: bool,
) -> tuple[str, str]:
    """Work out the method and the path from the positional and option forms.

    Raises:
        UsageError: If the method is given twice or is not supported.
    """
    if path is None:
        target = method_or_path
        verb = method_option or ("POST" if has_body else "GET")
    else:
        if method_option is not None:
            raise UsageError(f"Method given twice: '{method_or_path}' and -X {method_option}")
        target = path
        verb = method_or_path

    verb = verb.upper()
    if verb not in _ALLOWED_METHODS:
        raise UsageError(f"Unsupported method '{verb}'. Use one of: {', '.join(_ALLOWED_METHODS)}.")
    return verb, target


def _download_identifier(url_path: str) -> str:
    """Name a downloaded file after the last two path segments of its endpoint."""
    segments = [segment for segment in url_path.split("/") if segment]
    tail = segments[-2:] if segments else ["download"]
    return "-".join(tail).rsplit(".", 1)[0]


def api_command(
    method_or_path: Annotated[
        str,
        typer.Argument(metavar="METHOD|PATH", help="HTTP method, or the path when the method is omitted."),
    ],
    path: Annotated[
        str | None,
        typer.Argument(metavar="[PATH]", help="API path. Account-relative unless it starts with /."),
    ] = None,
    method_option: Annotated[
        str | None,
        typer.Option("--method", "-X", help="HTTP method, when it is not given positionally."),
    ] = None,
    payload: Annotated[
        str | None,
        typer.Option("--payload", help="Request body as a JSON string. Beats --input and stdin."),
    ] = None,
    input_ref: Annotated[
        str | None,
        typer.Option("--input", help="Read the request body from FILE, or - for stdin."),
    ] = None,
    paginate: Annotated[
        bool,
        typer.Option("--paginate", help="Walk every page and print one merged array. GET only."),
    ] = False,
    include: Annotated[
        bool,
        typer.Option("--include", help="Print the response status and headers to stderr."),
    ] = False,
) -> None:
    """Send a raw request to the Fakturoid API and print the response.

    Paths are account-relative, so 'invoices.json' becomes
    /accounts/<slug>/invoices.json. A path starting with / is used verbatim,
    which is how /user.json is reached. The body is never filtered or reshaped,
    and no schema is applied.

    Examples:
        fakturoid api GET /user.json
        fakturoid api GET invoices.json -f status=open
        fakturoid api GET invoices.json --paginate
        fakturoid api PATCH generators/12345.json --payload '{"note":"x"}'
        cat body.json | fakturoid api POST invoices.json --input -
    """
    ctx = get_context()

    body = read_json_body(payload, input_ref)
    verb, target = _resolve_call(method_or_path, path, method_option, body is not None)

    client = ctx.client
    walk_pages = paginate or ctx.all_pages

    if walk_pages:
        if verb != "GET":
            raise UsageError("--paginate is only valid for GET")
        if ctx.page is not None:
            raise UsageError("--page and --paginate are mutually exclusive")
        merged = client.paginate(target)
        if merged is not None:
            output_json(merged)
        return

    response = client.request(verb, target, params=ctx.pagination_params(), json_body=body)
    if response is None:
        return

    if include:
        stderr_line(
            json.dumps(
                {"status": response.status_code, "headers": dict(response.headers)},
                indent=2,
                ensure_ascii=False,
            )
        )

    if client.is_json(response) or not response.content:
        output_json(client.parse_json(response))
        return

    output_json(
        client.write_response_to_file(response, resource="api", identifier=_download_identifier(response.url.path))
    )
