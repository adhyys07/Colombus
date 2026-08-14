from __future__ import annotations
import re
from dataclasses import dataclass, field

@dataclass
class SearchHit:
    tmdb_id: int
    title: str
    year: str
    overview: str
    poster_path: str | None
    popularity: float = 0.0
    vote_average: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.title} ({self.year})" if self.year else self.title

@dataclass
class Rating:
    """A single critic/aggregator score, plus a 0-100 normalisation for bars."""

    source: str
    value: str
    score: float | None = None

    @classmethod
    def parse(cls, source: str, value: str) -> "Rating":
        return cls(source=source, value=value, score=_normalise(value))

def _normalise(value: str) -> float | None:
    value = value.strip()
    if m := re.fullmatch(r"(\d+(?:\.\d+)?)\s*%", value):
        return float(m.group(1))
    if m := re.fullmatch(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", value):
        num, den = float(m.group(1)), float(m.group(2))
        return round(num / den * 100, 1) if den else None
    if m := re.fullmatch(r"(\d+(?:\.\d+)?)", value):
        return float(m.group(1))
    return None

@dataclass
class Review:
    author: str
    content: str
    rating: float | None = None
    url: str | None = None
    source: str = "TMDB"

    def excerpt(self, limit:int = 600) -> str:
        text = " ".join(self.content.split())
        return text if len(text) <= limit else text[:limit - 1].rstrip() + "..."

@dataclass
class Movie:
    tmdb_id: int
    title: str
    year: str = ""
    imdb_id: str | None = None
    tagline: str = ""
    runtime: int | None = None
    genres: list[str] = field(default_factory=list)
    director: str = ""
    writers: list[str] = field(default_factory=list)
    cast: list[str] = field(default_factory=list)
    overview: str = ""
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

    @property
    def imdb_url(self) -> str | None:
        return f"https://www.imdb.com/title/{self.imdb_id}/" if self.imdb_id else None