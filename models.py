from __future__ import annotations

import re
from dataclasses import dataclass, field


MOVIE = "movie"
TV = "tv"


@dataclass
class SearchHit:
    tmdb_id: int
    title: str
    year: str
    overview: str
    poster_path: str | None
    popularity: float = 0.0
    vote_average: float = 0.0
    media_type: str = MOVIE

    @property
    def label(self) -> str:
        return f"{self.title} ({self.year})" if self.year else self.title

    @property
    def is_series(self) -> bool:
        return self.media_type == TV


@dataclass
class Rating:
    """A single critic/aggregator score, plus a 0-100 normalisation for bars."""

    source: str
    value: str
    score: float | None = None

    @classmethod
    def parse(cls, source: str, value: str) -> Rating:
        return cls(source=source, value=value, score=_normalise(value))


def _clamp(score: float) -> float:
    """Keep scores inside the 0-100 range the bars are drawn against."""
    return min(100.0, max(0.0, score))


def _normalise(value: str) -> float | None:
    value = value.strip()
    if m := re.fullmatch(r"(\d+(?:\.\d+)?)\s*%", value):
        return _clamp(float(m.group(1)))
    if m := re.fullmatch(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", value):
        num, den = float(m.group(1)), float(m.group(2))
        return _clamp(round(num / den * 100, 1)) if den else None
    if m := re.fullmatch(r"(\d+(?:\.\d+)?)", value):
        # A bare number is either a 0-10 score (TMDB) or a 0-100 one
        # (Metacritic). Assume 0-10 at or below 10; "10" reads as 100.
        score = float(m.group(1))
        return _clamp(score * 10 if score <= 10 else score)
    return None


@dataclass
class Review:
    author: str
    content: str
    rating: float | None = None
    url: str | None = None
    source: str = "TMDB"
    created_at: str = ""

    @property
    def date(self) -> str:
        """Just the calendar day from TMDB's ISO timestamp."""
        return self.created_at[:10]

    def excerpt(self, limit: int = 600) -> str:
        """Whitespace-collapsed content, never longer than `limit` characters."""
        text = " ".join(self.content.split())
        if len(text) <= limit:
            return text
        if limit <= 3:
            return text[: max(limit, 0)]
        return text[: limit - 3].rstrip() + "..."


@dataclass
class Person:
    tmdb_id: int
    name: str
    role: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} ({self.role})" if self.role else self.name


@dataclass
class Provider:
    name: str
    kind: str  # flatrate | free | ads | rent | buy


@dataclass
class Video:
    name: str
    key: str
    kind: str = "Trailer"
    site: str = "YouTube"

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.key}"


@dataclass
class Episode:
    number: int
    name: str
    overview: str = ""
    air_date: str = ""
    runtime: int | None = None
    vote_average: float = 0.0

@dataclass
class Season:
    number: int
    name: str = ""
    episodes: list[Episode] = field(default_factory=list)


@dataclass
class Genre:
    """A TMDB category, used to populate the Categories tab."""

    tmdb_id: int
    name: str
    media_type: str = MOVIE


@dataclass
class Movie:
    """A movie or a series; `media_type` says which."""

    tmdb_id: int
    title: str
    year: str = ""
    media_type: str = MOVIE
    imdb_id: str | None = None
    tagline: str = ""
    runtime: int | None = None
    genres: list[str] = field(default_factory=list)
    director: str = ""
    writers: list[str] = field(default_factory=list)
    cast: list[Person] = field(default_factory=list)
    providers: list[Provider] = field(default_factory=list)
    provider_link: str = ""
    videos: list[Video] = field(default_factory=list)
    recommendations: list[SearchHit] = field(default_factory=list)
    season_numbers: list[int] = field(default_factory=list)
    overview: str = ""
    poster_path: str | None = None
    poster_url: str | None = None
    ratings: list[Rating] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    wiki_extract: str = ""
    wiki_url: str = ""
    budget: int = 0
    revenue: int = 0
    languages: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    certificate: str = ""
    seasons: int | None = None
    episodes: int | None = None

    @property
    def is_series(self) -> bool:
        return self.media_type == TV

    @property
    def imdb_url(self) -> str | None:
        return f"https://www.imdb.com/title/{self.imdb_id}/" if self.imdb_id else None

    @property
    def label(self) -> str:
        return f"{self.title} ({self.year})" if self.year else self.title

    @property
    def trailer(self) -> Video | None:
        for video in self.videos:
            if video.kind == "Trailer":
                return video
        return self.videos[0] if self.videos else None

    @property
    def tmdb_url(self) -> str:
        return f"https://www.themoviedb.org/{self.media_type}/{self.tmdb_id}"

    def providers_of(self, *kinds: str) -> list[str]:
        seen: list[str] = []
        for provider in self.providers:
            if provider.kind in kinds and provider.name not in seen:
                seen.append(provider.name)
        return seen

