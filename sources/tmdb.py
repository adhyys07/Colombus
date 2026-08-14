from __future__ import annotations
import httpx
from cache import Cache
from models import SearchHit

BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"

class TMDBSource:
    def __init__(
            self,
            client: httpx.AsyncClient,
            cache: Cache,
            *,
            api_key: str | None = None,
            access_token: str | None = None,
            poster_size: str = "w342",
    ) -> None:
        if not(api_key or access_token):
            raise ValueError("TMDB API key or access token is required")
        self._client = client
        self._cache = cache
        self._api_key = api_key
        self._access_token = access_token
        self._poster_size = poster_size

    @property
    def _headers(self) -> dict[str, str]:
        if self._access_token:
            return {"Authorization": f"Bearer {self._access_token}"}
        return {}

    def _auth_params(self, params:dict) -> dict:
        if not self._access_token and self._api_key:
            params = {**params, "api_key": self._api_key}
        return params

    async def _get(self, path:str, cache_key:str, **params) -> dict:
        if (hit := self._cache.get_json(cache_key)) is not None:
            return hit
        resp = await self._client.get(
            f"{BASE}/{path}",
            headers=self._headers,
            params=self._auth_params(params),
        )
        resp.raise_for_status()
        data = resp.json()
        self._cache.set_json(cache_key, data)
        return data

    async def search(self, query:str, limit: int = 25) -> list[SearchHit]:
        query = query.strip()
        if not query:
            return []
        data = await self._get(
            "/search/movie",
            f"tmdb:search:{query.lower()}",
            query=query,
            include_adult=False,
            language="en-US",
            page=1,
        )
        hits = [
            SearchHit(
                tmdb_id=r["id"],
                title=r.get("title") or r.get("original_title", "Untitled"),
                year=(r.get("release_date") or "")[:4],
                overview=r.get("overview", ""),
                poster_path=r.get("poster_path"),
                popularity=r.get("popularity", 0.0),
                vote_average=r.get("vote_average", 0.0),
            )
            for r in data.get("results", [])
        ]
        lowered = query.lower()
        hits.sort(key = lambda h: (h.title.lower() != lowered, -h.popularity))
        return hits[:limit]

    async def details(self, tmdb_id:int) -> dict:
        return await self._get(
            f"/movie/{tmdb_id}",
            f"tmdb:details:{tmdb_id}",
            language="en-US",
            append_to_response="credits,reviews,external_ids,release_dates",
        )
    
    def poster_url(self, poster_path:str | None, size:str | None = None) -> str | None:
        if not poster_path:
            return None
        return f"{IMAGE_BASE}/{size or self.poster_size}{poster_path}"

    async def poster_bytes(self, url: str) -> bytes | None:
        if (blob := self._cache.get_blob(url)) is not None:
            return blob
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        self._cache.set_blob(url, resp.content)
        return resp.content