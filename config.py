from __future__ import annotations
import os 
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **_kwargs) -> bool:
        return False

class ConfigError(RuntimeError):
    """Raised when required credentials are missing."""


@dataclass(frozen=True)
class Config:
    tmdb_api_key: str | None
    tmdb_access_token: str | None
    omdb_api_key: str | None
    cache_dir: Path
    cache_ttl: int
    poster_size: str

    @property
    def has_omdb(self) -> bool:
        return bool(self.omdb_api_key)

    @classmethod
    def load(cls, env_file: str | os.PathLike | None = None) -> Config:
        load_dotenv(env_file) if env_file else load_dotenv()

        tmdb_key = os.getenv("TMDB_API_KEY") or None
        tmdb_token = os.getenv("TMDB_ACCESS_TOKEN") or None
        if not (tmdb_key or tmdb_token):
            raise ConfigError(
                raise ConfigError(
                "No TMDB credentials found.\n"
                "Set TMDB_API_KEY (v3) or TMDB_ACCESS_TOKEN (v4) in your "
                "environment or a .env file.\n"
                "Get one free at https://www.themoviedb.org/settings/api"
                )

            cache_dir = Path(os.getenv("CACHE_DIR", ".cache")).expanduser()
            ).expanduser()
        return cls(
            tmdb_api_key=tmdb_key,
            tmdb_access_token=tmdb_token,
            omdb_api_key=os.getenv("OMDB_API_KEY") or None,
            cache_dir=cache_dir,
            cache_ttl=int(os.getenv("COLOMBUS_CACHE_TTL", 7 * 24 * 3600)),
            poster_size=os.getenv("COLOMBUS_POSTER_SIZE", "w342"),
        )