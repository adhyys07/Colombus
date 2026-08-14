from __future__ import annotations
from rich.text import Text
from textual.widgets import Label, ListView, ListItem
from models import SearchHit

class ResultsItem(ListItem):
    def __init__(self,hit: SearchHit) -> None:
        super().__init__()
        self.hit = hit

    def compose(self):
        text = Text()
        text.append(self.hit.title, style="bold")
        if self.hit.year:
            text.append(f" ({self.hit.year})", style="dim")
        if self.hit.vote_average:
            text.append(f"  ★{self.hit.vote_average:.1f}", style="yellow")
        yield Label(text)

class ResultList(ListView):
    DEFAULT_CSS = """
    ResultList {
        height: 1fr;
        border: none;
        background: transparent;
    }
    ResultList > ResultItem {
        padding: 0 1;
    }
    ResultList > ResultItem.--highlight {
        background: $accent 30;
    }
    """

    async def set_hits(self, hits: list[SearchHit]) -> None:
        await self.clear()
        for hit in hits:
            await self.append(ResultsItem(hit))
        if hits:
            self.index = 0
    @property
    def current_hit(self) -> SearchHit | None:
        item = self.highlighted_child
        return item.hit if isinstance(item, ResultItem) else None