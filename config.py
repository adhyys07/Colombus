from __future__ import annotations

import os
import sys
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
DEFAULT_POSTER_PROTOCOL = "auto"
DEFAULT_REGION = "US"
DEFAULT_LANGUAGE = "en-US"
DEFAULT_UI_LANGUAGE = "en"
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


def _frozen_env_file() -> Path | None:
    """A .env sitting beside the executable, for the packaged build."""
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent / ".env"
        if candidate.is_file():
            return candidate
    return None


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
    poster_protocol: str = DEFAULT_POSTER_PROTOCOL
    region: str = DEFAULT_REGION
    language: str = DEFAULT_LANGUAGE
    ui_language: str = DEFAULT_UI_LANGUAGE
    offline: bool = False
    trailer_audio: bool = True
    trailer_max_cols: int = 0  # 0 = fill the pane
    # Sharpening costs almost nothing next to decoding, so it is on by
    # default; COLOMBUS_TRAILER_SHARPEN=0 gets the plain bilinear picture.
    trailer_sharpen: bool = True
    # Percent. 100 leaves the sound untouched; above that compresses the
    # trailer's wide dynamic range before boosting, so quiet dialogue
    # comes up without the already-full-scale peaks distorting.
    trailer_volume: int = 100

    @property
    def language_code(self) -> str:
        """Just the ISO 639-1 half: 'hi' from 'hi-IN'."""
        return self.language.split("-")[0].lower()

    @property
    def is_english(self) -> bool:
        return self.language_code == "en"

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
            # Beside the .exe first, then the usual walk up from the cwd.
            if beside_exe := _frozen_env_file():
                load_dotenv(beside_exe)
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
            poster_protocol=(
                os.getenv("COLOMBUS_POSTER_PROTOCOL") or DEFAULT_POSTER_PROTOCOL
            ).strip().lower(),
            region=(os.getenv("COLOMBUS_REGION") or DEFAULT_REGION).strip().upper(),
            language=(os.getenv("COLOMBUS_LANGUAGE") or DEFAULT_LANGUAGE).strip()
            or DEFAULT_LANGUAGE,
            ui_language=(os.getenv("COLOMBUS_UI_LANGUAGE") or DEFAULT_UI_LANGUAGE)
            .strip()
            .lower(),
            offline=(os.getenv("COLOMBUS_OFFLINE") or "").strip().lower()
            in ("1", "true", "yes", "on"),
            trailer_audio=(os.getenv("COLOMBUS_TRAILER_AUDIO") or "1").strip().lower()
            not in ("0", "false", "no", "off"),
            trailer_max_cols=max(0, _env_int("COLOMBUS_TRAILER_WIDTH", 0)),
            trailer_volume=max(10, min(400, _env_int("COLOMBUS_TRAILER_VOLUME", 100))),
            trailer_sharpen=(os.getenv("COLOMBUS_TRAILER_SHARPEN") or "1")
            .strip()
            .lower()
            not in ("0", "false", "no", "off"),
        )
