"""Request-body precedence: --payload, then --input, then piped stdin."""

from __future__ import annotations

import io
import sys

import pytest

from fakturoidcli.errors import UsageError
from fakturoidcli.payload import read_json_body, require_json_body


class PipedStdin(io.StringIO):
    """A stdin that reports itself as a pipe, the way a shell pipeline does."""

    def isatty(self) -> bool:
        return False


class TerminalStdin(io.StringIO):
    """A stdin that reports itself as a terminal, the way an interactive shell does."""

    def isatty(self) -> bool:
        return True


@pytest.fixture
def piped(monkeypatch):
    def attach(text: str) -> None:
        monkeypatch.setattr(sys, "stdin", PipedStdin(text))

    return attach


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr(sys, "stdin", TerminalStdin(""))


def test_payload_option_is_parsed(interactive) -> None:
    assert read_json_body('{"note": "x"}') == {"note": "x"}


def test_payload_option_beats_stdin(piped) -> None:
    piped('{"note": "from stdin"}')

    assert read_json_body('{"note": "from payload"}') == {"note": "from payload"}


def test_input_file_is_read(tmp_path, interactive) -> None:
    path = tmp_path / "body.json"
    path.write_text('{"note": "from file"}', encoding="utf-8")

    assert read_json_body(None, str(path)) == {"note": "from file"}


def test_input_dash_reads_stdin(piped) -> None:
    piped('{"note": "from stdin"}')

    assert read_json_body(None, "-") == {"note": "from stdin"}


def test_piped_stdin_is_read_without_any_option(piped) -> None:
    piped('{"note": "from stdin"}')

    assert read_json_body(None) == {"note": "from stdin"}


def test_a_terminal_stdin_is_never_read(interactive) -> None:
    assert read_json_body(None) is None


def test_an_empty_pipe_means_no_body(piped) -> None:
    piped("   \n")

    assert read_json_body(None) is None


def test_invalid_json_is_a_usage_error(interactive) -> None:
    with pytest.raises(UsageError) as raised:
        read_json_body("{not json")

    assert "Invalid JSON" in str(raised.value)


def test_a_required_body_that_is_absent_is_a_usage_error(interactive) -> None:
    with pytest.raises(UsageError) as raised:
        require_json_body(None)

    assert "--payload" in str(raised.value)


def test_a_required_body_reads_the_same_sources(piped) -> None:
    piped('{"note": "x"}')

    assert require_json_body(None) == {"note": "x"}
