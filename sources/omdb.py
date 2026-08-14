from __future__ import annotations
import httpx
from cache import Cache
from models import Rating

BASE = "http://www.omdbapi.com"

_SOURCE_LABELS = {
    "Internet Movie Database": "IMDb",
    "Rotten Tomatoes": "Rotten Tomatoes",
    "Metacritic": "Metacritic",
}

class OMDBSource:   
    def __init__(
            self, client: httpx.AsyncClient, cache: Cache, api_key: str | None
    ) -> None:
        self._client = client
        self._cache = cache
        self._api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def by_imdb_id(self, imdb_id: str) -> dict | None:
        if not (self.enabled and imdb_id):
            return None

        key = f"omdb:{imdb_id}"
        if (hit := self._cache.get_json(key)) is not None:
            return hit
        try:
            resp = await self._client.get(
                  BASE, params={"apikey": self._api_key, "i": imdb_id, "plot": "short"}
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None

    async def ratings(self, imdb_id: str) -> list[Rating]:
        data = await self.by_imdb_id(imdb_id)
        if not data:
            return []

        out: list[Rating] = []
        for entry in data.get("Ratings", []):
            source = entry.get("Source", "")
            value = entry.get("Value", "")
            if not (source and value):
                continue
            out.append(Rating.parse(_SOURCE_LABELS.get(source, source), value))

        have = {r.source for r in out}
        meta = data.get("Metascore")
        if "Metacritic" not in have and meta and meta != "N/A":
            out.append(Rating.parse("Metacritic", f"{meta}/100"))

        return out

    async def extras(self, imdb_id: str) -> dict[str, str]:
        data = await self.by_imdb_id(imdb_id)
        if not data:
            return {}
        return {
            k: v
            for k,v in {
                "plot": data.get("Plot", ""),
                "poster_url": data.get("Poster"),
                "languages": [l.strip() for l in data.get("Language", "").split(",")],
                "countries": [c.strip() for c in data.get("Country", "").split(",")],
                "certificate": data.get("Rated", ""),
            }.items()
            if v and v != "N/A"
        }