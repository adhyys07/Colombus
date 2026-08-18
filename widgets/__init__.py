"""Textual widgets composing the Colombus UI."""

from widgets.cast import CastPane, PersonItem
from widgets.episodes import EpisodesPane

from widgets.detail import DetailPane
from widgets.poster import PosterPane
from widgets.player import PlayerPane
from widgets.stats import StatsPane
from widgets.results import PersonResult, QueryItem, ResultItem, ResultsList
from widgets.reviews import ReviewsPane

__all__ = [
    "CastPane",
    "DetailPane",
    "EpisodesPane",
    "PersonItem",
    "PersonResult",
    "PlayerPane",
    "QueryItem",
    "PosterPane",
    "ResultItem",
    "ResultsList",
    "ReviewsPane",
    "StatsPane",
]
