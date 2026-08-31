"""Pure transforms over Fakturoid documents. Nothing here reaches the network."""

from __future__ import annotations

from typing import Any

__all__ = ["GENERATOR_CARRIED_FIELDS", "GENERATOR_LINE_FIELDS", "generator_to_invoice_payload"]

# Order matters: it is the key order of the printed payload, which a person edits by hand.
GENERATOR_CARRIED_FIELDS = (
    "subject_id",
    "lines",
    "due",
    "payment_method",
    "currency",
    "language",
    "note",
    "footer_note",
    "number_format_id",
    "bank_account_id",
    "tags",
    "order_number",
)

GENERATOR_LINE_FIELDS = ("name", "quantity", "unit_name", "unit_price", "vat_rate")


def _carry_line(line: Any) -> Any:
    """Reduce one generator line to the fields an invoice line accepts.

    A generator line ``id`` points at a row of the template, not of the new
    document. The price and VAT totals are the server's own arithmetic, and
    sending them back fights it. Both are dropped, along with the inventory
    block and every ``native_*`` field.
    """
    if not isinstance(line, dict):
        return line
    return {key: line[key] for key in GENERATOR_LINE_FIELDS if line.get(key) is not None}


def generator_to_invoice_payload(generator: dict[str, Any]) -> dict[str, Any]:
    """Map a generator onto an invoice create payload.

    A null value is omitted rather than sent as an explicit null, because an
    explicit null overrides an account default the server would otherwise apply.

    Args:
        generator: The body of ``GET /generators/{id}.json``.

    Returns:
        A payload for ``POST /invoices.json``, ready to edit for the month.
    """
    payload: dict[str, Any] = {}
    for key in GENERATOR_CARRIED_FIELDS:
        value = generator.get(key)
        if value is None:
            continue
        payload[key] = [_carry_line(line) for line in value] if key == "lines" else value

    # A generator says "proforma" with a boolean, an invoice says it with document_type.
    # The false case stays absent, because the server already defaults to a regular invoice.
    if generator.get("proforma"):
        payload["document_type"] = "proforma"

    return payload
