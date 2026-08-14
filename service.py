from __future__ import annotations
import asyncio
import httpx
from cache import Cache
from config import Config
from models import Movie, Rating, Review, SearchHit
from sources import OMDBSource, TMDBSource, WikipediaSource

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

class MovieService:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._cache = Cache(config.cache_dir, ttl=config.cache_ttl)
        self._client = httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=True,
            limits = httpx.Limits(max_connections=10),
            headers = {"Accept": "application/json"},
        )
        self._tmdb = TMDBSource(
            self._client,
            self.cache,
            api_key=config.tmdb_api_key,
            access_token=config.tmdb_access_token,
            poster_size=config.poster_size,
        )
        self._omdb = OMDBSource(self._client, self.cache, api_key=config.omdb_api_key)
        self._wiki = WikipediaSource(self._client, self.cache)

    async def search(self, query: str, limit: int = 25) -> list[SearchHit]:
        return await self.tmdb.search(query, limit=limit)

    async def get_movie(self, tmdb_id: int) -> Movie:
        raw = await self.tmdb.details(tmdb_id)
        movie = self._map_tmdb(raw)
        ratings_task = (
            self.omdb.ratings(movie.imdb_id)
            if movie.imdb_id
            else _noop([])
        )
        wiki_task = self.wiki.summary(movie.title, movie.year)

        ratings, wiki = await asyncio.gather(ratings_task, wiki_task, return_exceptions=True)

        if isinstance(ratings, list):
            movie.ratings= ratings
        if isinstance(wiki, dict) and wiki:
            movie.wiki_extract = wiki.get("extract", "")
            movie.wiki_url = wiki.get("url","")

        if raw.get("vote_average"):
            movie.ratings.append(
                Rating.parse(
                    f"TMDB users ({raw.get('vote_count', 0):,})",
                    f"{raw['vote_average']:.1f}/10",
                )
            )
        return movie
    
    async def poster(self, movie:Movie) -> bytes | None:
        return await self.tmdb.poster_bytes(movie.poster_url) if movie.poster_url else None

    async def poster_for_hit(self, hit: SearchHit) -> bytes | None:
        url = self.tmdb.poster_url(hit.poster_path)
        return await self.tmdb.poster_bytes(url) if url else None

    async def aclose(self) -> None:
        await self._client.aclose()
        self.cache.close()

    def _map_tmdb(self, raw: dict) -> Movie:
        credits = raw.get("credits", {}) or {}
        crew = credits.get("crew", []) or []

        directors = [c["name"] for c in crew if c.get("job") == "Director"]
        writers = [
            c["name"]
            for c in crew
            if c.get("job") in ("Writer", "Screenplay", "Story")
        ]

        movie= Movie(
             tmdb_id=raw["id"],
            title=raw.get("title") or raw.get("original_title", "Untitled"),
            year=(raw.get("release_date") or "")[:4],
            imdb_id=raw.get("imdb_id")
            or (raw.get("external_ids", {}) or {}).get("imdb_id"),
            tagline=raw.get("tagline", "") or "",
            runtime=raw.get("runtime") or None,
            genres=[g["name"] for g in raw.get("genres", [])],
            director=", ".join(dict.fromkeys(directors)),
            writers=list(dict.fromkeys(writers))[:4],
            cast=[c["name"] for c in (credits.get("cast") or [])[:8]],
            overview=raw.get("overview", "") or "",
            poster_url=self.tmdb.poster_url(raw.get("poster_path")),
            budget=raw.get("budget", 0) or 0,
            revenue=raw.get("revenue", 0) or 0,
            languages=[
                l.get("english_name", l.get("name", ""))
                for l in raw.get("spoken_languages", [])
            ],
            countries=[c.get("name", "") for c in raw.get("production_countries", [])],
            certification=_us_certification(raw),
        )

        movie.reviews = [
            Review(
                author=r.get("author", "anonymous"),
                content=r.get("content", ""),
                rating=r.get("author_details" or {}).get("rating"),
                url=r.get("url"),
            )
            for r in (raw.get("reviews", {}) or {}).get("results", [])
            if r.get("content")
        ][:6]

        return movie

    def _us_certification(raw: dict) -> str:
        for entry in (raw.get("release_dates", {}) or {}).get("results", []):
            if entry.get("iso_3166_1") != "US":
                continue
            for rd in entry.get("release_dates", []):
                    if rd.get("certification"):
                        return rd["certification"]
        return ""

    async def _noop(value):
        return value