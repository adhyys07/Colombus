"""Scrollable pane holding the rendered movie detail."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from models import Movie
from render import message_renderable, movie_renderable


class DetailPane(VerticalScroll):
    BORDER_TITLE = "Details"

    def compose(self) -> ComposeResult:
        yield Static(message_renderable("Search for a film to begin."), id="detail-body")

    @property
    def _body(self) -> Static:
        return self.query_one("#detail-body", Static)

    def show_movie(self, movie: Movie) -> None:
        self._body.update(movie_renderable(movie))
        self.scroll_home(animate=False)

    def show_message(self, text: str, style: str = "dim") -> None:
        self._body.update(message_renderable(text, style))
        self.scroll_home(animate=False)
