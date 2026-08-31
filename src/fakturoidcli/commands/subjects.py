"""Subject commands. A subject is a customer or a supplier."""

from __future__ import annotations

from typing import Annotated

import typer

from .common import run_get, run_list

__all__ = ["app"]

app = typer.Typer(
    name="subjects",
    help="Customer and supplier operations.",
    no_args_is_help=True,
    rich_markup_mode=None,
)


@app.command("list")
def subjects_list(
    since: Annotated[
        str | None,
        typer.Option("--since", help="Subjects created after this ISO 8601 date or datetime."),
    ] = None,
    until: Annotated[
        str | None,
        typer.Option("--until", help="Subjects created before this ISO 8601 date or datetime."),
    ] = None,
    updated_since: Annotated[
        str | None,
        typer.Option("--updated-since", help="Subjects created or updated after this ISO 8601 value."),
    ] = None,
    updated_until: Annotated[
        str | None,
        typer.Option("--updated-until", help="Subjects created or updated before this ISO 8601 value."),
    ] = None,
    custom_id: Annotated[
        str | None,
        typer.Option("--custom-id", help="Filter by your own identifier."),
    ] = None,
) -> None:
    """List subjects.

    GET /accounts/{slug}/subjects.json. Date values are passed through as typed,
    so a non-ISO value comes back as the server's own 400.
    """
    run_list(
        "subjects.json",
        {
            "since": since,
            "until": until,
            "updated_since": updated_since,
            "updated_until": updated_until,
            "custom_id": custom_id,
        },
    )


@app.command("search")
def subjects_search(
    query: Annotated[
        str,
        typer.Option("--query", help="Text to look for. Required."),
    ],
) -> None:
    """Search subjects by name, address, registration number or private note.

    GET /accounts/{slug}/subjects/search.json. The server looks at name,
    full_name, email, email_copy, registration_no, vat_no and private_note.
    """
    run_list("subjects/search.json", {"query": query})


@app.command("show")
def subjects_show(
    subject_id: Annotated[int, typer.Argument(metavar="ID", help="Subject id.")],
) -> None:
    """Show one subject, including the e-mail address invoices go to.

    GET /accounts/{slug}/subjects/{id}.json.
    """
    run_get(f"subjects/{subject_id}.json")
