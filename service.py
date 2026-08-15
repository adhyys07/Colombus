"""Fans one query out across TMDB, OMDb and Wikipedia into a single Movie."""

from __future__ import annotations

import asyncio

import httpx

from cache import Cache
from config import Config
from models import Movie, Rating, Review, SearchHit
from sources import OMDBSource, TMDBSource, WikipediaSource

USER_AGENT = "Colombus/0.1 (terminal movie browser)"
WRITER_JOBS = {"Writer", "Screenplay", "Story", "Screenstory", "Author"}
CAST_LIMIT = 12


class MovieService:
    def __init__(
        self,
        config: Config,
        cache: Cache | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.cache = cache or Cache(config.cache_dir, config.cache_ttl)
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        self.tmdb = TMDBSource(config, self.cache, self._client)
        self.omdb = OMDBSource(config, self.cache, self._client)
        self.wiki = WikipediaSource(self.cache, self._client)

    async def __aenter__(self) -> MovieService:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()
        self.cache.close()

    def purge_cache(self) -> None:
        self.cache.purge()

    async def search(self, query: str) -> list[SearchHit]:
        return await self.tmdb.search(query)

    async def details(self, tmdb_id: int) -> Movie:
        """TMDB is required; OMDb and Wikipedia enrich it opportunistically."""
        movie = self._build(await self.tmdb.movie(tmdb_id))

        extras = await asyncio.gather(
            self.omdb.ratings(movie.imdb_id),
            self.wiki.summary(movie.title, movie.year),
            return_exceptions=True,
        )
        omdb_result, wiki_result = extras

        if not isinstance(omdb_result, BaseException):
            ratings, certificate = omdb_result
            movie.ratings.extend(ratings)
            if certificate and not movie.certificate:
                movie.certificate = certificate

        if not isinstance(wiki_result, BaseException):
            movie.wiki_extract, movie.wiki_url = wiki_result

        return movie

    async def poster(self, poster_path: str | None) -> bytes | None:
        return await self.tmdb.poster(poster_path)

    def _build(self, payload: dict) -> Movie:
        credits = payload.get("credits") or {}
        crew = credits.get("crew") or []

        directors = [c["name"] for c in crew if c.get("job") == "Director" and c.get("name")]
        writers: list[str] = []
        for member in crew:
            if member.get("job") in WRITER_JOBS and member.get("name") not in writers:
                if member.get("name"):
                    writers.append(member["name"])

        poster_path = payload.get("poster_path")
        ratings: list[Rating] = []
        if vote := float(payload.get("vote_average") or 0.0):
            ratings.append(Rating.parse("TMDB", f"{vote:.1f}/10"))

        return Movie(
            tmdb_id=payload["id"],
            title=payload.get("title") or payload.get("original_title") or "Untitled",
            year=(payload.get("release_date") or "")[:4],
            imdb_id=payload.get("imdb_id")
            or (payload.get("external_ids") or {}).get("imdb_id"),
            tagline=payload.get("tagline") or "",
            runtime=payload.get("runtime") or None,
            genres=[g["name"] for g in payload.get("genres", []) if g.get("name")],
            director=", ".join(directors),
            writers=writers[:4],
            cast=[c["name"] for c in (credits.get("cast") or [])[:CAST_LIMIT] if c.get("name")],
            overview=payload.get("overview") or "",
            poster_path=poster_path,
            poster_url=(
                f"{TMDBSource.IMAGE_BASE}/{self.config.poster_size}{poster_path}"
                if poster_path
                else None
            ),
            ratings=ratings,
            reviews=self._reviews(payload),
            budget=int(payload.get("budget") or 0),
            revenue=int(payload.get("revenue") or 0),
            languages=[
                lang.get("english_name") or lang.get("name", "")
                for lang in payload.get("spoken_languages", [])
            ],
            countries=[
                c.get("name", "") for c in payload.get("production_countries", [])
            ],
            certificate=self._certificate(payload),
        )

    @staticmethod
    def _reviews(payload: dict) -> list[Review]:
        rows = (payload.get("reviews") or {}).get("results") or []
        return [
            Review(
                author=row.get("author") or "Anonymous",
                content=row.get("content") or "",
                rating=(row.get("author_details") or {}).get("rating"),
                url=row.get("url"),
            )
            for row in rows
            if row.get("content")
        ]

    @staticmethod
    def _certificate(payload: dict) -> str:
        results = (payload.get("release_dates") or {}).get("results") or []
        for entry in results:
            if entry.get("iso_3166_1") != "US":
                continue
            for release in entry.get("release_dates", []):
                if certification := (release.get("certification") or "").strip():
                    return certification
        return ""
