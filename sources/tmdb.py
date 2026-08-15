"""TMDB: search, trending, categories, metadata and posters.

Movies and series share one code path; the differing field names
(title/name, release_date/first_air_date) are normalised on the way in.
"""

from __future__ import annotations

import httpx

from cache import Cache
from config import Config
from models import MOVIE, TV, Genre, SearchHit

WINDOWS = ("day", "week")


class TMDBError(RuntimeError):
    """A TMDB request failed in a way the user needs to know about."""


def _row_title(row: dict) -> str:
    return (
        row.get("title")
        or row.get("name")
        or row.get("original_title")
        or row.get("original_name")
        or "Untitled"
    )


def _row_year(row: dict) -> str:
    return (row.get("release_date") or row.get("first_air_date") or "")[:4]


class TMDBSource:
    BASE = "https://api.themoviedb.org/3"
    IMAGE_BASE = "https://image.tmdb.org/t/p"
    MOVIE_APPEND = (
        "credits,reviews,release_dates,external_ids,"
        "videos,recommendations,watch/providers"
    )
    TV_APPEND = (
        "credits,reviews,content_ratings,external_ids,"
        "videos,recommendations,watch/providers"
    )

    def __init__(self, config: Config, cache: Cache, client: httpx.AsyncClient) -> None:
        self._config = config
        self._cache = cache
        self._client = client

    def _auth(self) -> tuple[dict[str, str], dict[str, str]]:
        headers = self._config.tmdb_headers
        if headers:
            return headers, {}
        return {}, {"api_key": self._config.tmdb_api_key or ""}

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
        cache_key: str | None = None,
        language: str | None = None,
    ) -> dict:
        lang = language or self._config.language
        # Cached payloads are language-specific; without this suffix, switching
        # language would serve whatever was fetched first.
        if cache_key:
            cache_key = f"{cache_key}:{lang}"
            cached = self._cache.get_json(cache_key)
            if cached is not None:
                return cached

        headers, auth_params = self._auth()
        try:
            response = await self._client.get(
                f"{self.BASE}{path}",
                params={**auth_params, "language": lang, **(params or {})},
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

    # ------------------------------------------------------------------ lists

    def _hits(self, data: dict, media_type: str, limit: int) -> list[SearchHit]:
        hits = []
        for row in data.get("results", []):
            if row.get("id") is None:
                continue
            # /trending/all mixes in people, who have no poster or title.
            kind = row.get("media_type") if media_type == "all" else media_type
            if kind not in (MOVIE, TV):
                continue
            hits.append(
                SearchHit(
                    tmdb_id=row["id"],
                    title=_row_title(row),
                    year=_row_year(row),
                    overview=row.get("overview") or "",
                    poster_path=row.get("poster_path"),
                    popularity=float(row.get("popularity") or 0.0),
                    vote_average=float(row.get("vote_average") or 0.0),
                    media_type=kind,
                )
            )
        hits.sort(key=lambda hit: hit.popularity, reverse=True)
        return hits[:limit]

    async def search(
        self, query: str, media_type: str = MOVIE, limit: int = 30
    ) -> list[SearchHit]:
        query = query.strip()
        if not query:
            return []
        path = "/search/multi" if media_type == "all" else f"/search/{media_type}"
        data = await self._get(
            path,
            {"query": query, "include_adult": "false"},
            cache_key=f"tmdb:search:{media_type}:{query.lower()}",
        )
        return self._hits(data, media_type, limit)

    async def trending(
        self, media_type: str = MOVIE, window: str = "week", limit: int = 30
    ) -> list[SearchHit]:
        if window not in WINDOWS:
            window = "week"
        data = await self._get(
            f"/trending/{media_type}/{window}",
            cache_key=f"tmdb:trending:{media_type}:{window}",
        )
        return self._hits(data, media_type, limit)

    async def genres(self, media_type: str = MOVIE) -> list[Genre]:
        if media_type not in (MOVIE, TV):
            media_type = MOVIE
        data = await self._get(
            f"/genre/{media_type}/list", cache_key=f"tmdb:genres:{media_type}"
        )
        return [
            Genre(tmdb_id=row["id"], name=row["name"], media_type=media_type)
            for row in data.get("genres", [])
            if row.get("id") is not None and row.get("name")
        ]

    async def discover(
        self,
        media_type: str,
        genre_id: int | None = None,
        original_language: str = "",
        limit: int = 30,
    ) -> list[SearchHit]:
        if media_type not in (MOVIE, TV):
            media_type = MOVIE
        params = {"sort_by": "popularity.desc"}
        if genre_id:
            params["with_genres"] = str(genre_id)
        if original_language:
            params["with_original_language"] = original_language
        data = await self._get(
            f"/discover/{media_type}",
            params,
            cache_key=(
                f"tmdb:discover:{media_type}:"
                f"{genre_id or 'any'}:{original_language or 'any'}"
            ),
        )
        return self._hits(data, media_type, limit)

    async def person_credits(self, person_id: int, limit: int = 40) -> list[SearchHit]:
        data = await self._get(
            f"/person/{person_id}/combined_credits",
            cache_key=f"tmdb:person:{person_id}",
        )
        rows = list(data.get("cast") or []) + list(data.get("crew") or [])
        deduped: dict[tuple[int, str], dict] = {}
        for row in rows:
            key = (row.get("id"), row.get("media_type"))
            if key[0] is not None and key not in deduped:
                deduped[key] = row
        return self._hits({"results": list(deduped.values())}, "all", limit)

    async def season(self, tv_id: int, season_number: int) -> dict:
        return await self._get(
            f"/tv/{tv_id}/season/{season_number}",
            cache_key=f"tmdb:season:{tv_id}:{season_number}",
        )

    async def english_text(self, media_type: str, tmdb_id: int) -> tuple[str, str]:
        """(overview, tagline) in English, for filling gaps in a translation."""
        data = await self._get(
            f"/{media_type}/{tmdb_id}",
            cache_key=f"tmdb:en:{media_type}:{tmdb_id}",
            language="en-US",
        )
        return data.get("overview") or "", data.get("tagline") or ""

    # --------------------------------------------------------------- details

    async def title(self, media_type: str, tmdb_id: int) -> dict:
        if media_type not in (MOVIE, TV):
            media_type = MOVIE
        append = self.TV_APPEND if media_type == TV else self.MOVIE_APPEND
        return await self._get(
            f"/{media_type}/{tmdb_id}",
            {"append_to_response": append},
            cache_key=f"tmdb:v2:{media_type}:{tmdb_id}",
        )

    async def poster(self, poster_path: str | None) -> bytes | None:
        """Poster bytes, cached on disk. Never raises - posters are optional."""
        if not poster_path:
            return None

        size = self._config.poster_size
        key = f"poster:{size}:{poster_path}"
        if cached := self._cache.get_blob(key):
            return cached

        try:
            response = await self._client.get(f"{self.IMAGE_BASE}/{size}{poster_path}")
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        self._cache.set_blob(key, response.content)
        return response.content