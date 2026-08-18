from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from i18n import _
from models import Stats
from render import message_renderable, stats_renderable


class StatsPane(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Static(message_renderable(_("nothing_watched")), id="stats-body")

    @property
    def _body(self) -> Static:
        return self.query_one("#stats-body", Static)

    def show_stats(self, stats: Stats) -> None:
        self._body.update(stats_renderable(stats))
        self.scroll_home(animate=False)
