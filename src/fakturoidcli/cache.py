"""Disk cache for the OAuth2 access token.

The token lives 7200 seconds, so caching it turns a two-request command into
one. The cache sits next to the config file in ``~/.config/fakturoidcli/``, is
disposable, and is regenerated on demand: every read failure degrades to a miss
rather than an exception.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import ensure_config_dir, get_config_path
from .constants import PRIVATE_FILE_MODE, TOKEN_EXPIRY_MARGIN_SECONDS

__all__ = ["get_cache_path", "get_cached_token", "store_token", "clear_token"]


def get_cache_path() -> Path:
    """Get the path to the token cache file."""
    return get_config_path().parent / "cache.json"


def _client_fingerprint(client_id: str) -> str:
    """Fingerprint the client_id.

    A hash identifies the credentials that a cached token belongs to without
    writing a second copy of them to disk.
    """
    return hashlib.sha256(client_id.encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, Any]:
    """Load the cache file, treating any problem as an empty cache."""
    path = get_cache_path()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache(data: dict[str, Any]) -> None:
    """Write the cache file with owner-only permissions, ignoring failures."""
    try:
        ensure_config_dir()
        path = get_cache_path()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        path.chmod(PRIVATE_FILE_MODE)
    except OSError:
        pass


def get_cached_token(profile: str, client_id: str) -> str | None:
    """Return a cached access token that is still valid.

    Args:
        profile: The profile the token was fetched for.
        client_id: The credentials the caller expects the token to belong to.

    Returns:
        The access token, or None on a miss, an expired entry, or a credential
        mismatch.
    """
    entry = _load_cache().get(profile)
    if not isinstance(entry, dict):
        return None

    if entry.get("client_fingerprint") != _client_fingerprint(client_id):
        return None

    token = entry.get("access_token")
    expires_at = entry.get("expires_at")
    if not token or not expires_at:
        return None

    try:
        expiry = datetime.fromisoformat(expires_at)
    except (TypeError, ValueError):
        return None
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)

    if datetime.now(UTC) + timedelta(seconds=TOKEN_EXPIRY_MARGIN_SECONDS) >= expiry:
        return None

    return token


def store_token(profile: str, client_id: str, access_token: str, expires_in: int) -> None:
    """Record a freshly fetched access token with its absolute expiry."""
    cache = _load_cache()
    cache[profile] = {
        "client_fingerprint": _client_fingerprint(client_id),
        "access_token": access_token,
        "expires_at": (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat(),
    }
    _write_cache(cache)


def clear_token(profile: str) -> None:
    """Drop the cached token for a profile."""
    cache = _load_cache()
    if cache.pop(profile, None) is not None:
        _write_cache(cache)
