"""Shared test fixtures.

The generator fixture is an anonymized capture: invented account, customer,
line names and rates. This repository is public, so no real accounting data
belongs in it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def generator() -> dict[str, Any]:
    """The body of GET /generators/{id}.json for a monthly invoice template."""
    data: dict[str, Any] = json.loads((FIXTURE_DIR / "generator.json").read_text(encoding="utf-8"))
    return data
