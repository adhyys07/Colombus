from __future__ import annotations
from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static
from models import Movie, Rating

_BAR_WIDTH = 18

def score_colour(score: float | None) -> str:
    if score is None:
        return "grey62"
    if score >= 75:
        return "green"
    if score >= 55:
        return "yellow"
    return "red"

def rating_bar(rating: Rating) -> Text:
    text = Text()
    text.append(f"{rating.source:<22}", style="bold")
    if rating.score is None:
        text.append(rating.value)
        return text
    filled = round(rating.score / 100 * _BAR_WIDTH)
    colour = score_colour(rating.score)
    text.append("█" * filled, style=colour)
    text.append("░" * (_BAR_WIDTH - filled), style="grey30")
    text.append(f"  {rating.value}", style=colour)
    return text

def _money(n:int) -> str:
    if not n:
        return "—"
    for unit, div in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if n >= div:
            return f"${n / div:.1f}{unit}"
    return f"${n}"

class DetailPanel(VerticalScroll):
    DEFAULT_CSS = """
    DetailPanel {
        width: 1fr;
        height: 1fr;
        padding: 0 2 1 1;
        scrollbar-size-vertical: 1;
    }
    DetailPanel > Static {
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(id="d-head")
        yield Static(id="d-facts")
        yield Static(id="d-scores")
        yield Static(id="d-plot")
        yield Static(id="d-wiki")
        yield Static(id="d-reviews")

    def show_message(self, message: str) -> None:
        self.query_one("#d-head", Static).update(Text(message, style="dim italic"))
        for wid in ("#d-facts", "#d-scores", "#d-plot", "#d-wiki", "#d-reviews"):
            self.query_one(wid, Static).update("")

    def show_movie(self, movie: Movie) -> None:
        self.scroll_home(animate=False)
        self.query_one("#d-head", Static).update(self._head(movie))
        self.query_one("#d-facts", Static).update(self._facts(movie))
        self.query_one("#d-scores", Static).update(self._scores(movie))
        self.query_one("#d-plot", Static).update(self._plot(movie))
        self.query_one("#d-wiki", Static).update(self._wiki(movie))
        self.query_one("#d-reviews", Static).update(self._reviews(movie))

    def _head(self, m: Movie) -> Group:
        title = Text(m.title, style="bold white")
        if m.year:
            title.append(f" ({m.year})", style="not bold grey62")
        parts = [title]
        if m.tagline:
            parts.append(Text(f"“{m.tagline}”", style="italic grey62"))
        return Group(*parts)

    def _facts(self, m: Movie) -> Table:
        table = Table.grid(padding=(0, 2))
        table.add_column(style="grey50", justify="right", no_wrap=True)
        table.add_column(style="white")

        def row(label: str, value: str) -> None:
            if value and value != "—":
                table.add_row(label, value)

        meta = " · ".join(
            x for x in (m.runtime_str, ", ".join(m.genres), m.certification) if x
        )
        row("", meta)
        row("Director", m.director)
        row("Writers", ", ".join(m.writers))
        row("Cast", ", ".join(m.cast))
        row("Language", ", ".join(m.languages[:3]))
        row("Country", ", ".join(m.countries[:3]))
        if m.budget or m.revenue:
            row("Box office", f"{_money(m.budget)} budget → {_money(m.revenue)} gross")
        if m.imdb_url:
            row("IMDb", m.imdb_url)
        return table

    def _scores(self, m: Movie):
        if not m.ratings:
            return Text("No aggregate scores available.", style="dim")
        return Panel(
            Group(*[rating_bar(r) for r in m.ratings]),
            title="[bold]critic & audience scores[/]",
            title_align="left",
            border_style="grey37",
            padding=(0, 1),
        )

    def _plot(self, m: Movie):
        if not m.overview:
            return Text("")
        return Group(
            Rule("synopsis", style="grey50", align="left"),
            Text(m.overview, style="white"),
        )

    def _wiki(self, m: Movie):
        if not m.wiki_extract:
            return Text("")
        body = Text(m.wiki_extract, style="grey70")
        parts = [Rule("wikipedia", style="grey37", align="left"), body]
        if m.wiki_url:
            parts.append(Text(m.wiki_url, style="dim blue underline"))
        return Group(*parts)

    def _reviews(self, m: Movie):
        if not m.reviews:
            return Group(
                Rule("reviews", style="grey37", align="left"),
                Text(
                    "No reviews returned for this title. Note that Rotten "
                    "Tomatoes and Metacritic license their review text — only "
                    "the scores above are freely available.",
                    style="dim italic",
                ),
            )

        blocks = [Rule("reviews", style="grey37", align="left")]
        for rev in m.reviews[:4]:
            header = Text(f"@{rev.author}", style="bold cyan")
            if rev.rating:
                header.append(
                    f"  {rev.rating:.0f}/10",
                    style=score_colour(rev.rating * 10),
                )
            blocks.append(header)
            blocks.append(Text(rev.excerpt(), style="grey70"))
            blocks.append(Text(""))
        return Group(*blocks)
            