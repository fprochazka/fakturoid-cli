"""Entry point: the typer app, the global options, and the exit-code mapping."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .commands import (
    account_app,
    api_command,
    generators_app,
    invoices_app,
    subjects_app,
    users_app,
)
from .context import get_context, parse_fields
from .errors import ExitCode, FakturoidError, UsageError
from .logging import setup_logging
from .output import output_json, report_error, stderr_line

app = typer.Typer(
    name="fakturoid",
    help="A command-line interface for Fakturoid.",
    no_args_is_help=True,
    rich_markup_mode=None,
)

app.add_typer(users_app, name="users")
app.add_typer(account_app, name="account")
app.add_typer(subjects_app, name="subjects")
app.add_typer(generators_app, name="generators")
app.add_typer(invoices_app, name="invoices")
app.command("api")(api_command)

_ctx = get_context()

# Global options that take a value, and the bare flags, for argv hoisting.
_VALUE_OPTIONS = {"--slug", "--profile", "-p", "--output-dir", "--page", "--field", "-f"}
_FLAG_OPTIONS = {"--dry-run", "--all", "--verbose", "-v", "--version", "-V"}


def version_callback(value: bool) -> None:
    """Print the version as JSON, keeping stdout machine-readable."""
    if value:
        output_json({"name": "fakturoid", "version": __version__})
        raise typer.Exit()


@app.callback()
def main(
    slug: Annotated[
        str | None,
        typer.Option("--slug", help="Account slug for this invocation. Overrides default_slug."),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Credential profile from the config file."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the request that would be sent and send nothing."),
    ] = False,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Directory for downloaded files. Defaults to /tmp/fakturoid."),
    ] = None,
    page: Annotated[
        int | None,
        typer.Option("--page", help="Page number for list endpoints. 40 records per page."),
    ] = None,
    all_pages: Annotated[
        bool,
        typer.Option("--all", help="Walk every page and print one merged JSON array."),
    ] = False,
    fields: Annotated[
        list[str] | None,
        typer.Option("--field", "-f", help="Extra query parameter, as key=value. Repeatable."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Log request lines to stderr.", is_eager=True),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", help="Show version and exit.", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """Fakturoid CLI - one shell command, one HTTP request, raw JSON on stdout."""
    setup_logging(verbose=verbose)

    if page is not None and all_pages:
        raise UsageError("--page and --all are mutually exclusive")

    _ctx.verbose = verbose
    _ctx.profile = profile
    _ctx.slug = slug
    _ctx.dry_run = dry_run
    _ctx.output_dir = output_dir
    _ctx.page = page
    _ctx.all_pages = all_pages
    _ctx.fields = parse_fields(fields)


def _hoist_global_options(argv: list[str]) -> list[str]:
    """Move global options to before the first subcommand.

    Typer/Click requires group-level options to appear before subcommands. This
    lets a user write the flags after the full command path, which is also what
    prefix-based permission matching needs.
    """
    hoisted: list[str] = []
    rest: list[str] = []

    i = 0
    while i < len(argv):
        arg = argv[i]

        # Everything after -- is an argument, never an option.
        if arg == "--":
            rest.extend(argv[i:])
            break

        if any(arg.startswith(f"{opt}=") for opt in _VALUE_OPTIONS):
            hoisted.append(arg)
            i += 1
        elif arg in _VALUE_OPTIONS:
            hoisted.append(arg)
            if i + 1 < len(argv):
                i += 1
                hoisted.append(argv[i])
            i += 1
        elif arg in _FLAG_OPTIONS:
            hoisted.append(arg)
            i += 1
        else:
            rest.append(arg)
            i += 1

    return hoisted + rest


def cli() -> None:
    """Run the CLI, mapping every failure onto its exit code."""
    try:
        sys.argv[1:] = _hoist_global_options(sys.argv[1:])
        app()
    except FakturoidError as e:
        report_error(e)
        sys.exit(e.exit_code)
    except Exception as e:
        stderr_line(f"error: {e}")
        traceback.print_exc(file=sys.stderr)
        sys.exit(ExitCode.INTERNAL)
