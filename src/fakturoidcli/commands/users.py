"""User commands. The one endpoint that carries no account slug."""

from __future__ import annotations

import typer

from .common import run_get

__all__ = ["app"]

app = typer.Typer(name="users", help="User operations.", no_args_is_help=True, rich_markup_mode=None)


@app.command("me")
def users_me() -> None:
    """Show the user behind the credentials, with every account they can reach.

    GET /user.json. The path carries no slug, so --slug changes nothing here.
    The response holds default_account and an accounts array, which is where the
    slug for the config file comes from.
    """
    run_get("/user.json")
