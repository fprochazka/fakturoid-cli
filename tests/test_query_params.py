"""Path expansion and query-parameter serialization.

Only URL building is exercised, so no test here reaches the network.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from fakturoidcli.client import FakturoidClient
from fakturoidcli.config import ProfileConfig
from fakturoidcli.context import parse_fields
from fakturoidcli.errors import ConfigError, UsageError


def make_client(default_params: dict[str, Any] | None = None, slug: str | None = "example-account") -> FakturoidClient:
    """Build a client that can construct URLs. It never fetches a token."""
    profile = ProfileConfig(
        name="test",
        client_id="id",
        client_secret="secret",
        user_agent_contact="test@example.com",
        default_slug=slug,
    )
    return FakturoidClient(profile, slug=slug, default_params=default_params)


def query_of(url: Any) -> dict[str, list[str]]:
    """Parse a built URL back into its query parameters."""
    return parse_qs(urlsplit(str(url)).query)


# ------------------------------------------------------------------ -f parsing


def test_field_option_parses_key_value() -> None:
    assert parse_fields(["status=open"]) == {"status": "open"}


def test_field_option_keeps_an_equals_sign_in_the_value() -> None:
    assert parse_fields(["query=a=b"]) == {"query": "a=b"}


def test_repeated_field_option_becomes_an_array() -> None:
    assert parse_fields(["tags[]=one", "tags[]=two"]) == {"tags[]": ["one", "two"]}


def test_a_single_bracket_field_is_still_an_array() -> None:
    assert parse_fields(["tags[]=one"]) == {"tags[]": ["one"]}


def test_a_repeated_plain_key_becomes_an_array() -> None:
    assert parse_fields(["status=open", "status=paid"]) == {"status": ["open", "paid"]}


def test_field_option_without_a_value_is_a_usage_error() -> None:
    with pytest.raises(UsageError):
        parse_fields(["status"])


def test_empty_value_is_allowed() -> None:
    assert parse_fields(["custom_id="]) == {"custom_id": ""}


# ------------------------------------------------------------ URL construction


def test_account_relative_path_gets_the_slug() -> None:
    url = make_client().build_url("invoices.json")

    assert str(url) == "https://app.fakturoid.cz/api/v3/accounts/example-account/invoices.json"


def test_absolute_path_skips_the_slug() -> None:
    url = make_client().build_url("/user.json")

    assert str(url) == "https://app.fakturoid.cz/api/v3/user.json"


def test_an_absolute_path_needs_no_slug_at_all() -> None:
    assert str(make_client(slug=None).build_url("/user.json")).endswith("/user.json")


def test_an_account_relative_path_without_a_slug_fails() -> None:
    with pytest.raises(ConfigError):
        make_client(slug=None).build_url("invoices.json")


def test_named_options_become_query_parameters() -> None:
    url = make_client().build_url("invoices.json", {"status": "open", "subject_id": 55000123})

    assert query_of(url) == {"status": ["open"], "subject_id": ["55000123"]}


def test_none_valued_options_are_dropped() -> None:
    url = make_client().build_url("invoices.json", {"status": "open", "number": None, "since": None})

    assert query_of(url) == {"status": ["open"]}


def test_repeated_tags_serialize_as_an_array() -> None:
    url = make_client(parse_fields(["tags[]=retainer", "tags[]=monthly"])).build_url("invoices/search.json")

    assert query_of(url) == {"tags[]": ["retainer", "monthly"]}
    assert "tags%5B%5D=retainer&tags%5B%5D=monthly" in str(url)


def test_global_fields_reach_a_dedicated_command() -> None:
    url = make_client(parse_fields(["custom_field=1"])).build_url("invoices.json", {"status": "open"})

    assert query_of(url) == {"custom_field": ["1"], "status": ["open"]}


def test_a_named_option_wins_over_the_same_global_field() -> None:
    url = make_client(parse_fields(["status=paid"])).build_url("invoices.json", {"status": "open"})

    assert query_of(url) == {"status": ["open"]}


def test_pagination_parameter_is_serialized() -> None:
    url = make_client().build_url("invoices.json", {"page": 2})

    assert query_of(url) == {"page": ["2"]}


def test_only_the_fakturoid_host_is_accepted() -> None:
    with pytest.raises(UsageError):
        make_client().build_url("https://example.com/api/v3/invoices.json")
