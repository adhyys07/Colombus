"""Scrollable pane holding every review for the selected title."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from models import Movie
from render import message_renderable, reviews_renderable


class ReviewsPane(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Static(
            message_renderable("Pick a title to read its reviews."), id="reviews-body"
        )

    @property
    def _body(self) -> Static:
        return self.query_one("#reviews-body", Static)

    def show_movie(self, movie: Movie) -> None:
        self._body.update(reviews_renderable(movie))
        self.scroll_home(animate=False)

    def show_message(self, text: str, style: str = "dim") -> None:
        self._body.update(message_renderable(text, style))
        self.scroll_home(animate=False)
