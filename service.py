"""Fans one lookup across TMDB, OMDb and Wikipedia into a single Movie."""

from __future__ import annotations

import asyncio

import httpx

from cache import Cache
from config import Config
from models import MOVIE, TV, Genre, Movie, Rating, Review, SearchHit
from sources import OMDBSource, TMDBSource, WikipediaSource

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
        # Establishing the connection is the fragile step on some networks;
        # once a connection is up it is reused for the rest of the session.
        transport = httpx.AsyncHTTPTransport(retries=config.http_retries)
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": config.user_agent},
            follow_redirects=True,
            transport=transport,
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

    # ------------------------------------------------------------------ lists

    async def search(self, query: str, media_type: str = MOVIE) -> list[SearchHit]:
        return await self.tmdb.search(query, media_type)

    async def trending(
        self, media_type: str = MOVIE, window: str = "week"
    ) -> list[SearchHit]:
        return await self.tmdb.trending(media_type, window)

    async def genres(self, media_type: str = MOVIE) -> list[Genre]:
        return await self.tmdb.genres(media_type)

    async def by_genre(self, media_type: str, genre_id: int) -> list[SearchHit]:
        return await self.tmdb.discover(media_type, genre_id)

    # ---------------------------------------------------------------- details

    async def details(self, tmdb_id: int, media_type: str = MOVIE) -> Movie:
        """TMDB is required; OMDb and Wikipedia enrich it opportunistically."""
        payload = await self.tmdb.title(media_type, tmdb_id)
        movie = self._build(payload, media_type)

        extras = await asyncio.gather(
            self.omdb.ratings(movie.imdb_id),
            self.wiki.summary(movie.title, movie.year, series=movie.is_series),
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

    # ---------------------------------------------------------------- mapping

    def _build(self, payload: dict, media_type: str) -> Movie:
        is_tv = media_type == TV
        credits = payload.get("credits") or {}
        crew = credits.get("crew") or []

        if is_tv:
            # Series credit a creator rather than a single director.
            directors = [
                person["name"]
                for person in payload.get("created_by", [])
                if person.get("name")
            ]
        else:
            directors = [
                c["name"] for c in crew if c.get("job") == "Director" and c.get("name")
            ]

        writers: list[str] = []
        for member in crew:
            name = member.get("name")
            if member.get("job") in WRITER_JOBS and name and name not in writers:
                writers.append(name)

        runtime = payload.get("runtime")
        if is_tv:
            episode_runtimes = payload.get("episode_run_time") or []
            runtime = episode_runtimes[0] if episode_runtimes else None

        poster_path = payload.get("poster_path")
        ratings: list[Rating] = []
        if vote := float(payload.get("vote_average") or 0.0):
            ratings.append(Rating.parse("TMDB", f"{vote:.1f}/10"))

        countries = [
            c.get("name", "") for c in payload.get("production_countries", [])
        ] or list(payload.get("origin_country") or [])

        return Movie(
            tmdb_id=payload["id"],
            title=(
                payload.get("title")
                or payload.get("name")
                or payload.get("original_title")
                or payload.get("original_name")
                or "Untitled"
            ),
            year=(payload.get("release_date") or payload.get("first_air_date") or "")[
                :4
            ],
            media_type=TV if is_tv else MOVIE,
            imdb_id=payload.get("imdb_id")
            or (payload.get("external_ids") or {}).get("imdb_id"),
            tagline=payload.get("tagline") or "",
            runtime=runtime or None,
            genres=[g["name"] for g in payload.get("genres", []) if g.get("name")],
            director=", ".join(directors),
            writers=writers[:4],
            cast=[
                c["name"]
                for c in (credits.get("cast") or [])[:CAST_LIMIT]
                if c.get("name")
            ],
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
            countries=countries,
            certificate=self._certificate(payload, is_tv),
            seasons=payload.get("number_of_seasons") if is_tv else None,
            episodes=payload.get("number_of_episodes") if is_tv else None,
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
                created_at=row.get("created_at") or "",
            )
            for row in rows
            if row.get("content")
        ]

    @staticmethod
    def _certificate(payload: dict, is_tv: bool) -> str:
        if is_tv:
            # Series expose content_ratings instead of release_dates.
            for entry in (payload.get("content_ratings") or {}).get("results") or []:
                rating = (entry.get("rating") or "").strip()
                if entry.get("iso_3166_1") == "US" and rating:
                    return rating
            return ""

        for entry in (payload.get("release_dates") or {}).get("results") or []:
            if entry.get("iso_3166_1") != "US":
                continue
            for release in entry.get("release_dates", []):
                if certification := (release.get("certification") or "").strip():
                    return certification
        return ""
