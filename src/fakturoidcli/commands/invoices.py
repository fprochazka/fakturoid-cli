"""Invoice commands.

v1 has no way to send a document to a customer: neither ``fire`` nor ``message``
is implemented, so no command here can e-mail an invoice or change its status.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ..constants import DEFAULT_PDF_INTERVAL_SECONDS, DEFAULT_PDF_WAIT_SECONDS
from ..context import get_context
from .common import emit, run_get, run_list, run_write

__all__ = ["app"]

app = typer.Typer(name="invoices", help="Invoice operations.", no_args_is_help=True, rich_markup_mode=None)


@app.command("list")
def invoices_list(
    since: Annotated[
        str | None,
        typer.Option("--since", help="Invoices created after this ISO 8601 date or datetime."),
    ] = None,
    until: Annotated[
        str | None,
        typer.Option("--until", help="Invoices created before this ISO 8601 date or datetime."),
    ] = None,
    updated_since: Annotated[
        str | None,
        typer.Option("--updated-since", help="Invoices created or updated after this ISO 8601 value."),
    ] = None,
    updated_until: Annotated[
        str | None,
        typer.Option("--updated-until", help="Invoices created or updated before this ISO 8601 value."),
    ] = None,
    subject_id: Annotated[
        int | None,
        typer.Option("--subject-id", help="Filter by customer id."),
    ] = None,
    custom_id: Annotated[
        str | None,
        typer.Option("--custom-id", help="Filter by your own identifier."),
    ] = None,
    number: Annotated[
        str | None,
        typer.Option("--number", help="Filter by document number."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            help="Filter by status: open, sent, overdue, paid, cancelled, uncollectible.",
        ),
    ] = None,
    document_type: Annotated[
        str | None,
        typer.Option(
            "--document-type",
            help="Filter by type: regular, proforma, invoice, correction, tax_document.",
        ),
    ] = None,
) -> None:
    """List invoices.

    GET /accounts/{slug}/invoices.json. The status and type values are sent as
    typed, so a value Fakturoid adds later works before this help text knows it.
    """
    run_list(
        "invoices.json",
        {
            "since": since,
            "until": until,
            "updated_since": updated_since,
            "updated_until": updated_until,
            "subject_id": subject_id,
            "custom_id": custom_id,
            "number": number,
            "status": status,
            "document_type": document_type,
        },
    )


@app.command("show")
def invoices_show(
    invoice_id: Annotated[int, typer.Argument(metavar="ID", help="Invoice id.")],
) -> None:
    """Show one invoice, including its public_html_url.

    GET /accounts/{slug}/invoices/{id}.json.
    """
    run_get(f"invoices/{invoice_id}.json")


@app.command("create")
def invoices_create(
    payload: Annotated[
        str | None,
        typer.Option("--payload", help="Request body as a JSON string. Beats stdin."),
    ] = None,
) -> None:
    """Create an invoice. This consumes a document number permanently.

    POST /accounts/{slug}/invoices.json. The body comes from --payload, or from
    stdin when --payload is absent. It is checked against the invoice schema and
    then sent unchanged, extra fields included. Use --dry-run to see the request
    without sending it.
    """
    run_write("POST", "invoices.json", payload=payload, resource="invoices", action="create")


@app.command("update")
def invoices_update(
    invoice_id: Annotated[int, typer.Argument(metavar="ID", help="Invoice id.")],
    payload: Annotated[
        str | None,
        typer.Option("--payload", help="Request body as a JSON string. Beats stdin."),
    ] = None,
) -> None:
    """Update an invoice.

    PATCH /accounts/{slug}/invoices/{id}.json. A partial body is the point of the
    verb, so the schema requires no field at all.
    """
    run_write("PATCH", f"invoices/{invoice_id}.json", payload=payload, resource="invoices", action="update")


@app.command("pdf")
def invoices_pdf(
    invoice_id: Annotated[int, typer.Argument(metavar="ID", help="Invoice id.")],
    pdf_wait: Annotated[
        float,
        typer.Option("--pdf-wait", help="Seconds to keep retrying while the PDF is not generated."),
    ] = DEFAULT_PDF_WAIT_SECONDS,
    pdf_interval: Annotated[
        float,
        typer.Option("--pdf-interval", help="Seconds between retries."),
    ] = DEFAULT_PDF_INTERVAL_SECONDS,
) -> None:
    """Download an invoice PDF and print where it landed.

    GET /accounts/{slug}/invoices/{id}/download.pdf. The bytes never reach
    stdout. A 204 means the PDF is not generated yet, so the request repeats
    until --pdf-wait runs out and then fails with the asset-not-ready code.
    """
    ctx = get_context()
    emit(
        ctx.client.download(
            f"invoices/{invoice_id}/download.pdf",
            resource="invoice",
            identifier=str(invoice_id),
            wait_seconds=pdf_wait,
            interval_seconds=pdf_interval,
        )
    )
