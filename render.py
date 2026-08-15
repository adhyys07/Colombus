"""Rich renderables for the detail pane."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from models import Movie, Rating

BAR_WIDTH = 24
MAX_REVIEWS = 3
DASH = "—"


def _money(amount: int) -> str:
    if not amount:
        return DASH
    for suffix, size in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if amount >= size:
            return f"${amount / size:.1f}{suffix}"
    return f"${amount:,}"


def _runtime(minutes: int | None) -> str:
    if not minutes:
        return DASH
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins:02d}m" if hours else f"{mins}m"


def _score_style(score: float) -> str:
    if score >= 70:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def rating_bar(rating: Rating, width: int = BAR_WIDTH) -> Text:
    line = Text()
    line.append(f"{rating.source:<22}", style="bold")

    if rating.score is None:
        line.append(f"{rating.value:>8}", style="dim")
        return line

    filled = round(rating.score / 100 * width)
    style = _score_style(rating.score)
    line.append("█" * filled, style=style)
    line.append("░" * (width - filled), style="dim")
    line.append(f" {rating.value:>8}", style=style)
    return line


def facts_table(movie: Movie) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right", no_wrap=True)
    table.add_column(ratio=1)

    rows: list[tuple[str, str]] = [
        ("Director", movie.director or DASH),
        ("Writers", ", ".join(movie.writers) or DASH),
        ("Cast", ", ".join(movie.cast) or DASH),
        ("Genre", ", ".join(movie.genres) or DASH),
        ("Runtime", _runtime(movie.runtime)),
        ("Rated", movie.certificate or DASH),
        ("Language", ", ".join(filter(None, movie.languages)) or DASH),
        ("Country", ", ".join(filter(None, movie.countries)) or DASH),
        ("Budget", _money(movie.budget)),
        ("Revenue", _money(movie.revenue)),
    ]
    if movie.imdb_url:
        rows.append(("IMDb", movie.imdb_url))

    for label, value in rows:
        table.add_row(label, value)
    return table


def _header(movie: Movie) -> Text:
    header = Text(movie.title, style="bold white")
    if movie.year:
        header.append(f"  ({movie.year})", style="dim")
    if movie.tagline:
        header.append(f"\n{movie.tagline}", style="italic dim")
    return header


def movie_renderable(movie: Movie) -> RenderableType:
    parts: list[RenderableType] = [_header(movie), Rule(style="dim"), facts_table(movie)]

    if movie.ratings:
        parts += [
            Rule("Ratings", style="dim"),
            Group(*(rating_bar(rating) for rating in movie.ratings)),
        ]

    if movie.overview:
        parts += [Panel(movie.overview, title="Overview", border_style="dim")]

    if movie.wiki_extract:
        subtitle = movie.wiki_url or None
        parts += [
            Panel(
                movie.wiki_extract,
                title="Wikipedia",
                subtitle=subtitle,
                border_style="dim",
            )
        ]

    if movie.reviews:
        parts.append(Rule("Reviews", style="dim"))
        for review in movie.reviews[:MAX_REVIEWS]:
            title = review.author
            if review.rating is not None:
                title += f"  ({review.rating:g}/10)"
            parts.append(
                Panel(review.excerpt(), title=title, border_style="dim", title_align="left")
            )

    return Group(*parts)


def message_renderable(text: str, style: str = "dim") -> RenderableType:
    return Text(text, style=style, justify="center")
