"""Typer applications, one module per resource.

``api`` is the generic passthrough that reaches every endpoint. Resource
modules register their own typer app here as they land.
"""

from .account import app as account_app
from .api import api_command
from .generators import app as generators_app
from .invoices import app as invoices_app
from .subjects import app as subjects_app
from .users import app as users_app

__all__ = [
    "api_command",
    "account_app",
    "generators_app",
    "invoices_app",
    "subjects_app",
    "users_app",
]
