"""Pane that plays a trailer as terminal art."""

from __future__ import annotations

from rich.console import RenderableType
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from i18n import _
from render import message_renderable

# Cost scales with cell count: the renderer manages ~56fps at 50x16 but
# only ~10fps at 100x32, so the grid is capped rather than filling the pane.
MAX_COLS = 60
MAX_ROWS = 20


class PlayerPane(Container):
    def compose(self) -> ComposeResult:
        yield Static(message_renderable(_("trailer_idle")), id="player-body")

    @property
    def _body(self) -> Static:
        return self.query_one("#player-body", Static)

    def grid(self) -> tuple[int, int]:
        """Frame size to render at, capped for speed and never zero."""
        cols = min(MAX_COLS, max(20, self.size.width - 2))
        rows = min(MAX_ROWS, max(8, self.size.height - 2))
        return cols, rows

    def show_frame(self, frame: RenderableType) -> None:
        self._body.update(frame)

    def show_message(self, text: str, style: str = "dim") -> None:
        self._body.update(message_renderable(text, style))
