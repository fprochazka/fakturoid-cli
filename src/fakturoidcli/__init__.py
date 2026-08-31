"""Fakturoid CLI - a command-line interface for the Fakturoid REST API v3.

The package is a thin transport over the API: one shell command becomes one HTTP
request, and the response body is printed to stdout as raw JSON.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
