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
        if hit.is_series:
            line.append("  TV", style="cyan")
        if hit.vote_average:
            line.append(f"  ★{hit.vote_average:.1f}", style="yellow")
        return line


class QueryItem(ListItem):
    """A remembered search; selecting it re-runs the query."""

    def __init__(self, query: str) -> None:
        super().__init__(Label(Text(query, style="italic")))
        self.query = query


class ResultsList(ListView):
    BORDER_TITLE = "Results"

    async def show(self, hits: list[SearchHit]) -> None:
        await self.clear()
        for hit in hits:
            await self.append(ResultItem(hit))
        if hits:
            self.index = 0

    async def show_queries(self, queries: list[str]) -> None:
        await self.clear()
        for query in queries:
            await self.append(QueryItem(query))
        if queries:
            self.index = 0

    @property
    def selected_hit(self) -> SearchHit | None:
        item = self.highlighted_child
        return getattr(item, "hit", None)
