"""Season picker plus the episode list for a series."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Select, Static

from i18n import _
from models import Season
from render import episodes_renderable, message_renderable


class EpisodesPane(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Select([], prompt=_("season_prompt"), id="season")
        yield Static(
            message_renderable(_("pick_series_episodes")), id="episodes-body"
        )

    @property
    def _body(self) -> Static:
        return self.query_one("#episodes-body", Static)

    def set_seasons(self, numbers: list[int]) -> None:
        """Populates the picker. Returns nothing; the app reacts to Changed."""
        select = self.query_one("#season", Select)
        select.set_options([(f"{_('seasons')} {n}", n) for n in numbers])
        if numbers:
            select.value = numbers[0]

    def clear_seasons(self) -> None:
        self.query_one("#season", Select).set_options([])

    def show_season(self, season: Season) -> None:
        self._body.update(episodes_renderable(season))
        self.scroll_home(animate=False)

    def show_message(self, text: str, style: str = "dim") -> None:
        self._body.update(message_renderable(text, style))
        self.scroll_home(animate=False)
