"""Credential profiles, read from ~/.config/fakturoidcli/config.toml.

One TOML table per profile. Environment variables beat file values, so a shell
can drive the CLI without a config file at all.
"""

from __future__ import annotations

import os
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import PRIVATE_DIR_MODE, PRIVATE_FILE_MODE
from .errors import ConfigError
from .output import warn

__all__ = [
    "ProfileConfig",
    "DEFAULT_CONFIG_DIR",
    "get_config_path",
    "ensure_config_dir",
    "list_profiles",
    "load_profile",
    "save_profile",
]

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "fakturoidcli"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.toml"

ENV_CONFIG = "FAKTUROID_CONFIG"
ENV_PROFILE = "FAKTUROID_PROFILE"
ENV_CLIENT_ID = "FAKTUROID_CLIENT_ID"
ENV_CLIENT_SECRET = "FAKTUROID_CLIENT_SECRET"
ENV_SLUG = "FAKTUROID_SLUG"
ENV_USER_AGENT_CONTACT = "FAKTUROID_USER_AGENT_CONTACT"


@dataclass
class ProfileConfig:
    """One set of OAuth2 client credentials and the account they point at."""

    name: str
    client_id: str
    client_secret: str
    user_agent_contact: str
    default_slug: str | None = None


def get_config_path() -> Path:
    """Get the path to the config file, honoring FAKTUROID_CONFIG."""
    override = os.environ.get(ENV_CONFIG)
    return Path(override).expanduser() if override else DEFAULT_CONFIG_FILE


def ensure_config_dir() -> Path:
    """Create the config directory if it is missing and lock it to the owner."""
    directory = get_config_path().parent
    existed = directory.exists()
    directory.mkdir(parents=True, exist_ok=True)
    if not existed:
        directory.chmod(PRIVATE_DIR_MODE)
    return directory


def _read_config_file() -> dict[str, Any]:
    """Read the whole config file, or return an empty mapping when it is missing."""
    path = get_config_path()
    if not path.exists():
        return {}

    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        warn(f"{path} is readable by other users - run: chmod 600 {path}")

    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"Failed to read {path}: {e}") from e


def list_profiles() -> list[str]:
    """List the profile names declared in the config file."""
    return sorted(name for name, table in _read_config_file().items() if isinstance(table, dict))


def _resolve_profile_name(requested: str | None, tables: dict[str, Any]) -> str:
    """Pick the profile to use.

    Order:
    1. Explicit ``requested`` (from ``--profile`` / ``FAKTUROID_PROFILE``).
    2. ``default``, when the config file declares it.
    3. The sole configured profile, if exactly one exists.
    4. ``default``, so an environment-only setup needs no config file.
    """
    if requested:
        return requested
    from_env = os.environ.get(ENV_PROFILE)
    if from_env:
        return from_env
    if "default" in tables:
        return "default"
    if len(tables) == 1:
        return next(iter(tables))
    return "default"


def load_profile(name: str | None = None) -> ProfileConfig:
    """Load a credential profile from the config file and the environment.

    Args:
        name: The profile to load, or None to follow the resolution order.

    Returns:
        The resolved profile.

    Raises:
        ConfigError: If the profile is unknown or a mandatory value is missing.
    """
    data = _read_config_file()
    tables = {key: value for key, value in data.items() if isinstance(value, dict)}
    profile_name = _resolve_profile_name(name, tables)

    table = tables.get(profile_name, {})
    if name and name not in tables and not os.environ.get(ENV_CLIENT_ID):
        raise ConfigError(_unknown_profile_message(profile_name, sorted(tables)))

    client_id = os.environ.get(ENV_CLIENT_ID) or table.get("client_id")
    client_secret = os.environ.get(ENV_CLIENT_SECRET) or table.get("client_secret")
    contact = os.environ.get(ENV_USER_AGENT_CONTACT) or table.get("user_agent_contact")
    slug = os.environ.get(ENV_SLUG) or table.get("default_slug")

    if not client_id or not client_secret:
        raise ConfigError(_missing_credentials_message(profile_name, sorted(tables)))

    if not contact:
        raise ConfigError(
            f"Profile '{profile_name}' has no user_agent_contact. The API answers 400 without a User-Agent. "
            f'Add user_agent_contact = "you@example.com" to {get_config_path()}, '
            f"or set {ENV_USER_AGENT_CONTACT}."
        )

    return ProfileConfig(
        name=profile_name,
        client_id=client_id,
        client_secret=client_secret,
        user_agent_contact=contact,
        default_slug=slug,
    )


def _unknown_profile_message(profile_name: str, available: list[str]) -> str:
    """Name the missing profile and list the ones that do exist."""
    known = ", ".join(available) if available else "none"
    return f"Unknown profile '{profile_name}' in {get_config_path()}. Available profiles: {known}."


def _missing_credentials_message(profile_name: str, available: list[str]) -> str:
    """Explain how to supply credentials, listing what the file already holds."""
    known = ", ".join(available) if available else "none"
    return (
        f"No client credentials for profile '{profile_name}'. Available profiles: {known}.\n"
        f"Add them to {get_config_path()}:\n\n"
        f"[{profile_name}]\n"
        f'client_id = "..."\n'
        f'client_secret = "..."\n'
        f'default_slug = "your-account-slug"\n'
        f'user_agent_contact = "you@example.com"\n\n'
        f"Or set {ENV_CLIENT_ID} and {ENV_CLIENT_SECRET} in the environment."
    )


def save_profile(name: str, values: dict[str, Any]) -> None:
    """Merge one profile into the config file, preserving the others.

    The file holds plaintext secrets, so the mode is set to 0600.

    Args:
        name: The profile table to write.
        values: The keys to set on that profile.
    """
    import tomli_w

    ensure_config_dir()
    path = get_config_path()

    data = _read_config_file()
    table = data.get(name)
    merged = dict(table) if isinstance(table, dict) else {}
    merged.update(values)
    data[name] = merged

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_FILE_MODE)
    with os.fdopen(fd, "wb") as handle:
        tomli_w.dump(data, handle)
    path.chmod(PRIVATE_FILE_MODE)
