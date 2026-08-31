"""Logging configuration and console output utilities.

Both consoles write to stderr. Nothing renders data through Rich, because Rich
wraps at the terminal width and corrupts JSON.
"""

import logging

from rich.console import Console
from rich.logging import RichHandler

__all__ = ["error_console", "setup_logging", "get_logger"]

# Console for error output (writes to stderr)
error_console = Console(stderr=True)


def setup_logging(verbose: bool = False) -> None:
    """Route logging to stderr, at DEBUG level when verbose."""
    level = logging.DEBUG if verbose else logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=error_console,
                rich_tracebacks=True,
                show_time=verbose,
                show_path=verbose,
            )
        ],
    )

    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a module."""
    return logging.getLogger(name)
