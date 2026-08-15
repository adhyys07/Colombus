"""TMDB: the primary source for search results, metadata and posters."""

from __future__ import annotations

import httpx

from cache import Cache
from config import Config
from models import SearchHit


class TMDBError(RuntimeError):
    """A TMDB request failed in a way the user needs to know about."""


class TMDBSource:
    BASE = "https://api.themoviedb.org/3"
    IMAGE_BASE = "https://image.tmdb.org/t/p"
    APPEND = "credits,reviews,release_dates,external_ids"

    def __init__(self, config: Config, cache: Cache, client: httpx.AsyncClient) -> None:
        self._config = config
        self._cache = cache
        self._client = client

    def _auth(self) -> tuple[dict[str, str], dict[str, str]]:
        """Bearer header for a v4 token, else an api_key query param."""
        headers = self._config.tmdb_headers
        if headers:
            return headers, {}
        return {}, {"api_key": self._config.tmdb_api_key or ""}

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
        cache_key: str | None = None,
    ) -> dict:
        if cache_key:
            cached = self._cache.get_json(cache_key)
            if cached is not None:
                return cached

        headers, auth_params = self._auth()
        try:
            response = await self._client.get(
                f"{self.BASE}{path}",
                params={**auth_params, **(params or {})},
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code == 401:
                raise TMDBError(
                    "TMDB rejected your credentials. Check TMDB_API_KEY / "
                    "TMDB_ACCESS_TOKEN in your .env file."
                ) from exc
            if code == 404:
                raise TMDBError("TMDB has no record of that title.") from exc
            if code == 429:
                raise TMDBError("TMDB rate limit reached - try again shortly.") from exc
            raise TMDBError(f"TMDB request failed (HTTP {code}).") from exc
        except httpx.HTTPError as exc:
            detail = str(exc) or type(exc).__name__
            raise TMDBError(
                f"Could not reach TMDB: {detail}\n"
                "The connection failed after retrying. If this keeps happening, "
                "raise COLOMBUS_HTTP_RETRIES in your .env, or try another "
                "network - some ISPs interfere with api.themoviedb.org."
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise TMDBError("TMDB returned a malformed response.") from exc

        if cache_key:
            self._cache.set_json(cache_key, data)
        return data

    async def search(self, query: str, limit: int = 30) -> list[SearchHit]:
        query = query.strip()
        if not query:
            return []

        data = await self._get(
            "/search/movie",
            {"query": query, "include_adult": "false"},
            cache_key=f"tmdb:search:{query.lower()}",
        )

        hits = [
            SearchHit(
                tmdb_id=row["id"],
                title=row.get("title") or row.get("original_title") or "Untitled",
                year=(row.get("release_date") or "")[:4],
                overview=row.get("overview") or "",
                poster_path=row.get("poster_path"),
                popularity=float(row.get("popularity") or 0.0),
                vote_average=float(row.get("vote_average") or 0.0),
            )
            for row in data.get("results", [])
            if row.get("id") is not None
        ]
        hits.sort(key=lambda hit: hit.popularity, reverse=True)
        return hits[:limit]

    async def movie(self, tmdb_id: int) -> dict:
        return await self._get(
            f"/movie/{tmdb_id}",
            {"append_to_response": self.APPEND},
            cache_key=f"tmdb:movie:{tmdb_id}",
        )

    async def poster(self, poster_path: str | None) -> bytes | None:
        """Poster bytes, cached on disk. Never raises — posters are optional."""
        if not poster_path:
            return None

        size = self._config.poster_size
        key = f"poster:{size}:{poster_path}"
        if cached := self._cache.get_blob(key):
            return cached

        try:
            response = await self._client.get(
                f"{self.IMAGE_BASE}/{size}{poster_path}"
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        self._cache.set_blob(key, response.content)
        return response.content
