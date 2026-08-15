"""Wikipedia: a plot/background extract for the detail pane.

Optional enrichment — every failure returns empty strings rather than raising.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from cache import Cache


class WikipediaSource:
    API = "https://en.wikipedia.org/w/api.php"
    SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"

    def __init__(self, cache: Cache, client: httpx.AsyncClient) -> None:
        self._cache = cache
        self._client = client

    async def _find_page(
        self, title: str, year: str, series: bool = False
    ) -> str | None:
        kind = "TV series" if series else "film"
        term = f"{title} {year} {kind}".strip()
        try:
            response = await self._client.get(
                self.API,
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": term,
                    "srlimit": "5",
                    "format": "json",
                },
            )
            response.raise_for_status()
            results = response.json()["query"]["search"]
        except (httpx.HTTPError, ValueError, KeyError):
            return None

        if not results:
            return None

        # Prefer a page disambiguated as a film or series over a same-named
        # novel or album.
        wanted = ("tv series", "series") if series else ("film",)
        for row in results:
            name = row.get("title", "")
            if any(token in name.lower() for token in wanted):
                return name
        return results[0].get("title")

    async def summary(
        self, title: str, year: str = "", series: bool = False
    ) -> tuple[str, str]:
        """Returns (extract, url), or ("", "") when nothing usable is found."""
        if not title:
            return "", ""

        kind = "tv" if series else "movie"
        cache_key = f"wiki:{kind}:{title.lower()}:{year}"
        if (cached := self._cache.get_json(cache_key)) is not None:
            return cached.get("extract", ""), cached.get("url", "")

        page = await self._find_page(title, year, series)
        if not page:
            return "", ""

        try:
            response = await self._client.get(
                f"{self.SUMMARY}{quote(page.replace(' ', '_'), safe='')}"
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            return "", ""

        if data.get("type") == "disambiguation":
            return "", ""

        extract = data.get("extract") or ""
        url = (
            data.get("content_urls", {}).get("desktop", {}).get("page")
            or f"https://en.wikipedia.org/wiki/{quote(page.replace(' ', '_'), safe='')}"
        )

        if extract:
            self._cache.set_json(cache_key, {"extract": extract, "url": url})
        return extract, url
