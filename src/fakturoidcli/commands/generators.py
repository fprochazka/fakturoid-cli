"""Generator commands. A generator is an invoice template, not a schedule."""

from __future__ import annotations

from typing import Annotated

import typer

from ..context import get_context
from ..transforms import generator_to_invoice_payload
from .common import emit, run_get, run_list, run_write

__all__ = ["app"]

app = typer.Typer(name="generators", help="Invoice template operations.", no_args_is_help=True, rich_markup_mode=None)


@app.command("list")
def generators_list(
    since: Annotated[
        str | None,
        typer.Option("--since", help="Generators created after this ISO 8601 date or datetime."),
    ] = None,
    updated_since: Annotated[
        str | None,
        typer.Option("--updated-since", help="Generators created or updated after this ISO 8601 value."),
    ] = None,
    subject_id: Annotated[
        int | None,
        typer.Option("--subject-id", help="Filter by customer id."),
    ] = None,
) -> None:
    """List invoice templates.

    GET /accounts/{slug}/generators.json.
    """
    run_list("generators.json", {"since": since, "updated_since": updated_since, "subject_id": subject_id})


@app.command("show")
def generators_show(
    generator_id: Annotated[int, typer.Argument(metavar="ID", help="Generator id.")],
) -> None:
    """Show one invoice template.

    GET /accounts/{slug}/generators/{id}.json.
    """
    run_get(f"generators/{generator_id}.json")


@app.command("create")
def generators_create(
    payload: Annotated[
        str | None,
        typer.Option("--payload", help="Request body as a JSON string. Beats stdin."),
    ] = None,
) -> None:
    """Create an invoice template.

    POST /accounts/{slug}/generators.json. The body comes from --payload, or
    from stdin when --payload is absent. It is checked against the generator
    schema and then sent unchanged, extra fields included.
    """
    run_write("POST", "generators.json", payload=payload, resource="generators", action="create")


@app.command("update")
def generators_update(
    generator_id: Annotated[int, typer.Argument(metavar="ID", help="Generator id.")],
    payload: Annotated[
        str | None,
        typer.Option("--payload", help="Request body as a JSON string. Beats stdin."),
    ] = None,
) -> None:
    """Update an invoice template.

    PATCH /accounts/{slug}/generators/{id}.json. A partial body is the point of
    the verb, so the schema requires no field at all.
    """
    run_write(
        "PATCH",
        f"generators/{generator_id}.json",
        payload=payload,
        resource="generators",
        action="update",
    )


@app.command("payload")
def generators_payload(
    generator_id: Annotated[int, typer.Argument(metavar="ID", help="Generator id.")],
) -> None:
    """Print an invoice payload derived from a template. Writes nothing.

    GET /accounts/{slug}/generators/{id}.json, then a pure transform. This is a
    stdout filter: edit the result for the month and pipe it into
    'fakturoid invoices create'.

    A generator line id points at a row of the template, not of the new invoice,
    and the price totals are the server's own arithmetic. Both are dropped, and
    a null value is omitted rather than sent as an explicit null.
    """
    ctx = get_context()
    generator = ctx.client.request_json("GET", f"generators/{generator_id}.json")
    if generator is None:
        return
    emit(generator_to_invoice_payload(generator))
