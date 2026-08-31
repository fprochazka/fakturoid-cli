"""Account commands. The account is read-only in the API."""

from __future__ import annotations

import typer

from .common import run_get

__all__ = ["app"]

app = typer.Typer(name="account", help="Account operations.", no_args_is_help=True, rich_markup_mode=None)


@app.command("show")
def account_show() -> None:
    """Show the account behind the current slug.

    GET /accounts/{slug}/account.json. Fakturoid keeps the account read-only, so
    there is no update command. This is also the cheapest check that the
    credentials and the slug resolve.
    """
    run_get("account.json")
