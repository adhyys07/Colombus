"""Textual widgets composing the Colombus UI."""

from widgets.cast import CastPane, PersonItem
from widgets.episodes import EpisodesPane

from widgets.detail import DetailPane
from widgets.poster import PosterPane
from widgets.results import QueryItem, ResultItem, ResultsList
from widgets.reviews import ReviewsPane

__all__ = [
    "CastPane",
    "DetailPane",
    "EpisodesPane",
    "PersonItem",
    "QueryItem",
    "PosterPane",
    "ResultItem",
    "ResultsList",
    "ReviewsPane",
]
