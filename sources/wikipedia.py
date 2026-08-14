from __future__ import annotations
from urllib.parse import quote
import httpx
from cache import Cache

API = "https://en.wikipedia.org/w/api.php"
REST = "https://en.wikipedia.org/api/rest_v1/page/summary"

class WikipediaSource:
    def __init__(self, client: httpx.AsyncClient, cache: Cache) -> None:
        self._client = client
        self._cache = cache

    async def _search_title(self, title: str, year: str) -> str | None:
        query = f"{title} ({year}) film".strip()
        key = f"wiki:search:{query.lower()}"
        if (hit := self._cache.get_json(key)) is not None:
            return hit or None
        try:
            resp = await self._client.get(
                API,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 5,
                    "format": "json",
                },
                headers={"User-Agent": "Colombus/1.0"},
            )
            resp.raise_for_status()
            results= resp.json().get("query", {}).get("search", [])
        except (httpx.HTTPError, ValueError):
            return None

        if not results:
            self._cache.set_json(key, "")
            return None

        best = next(
            (r["title"] for r in results if "film" in r["title"].lower()),
            results[0]["title"],
        )
        self._cache.set_json(key, best)
        return best

    async def summary(self, title: str, year: str = "") -> dict | None:
        page = await self._search_title(title, year)
        if not page:
            return None
        key = f"wiki:summary:{page}"
        if (hit := self._cache.get_json(key)) is not None:
            return hit or None

        try:
            resp = await self._client.get(
                REST + quote(page.replace(" ", "_"), safe=""),
                headers = {"User-Agent": "Colombus/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None
        if data.get("type") == "disambiguation":
            return None

        out = {
            "extract": data.get("extract", ""),
            "url": data.get("content_urls", {})
            .get("desktop", {})
            .get("page", f"https://en.wikipedia.org/wiki/{quote(page)}"),
            "title": data.get("title", page),
        }
        self,_cache.set_json(key, out)
        return out