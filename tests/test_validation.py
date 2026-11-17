"""Payload validation: open-world schemas that warn instead of blocking."""

from __future__ import annotations

import pytest

from fakturoidcli.errors import ExitCode, UsageError
from fakturoidcli.validation import load_schema, validate_payload

WRITE_ACTIONS = [
    ("invoices", "create"),
    ("invoices", "update"),
    ("generators", "create"),
    ("generators", "update"),
]


@pytest.mark.parametrize(("resource", "action"), WRITE_ACTIONS)
def test_every_write_action_has_a_schema(resource: str, action: str) -> None:
    schema = load_schema(resource, action)

    assert schema.endpoint
    assert schema.schema["properties"]
    assert schema.schema["additionalProperties"] is True


def test_valid_invoice_payload_passes(capsys: pytest.CaptureFixture[str]) -> None:
    payload = {
        "subject_id": 55000123,
        "due": 14,
        "language": "cz",
        "payment_method": "bank",
        "lines": [
            {"name": "Konzultace", "quantity": "10.0", "unit_name": "MD", "unit_price": "4500.0", "vat_rate": 21}
        ],
    }

    validate_payload(payload, load_schema("invoices", "create"))

    assert capsys.readouterr().err == ""


def test_bad_enum_value_fails_and_names_the_field() -> None:
    payload = {"subject_id": 1, "language": "cs"}

    with pytest.raises(UsageError) as raised:
        validate_payload(payload, load_schema("invoices", "create"))

    message = str(raised.value)
    assert "language" in message
    assert "'cs'" in message
    assert "'cz'" in message
    assert raised.value.exit_code == ExitCode.USAGE


def test_bad_type_fails_and_names_the_field() -> None:
    with pytest.raises(UsageError) as raised:
        validate_payload({"subject_id": "55000123"}, load_schema("invoices", "create"))

    assert "subject_id" in str(raised.value)


def test_bad_value_inside_a_line_names_its_position() -> None:
    payload = {
        "subject_id": 1,
        "lines": [{"name": "ok", "unit_price": "1.0"}, {"name": "bad", "unit_price": True}],
    }

    with pytest.raises(UsageError) as raised:
        validate_payload(payload, load_schema("invoices", "create"))

    assert "lines[1].unit_price" in str(raised.value)


def test_missing_required_field_fails() -> None:
    with pytest.raises(UsageError) as raised:
        validate_payload({"note": "hello"}, load_schema("invoices", "create"))

    assert "subject_id" in str(raised.value)


def test_unknown_field_passes_with_exactly_one_warning(capsys: pytest.CaptureFixture[str]) -> None:
    validate_payload({"subject_id": 1, "subject_di": 2}, load_schema("invoices", "create"))

    warnings = capsys.readouterr().err.strip().splitlines()
    assert warnings == ["warning: 'subject_di' is not a known field for POST /invoices.json - sending it anyway"]


def test_unknown_field_inside_a_line_is_reported_with_its_position(capsys: pytest.CaptureFixture[str]) -> None:
    payload = {"subject_id": 1, "lines": [{"name": "ok", "unit_pric": "1.0"}]}

    validate_payload(payload, load_schema("invoices", "create"))

    warnings = capsys.readouterr().err.strip().splitlines()
    assert len(warnings) == 1
    assert "lines[0].unit_pric" in warnings[0]


def test_patch_accepts_a_single_field(capsys: pytest.CaptureFixture[str]) -> None:
    validate_payload({"note": "September"}, load_schema("invoices", "update"))
    validate_payload({"name": "ZZZ test template"}, load_schema("generators", "update"))

    assert capsys.readouterr().err == ""


def test_patch_requires_nothing() -> None:
    assert load_schema("invoices", "update").schema["required"] == []
    assert load_schema("generators", "update").schema["required"] == []


def test_patch_still_enforces_enums() -> None:
    with pytest.raises(UsageError) as raised:
        validate_payload({"vat_price_mode": "with_vat"}, load_schema("generators", "update"))

    assert "vat_price_mode" in str(raised.value)


def test_generator_create_requires_name_and_subject() -> None:
    with pytest.raises(UsageError) as raised:
        validate_payload({"name": "ZZZ test template"}, load_schema("generators", "create"))

    assert "subject_id" in str(raised.value)


def test_a_non_object_body_is_rejected() -> None:
    with pytest.raises(UsageError) as raised:
        validate_payload([{"subject_id": 1}], load_schema("invoices", "create"))

    assert "JSON object" in str(raised.value)


def test_the_error_points_at_the_escape_hatch() -> None:
    with pytest.raises(UsageError) as raised:
        validate_payload({"subject_id": 1, "language": "cs"}, load_schema("invoices", "create"))

    assert "fakturoid api" in str(raised.value)
