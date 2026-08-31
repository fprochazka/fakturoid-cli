"""Payload validation for the write commands.

An agent driving this CLI must fail loudly on a wrong value instead of quietly
creating a broken financial document. The schemas are open-world: an unknown
field is reported on stderr and sent anyway, because Fakturoid ships fields
before we model them. Types and enums are enforced, requiredness barely is.

There is no bypass flag. ``fakturoid api`` is the escape hatch and the only one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator

from .errors import UsageError
from .output import warn

__all__ = ["PayloadSchema", "load_schema", "validate_payload"]

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PayloadSchema:
    """One write endpoint's request-body schema, plus the label used in messages."""

    endpoint: str
    summary: str
    schema: dict[str, Any]


@cache
def load_schema(resource: str, action: str) -> PayloadSchema:
    """Load the request-body schema for one write action.

    One file per resource holds the shared field list once and gives each action
    its own ``required`` list, so ``create`` and ``update`` cannot drift apart.

    Args:
        resource: The CLI resource name, for example ``invoices``.
        action: The write action, ``create`` or ``update``.

    Returns:
        The schema, ready for ``validate_payload``.
    """
    raw = (files("fakturoidcli") / "schemas" / f"{resource}.json").read_text(encoding="utf-8")
    document = json.loads(raw)

    if document.get("schema_version") != SCHEMA_VERSION:
        raise UsageError(f"schemas/{resource}.json declares an unsupported schema_version")

    entry = document["actions"][action]
    return PayloadSchema(
        endpoint=entry["endpoint"],
        summary=entry["summary"],
        schema={**document["body"], "required": entry["required"]},
    )


def _unknown_field_paths(value: Any, schema: Any, prefix: str = "") -> list[str]:
    """Collect the payload keys that the schema does not name.

    The walk descends only where the schema declares ``properties``, so a field
    holding free-form data never produces a warning about its contents.
    """
    if not isinstance(schema, dict):
        return []

    if isinstance(value, dict):
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return []
        found: list[str] = []
        for key, item in value.items():
            path = f"{prefix}{key}"
            if key not in properties:
                found.append(path)
            else:
                found.extend(_unknown_field_paths(item, properties[key], f"{path}."))
        return found

    if isinstance(value, list):
        base = prefix.rstrip(".")
        found = []
        for index, item in enumerate(value):
            found.extend(_unknown_field_paths(item, schema.get("items"), f"{base}[{index}]."))
        return found

    return []


def _error_path(path: Any) -> str:
    """Render a jsonschema error path as ``lines[0].unit_price``."""
    parts: list[str] = []
    for token in path:
        if isinstance(token, int):
            parts.append(f"[{token}]")
        else:
            parts.append(f".{token}" if parts else str(token))
    return "".join(parts) or "(payload)"


def validate_payload(payload: Any, schema: PayloadSchema) -> None:
    """Check a request body before it is sent.

    Unknown fields produce one stderr warning each and are kept. A wrong type,
    a wrong enum value or a missing required field stops the command, so nothing
    reaches the server.

    Args:
        payload: The body as parsed from ``--payload`` or stdin.
        schema: The schema for the endpoint the body is going to.

    Raises:
        UsageError: If the body breaks the schema.
    """
    if not isinstance(payload, dict):
        raise UsageError(f"{schema.endpoint} expects a JSON object, got {type(payload).__name__}")

    for path in _unknown_field_paths(payload, schema.schema):
        warn(f"'{path}' is not a known field for {schema.endpoint} - sending it anyway")

    errors = sorted(Draft202012Validator(schema.schema).iter_errors(payload), key=lambda e: list(e.absolute_path))
    if not errors:
        return

    lines = [f"payload is not valid for {schema.endpoint}"]
    lines += [f"  {_error_path(error.absolute_path)}: {error.message}" for error in errors]
    lines.append("Use 'fakturoid api' to send a body without validation.")
    raise UsageError("\n".join(lines))
