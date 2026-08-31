"""The generator-to-invoice mapping. It is the one piece of Fakturoid knowledge
a person gets wrong by hand, so it is pinned here rather than rediscovered."""

from __future__ import annotations

from typing import Any

from fakturoidcli.transforms import GENERATOR_LINE_FIELDS, generator_to_invoice_payload
from fakturoidcli.validation import load_schema, validate_payload


def test_carries_the_documented_fields(generator: dict[str, Any]) -> None:
    payload = generator_to_invoice_payload(generator)

    assert payload["subject_id"] == 55000123
    assert payload["due"] == 14
    assert payload["payment_method"] == "bank"
    assert payload["currency"] == "CZK"
    assert payload["language"] == "cz"
    assert payload["note"] == ""
    assert payload["footer_note"] == ""
    assert payload["tags"] == []
    assert payload["order_number"] == ""
    # A falsy generator proforma stays absent — the server defaults to a regular invoice.
    assert "proforma" not in payload
    assert "document_type" not in payload


def test_omits_null_fields_instead_of_sending_them(generator: dict[str, Any]) -> None:
    assert generator["number_format_id"] is None
    assert generator["bank_account_id"] is None

    payload = generator_to_invoice_payload(generator)

    assert "number_format_id" not in payload
    assert "bank_account_id" not in payload


def test_drops_generator_only_fields(generator: dict[str, Any]) -> None:
    payload = generator_to_invoice_payload(generator)

    for key in ("id", "name", "html_url", "url", "subject_url", "created_at", "updated_at"):
        assert key not in payload

    for key in ("subtotal", "total", "native_subtotal", "native_total", "rounding_adjustment"):
        assert key not in payload


def test_lines_keep_only_the_five_accepted_fields(generator: dict[str, Any]) -> None:
    payload = generator_to_invoice_payload(generator)

    assert payload["lines"] == [
        {"name": "Konzultace", "quantity": "10.0", "unit_name": "MD", "unit_price": "4500.0", "vat_rate": 21},
        {"name": "Cestovné", "quantity": "1.0", "unit_name": "", "unit_price": "950.0", "vat_rate": 21},
    ]

    for line in payload["lines"]:
        assert set(line) <= set(GENERATOR_LINE_FIELDS)


def test_line_id_never_survives(generator: dict[str, Any]) -> None:
    # A generator line id points at a row of the template, not of the new invoice.
    assert all(line["id"] for line in generator["lines"])

    for line in generator_to_invoice_payload(generator)["lines"]:
        assert "id" not in line


def test_computed_line_fields_never_survive(generator: dict[str, Any]) -> None:
    computed = (
        "unit_price_without_vat",
        "unit_price_with_vat",
        "total_price_without_vat",
        "total_vat",
        "native_total_price_without_vat",
        "native_total_vat",
        "inventory",
    )

    for line in generator_to_invoice_payload(generator)["lines"]:
        for key in computed:
            assert key not in line


def test_key_order_is_stable(generator: dict[str, Any]) -> None:
    payload = generator_to_invoice_payload(generator)

    assert list(payload) == [
        "subject_id",
        "lines",
        "due",
        "payment_method",
        "currency",
        "language",
        "note",
        "footer_note",
        "tags",
        "order_number",
    ]


def test_proforma_generator_produces_document_type(generator: dict[str, Any]) -> None:
    proforma_generator = {**generator, "proforma": True}
    payload = generator_to_invoice_payload(proforma_generator)

    assert payload["document_type"] == "proforma"
    assert "proforma" not in payload


def test_input_is_not_mutated(generator: dict[str, Any]) -> None:
    generator_to_invoice_payload(generator)

    assert generator["lines"][0]["id"] == 700001
    assert "subtotal" in generator


def test_output_validates_against_the_invoice_create_schema(generator: dict[str, Any]) -> None:
    # This is what keeps the transform and the schema honest with each other.
    validate_payload(generator_to_invoice_payload(generator), load_schema("invoices", "create"))


def test_output_raises_no_unknown_field_warning(generator: dict[str, Any], capsys) -> None:
    validate_payload(generator_to_invoice_payload(generator), load_schema("invoices", "create"))

    assert capsys.readouterr().err == ""
