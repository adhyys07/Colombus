from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False


class ConfigError(RuntimeError):
    """Raised when required credentials are missing."""


DEFAULT_CACHE_DIR = Path.home() / ".cache" / "colombus"
DEFAULT_CACHE_TTL = 7 * 24 * 3600
DEFAULT_POSTER_SIZE = "w342"
DEFAULT_HTTP_RETRIES = 3
# Wikimedia rejects generic User-Agents; theirs must carry a contact URL.
# Override COLOMBUS_USER_AGENT to point at your own project or e-mail.
DEFAULT_USER_AGENT = (
    "Colombus/0.1 (https://github.com/colombus/colombus; terminal movie browser)"
)

_MISSING_TMDB = (
    "No TMDB credentials found.\n"
    "Set TMDB_API_KEY (v3) or TMDB_ACCESS_TOKEN (v4) in your "
    "environment or a .env file.\n"
    "Get one free at https://www.themoviedb.org/settings/api"
)


def _env_int(name: str, default: int) -> int:
    """Read an int from the environment, falling back on junk values."""
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    tmdb_api_key: str | None
    tmdb_access_token: str | None
    omdb_api_key: str | None
    cache_dir: Path
    cache_ttl: int
    poster_size: str
    http_retries: int = DEFAULT_HTTP_RETRIES
    user_agent: str = DEFAULT_USER_AGENT

    @property
    def has_omdb(self) -> bool:
        return bool(self.omdb_api_key)

    @property
    def tmdb_headers(self) -> dict[str, str]:
        """Bearer auth for the v4 token; empty when only a v3 key is set."""
        if self.tmdb_access_token:
            return {"Authorization": f"Bearer {self.tmdb_access_token}"}
        return {}

    @classmethod
    def load(cls, env_file: str | os.PathLike | None = None) -> Config:
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        tmdb_key = os.getenv("TMDB_API_KEY") or None
        tmdb_token = os.getenv("TMDB_ACCESS_TOKEN") or None
        if not (tmdb_key or tmdb_token):
            raise ConfigError(_MISSING_TMDB)

        cache_dir = Path(
            os.getenv("COLOMBUS_CACHE_DIR") or DEFAULT_CACHE_DIR
        ).expanduser()

        return cls(
            tmdb_api_key=tmdb_key,
            tmdb_access_token=tmdb_token,
            omdb_api_key=os.getenv("OMDB_API_KEY") or None,
            cache_dir=cache_dir,
            cache_ttl=_env_int("COLOMBUS_CACHE_TTL", DEFAULT_CACHE_TTL),
            poster_size=os.getenv("COLOMBUS_POSTER_SIZE") or DEFAULT_POSTER_SIZE,
            http_retries=max(0, _env_int("COLOMBUS_HTTP_RETRIES", DEFAULT_HTTP_RETRIES)),
            user_agent=os.getenv("COLOMBUS_USER_AGENT") or DEFAULT_USER_AGENT,
        )
