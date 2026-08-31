"""Typer applications, one module per resource.

``api`` is the generic passthrough that reaches every endpoint. Resource
modules register their own typer app here as they land.
"""

from .api import api_command

__all__ = ["api_command"]
