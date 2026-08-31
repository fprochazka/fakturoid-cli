"""Global context shared by every command.

Holds the global options and builds the client lazily, so a command that only
prints help never touches the config file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .errors import UsageError

if TYPE_CHECKING:
    from .client import FakturoidClient
    from .config import ProfileConfig

__all__ = ["Context", "get_context", "parse_fields"]


def parse_fields(raw: list[str] | None) -> dict[str, Any]:
    """Parse repeated ``-f key=value`` options into query parameters.

    A key repeated twice, or a key ending in ``[]``, becomes an array, which is
    the ``tags[]=a&tags[]=b`` form the API expects.

    Args:
        raw: The raw option values as typed.

    Returns:
        Query parameters, with a string or a list of strings per key.

    Raises:
        UsageError: If a value is not in ``key=value`` form.
    """
    params: dict[str, Any] = {}
    for item in raw or []:
        key, separator, value = item.partition("=")
        key = key.strip()
        if not separator or not key:
            raise UsageError(f"-f expects key=value, got: {item}")

        if key in params:
            existing = params[key]
            params[key] = [*existing, value] if isinstance(existing, list) else [existing, value]
        elif key.endswith("[]"):
            params[key] = [value]
        else:
            params[key] = value
    return params


@dataclass
class Context:
    """The global options of one invocation."""

    verbose: bool = False
    profile: str | None = None
    slug: str | None = None
    dry_run: bool = False
    output_dir: Path | None = None
    page: int | None = None
    all_pages: bool = False
    fields: dict[str, Any] = field(default_factory=dict)
    _config: ProfileConfig | None = field(default=None, repr=False)
    _client: FakturoidClient | None = field(default=None, repr=False)

    @property
    def config(self) -> ProfileConfig:
        """Get the resolved credential profile, loading it on first use."""
        if self._config is None:
            from .config import load_profile

            self._config = load_profile(self.profile)
        return self._config

    @property
    def client(self) -> FakturoidClient:
        """Get the API client for the resolved profile and slug."""
        if self._client is None:
            from .client import FakturoidClient

            config = self.config
            self._client = FakturoidClient(
                config,
                slug=self.slug or config.default_slug,
                dry_run=self.dry_run,
                output_dir=self.output_dir,
                default_params=self.fields,
            )
        return self._client

    def pagination_params(self) -> dict[str, Any]:
        """Query parameters for a single-page fetch."""
        return {"page": self.page} if self.page is not None else {}


_ctx = Context()


def get_context() -> Context:
    """Get the process-wide context."""
    return _ctx
