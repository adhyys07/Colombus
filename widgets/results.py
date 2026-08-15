"""Left-hand list of search results."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Label, ListItem, ListView

from models import SearchHit


class ResultItem(ListItem):
    """A ListItem that remembers which SearchHit it stands for."""

    def __init__(self, hit: SearchHit) -> None:
        super().__init__(Label(self._label_text(hit)))
        self.hit = hit

    @staticmethod
    def _label_text(hit: SearchHit) -> Text:
        line = Text(hit.title, style="bold")
        if hit.year:
            line.append(f"  {hit.year}", style="dim")
        if hit.vote_average:
            line.append(f"  ★{hit.vote_average:.1f}", style="yellow")
        return line


class ResultsList(ListView):
    BORDER_TITLE = "Results"

    async def show(self, hits: list[SearchHit]) -> None:
        await self.clear()
        for hit in hits:
            await self.append(ResultItem(hit))
        if hits:
            self.index = 0

    @property
    def selected_hit(self) -> SearchHit | None:
        item = self.highlighted_child
        return getattr(item, "hit", None)
