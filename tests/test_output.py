"""stdout carries JSON and nothing else.

Rich wraps text at 80 columns when stdout is not a TTY, which puts literal
newlines inside JSON string values. The same bug was fixed twice in the sibling
CLIs, so the output path is checked here through a real pipe with a narrow
COLUMNS, which is the condition that used to break it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from fakturoidcli.output import download_filename, output_json, write_download

LONG_CZECH_TEXT = (
    "Faktura za vývoj software a konzultace za měsíc srpen, včetně víceprací "
    "a cestovného, splatnost čtrnáct dnů od data vystavení dokladu."
)

PROGRAM = """
import json
from fakturoidcli.output import output_json
output_json(json.loads(__import__("sys").stdin.read()))
"""


def run_in_narrow_terminal(document: object) -> str:
    """Print a document through the real entry point with COLUMNS=40."""
    result = subprocess.run(
        [sys.executable, "-c", PROGRAM],
        input=json.dumps(document),
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "COLUMNS": "40"},
        cwd=Path(__file__).parent.parent,
    )
    return result.stdout


def test_narrow_columns_still_produce_parseable_json() -> None:
    document = {"note": LONG_CZECH_TEXT, "lines": [{"name": "Konzultace", "unit_price": "4500.0"}]}

    printed = run_in_narrow_terminal(document)

    assert json.loads(printed) == document


def test_narrow_columns_do_not_wrap_a_long_string() -> None:
    printed = run_in_narrow_terminal({"note": LONG_CZECH_TEXT})

    assert json.loads(printed)["note"] == LONG_CZECH_TEXT
    assert "\n" not in json.loads(printed)["note"]


def test_narrow_columns_survive_a_long_array() -> None:
    document = [{"id": index, "number": f"2600{index}"} for index in range(50)]

    assert json.loads(run_in_narrow_terminal(document)) == document


def test_czech_text_is_not_escaped(capsys: pytest.CaptureFixture[str]) -> None:
    output_json({"name": "Vývoj software"})

    assert "Vývoj software" in capsys.readouterr().out


def test_output_is_indented(capsys: pytest.CaptureFixture[str]) -> None:
    output_json({"a": 1})

    assert capsys.readouterr().out == '{\n  "a": 1\n}\n'


def test_download_filename_carries_resource_identifier_and_timestamp() -> None:
    name = download_filename("invoice", "60000001", "application/pdf", datetime(2026, 8, 31, 22, 0, 0))

    assert name == "invoice-60000001-20260831T220000.pdf"


def test_download_filename_falls_back_to_bin() -> None:
    name = download_filename("api", "download", "application/x-nonsense", datetime(2026, 8, 31, 22, 0, 0))

    assert name.endswith(".bin")


def test_download_descriptor_is_the_only_thing_on_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    descriptor = write_download(
        b"%PDF-1.4 ...", resource="invoice", identifier="1", content_type="application/pdf", output_dir=tmp_path
    )

    assert capsys.readouterr().out == ""
    assert set(descriptor) == {"path", "content_type", "bytes"}
    assert descriptor["content_type"] == "application/pdf"
    assert descriptor["bytes"] == 12
    assert Path(descriptor["path"]).read_bytes() == b"%PDF-1.4 ..."


def test_downloaded_files_are_readable_only_by_their_owner(tmp_path: Path) -> None:
    descriptor = write_download(
        b"x", resource="invoice", identifier="1", content_type="application/pdf", output_dir=tmp_path / "nested"
    )

    assert (Path(descriptor["path"]).stat().st_mode & 0o777) == 0o600
    assert ((tmp_path / "nested").stat().st_mode & 0o777) == 0o700
