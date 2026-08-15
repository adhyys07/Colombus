"""OMDb: supplies the IMDb / Rotten Tomatoes / Metacritic score line.

Entirely optional. Every failure degrades to "no extra ratings" rather than
raising, so a missing or throttled OMDb key never blocks a detail view.
"""

from __future__ import annotations

import httpx

from cache import Cache
from config import Config
from models import Rating


class OMDBSource:
    BASE = "https://www.omdbapi.com/"

    def __init__(self, config: Config, cache: Cache, client: httpx.AsyncClient) -> None:
        self._config = config
        self._cache = cache
        self._client = client
        self.auth_failed = False
        """Set when OMDb rejects the key, so the UI can say so once."""

    async def fetch(self, imdb_id: str | None) -> dict | None:
        if not (self._config.has_omdb and imdb_id):
            return None

        cache_key = f"omdb:{imdb_id}"
        if (cached := self._cache.get_json(cache_key)) is not None:
            return cached

        try:
            response = await self._client.get(
                self.BASE,
                params={"i": imdb_id, "apikey": self._config.omdb_api_key or ""},
            )
            data = response.json()
            response.raise_for_status()
        except httpx.HTTPStatusError:
            pass  # OMDb returns 401 with a JSON body; inspect it below.
        except (httpx.HTTPError, ValueError):
            return None

        # OMDb signals errors in-band, and 401s with a JSON body.
        if str(data.get("Response", "")).lower() != "true":
            if "key" in str(data.get("Error", "")).lower():
                self.auth_failed = True
            return None

        self._cache.set_json(cache_key, data)
        return data

    async def ratings(self, imdb_id: str | None) -> tuple[list[Rating], str]:
        """Returns (ratings, certificate). Both empty when OMDb is unavailable."""
        data = await self.fetch(imdb_id)
        if not data:
            return [], ""

        ratings = [
            Rating.parse(entry["Source"], entry["Value"])
            for entry in data.get("Ratings", [])
            if entry.get("Source") and entry.get("Value")
        ]

        certificate = data.get("Rated") or ""
        if certificate in {"N/A", "Not Rated", "Unrated"}:
            certificate = ""
        return ratings, certificate
