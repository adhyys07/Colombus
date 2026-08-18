"""Rich renderables for the detail pane."""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from i18n import _
from models import Movie, Rating, Season, Stats

BAR_WIDTH = 24
MAX_REVIEWS = 3
DASH = "—"
BLOCKS = "▁▂▃▄▅▆▇█"
BRAILLE_BASE = 0x2800
# dot bit per (column, row) inside a 2x4 braille cell
DOTS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))


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


def sparkline(values: list[float], lo: float = 0.0, hi: float = 10.0) -> Text:
    """One block per value, coloured by score band. Works in any font."""
    line = Text()
    span = hi - lo
    for value in values:
        index = round((value - lo) / span * (len(BLOCKS) - 1)) if span > 0 else 0
        index = max(0, min(len(BLOCKS) - 1, index))
        line.append(BLOCKS[index], style=_score_style(value * 10))
    return line


def braille_chart(
    values: list[float], cols: int = 40, rows: int = 4,
    lo: float = 0.0, hi: float = 10.0,
) -> Text:
    """A line plot at 2x4 dots per cell - four times the horizontal
    resolution of a block sparkline in the same width."""
    if not values:
        return Text()
    width, height = cols * 2, rows * 4
    grid = [[0] * cols for _ in range(rows)]
    span = hi - lo

    for x in range(width):
        position = x / max(1, width - 1) * (len(values) - 1)
        left = int(position)
        right = min(left + 1, len(values) - 1)
        value = values[left] + (values[right] - values[left]) * (position - left)
        ratio = (value - lo) / span if span > 0 else 0.5
        y = height - 1 - max(0, min(height - 1, round(ratio * (height - 1))))
        grid[y // 4][x // 2] |= DOTS[x % 2][y % 4]

    out = Text()
    for index, row in enumerate(grid):
        out.append("".join(chr(BRAILLE_BASE + bits) for bits in row))
        if index < len(grid) - 1:
            out.append(chr(10))
    return out


def season_chart(season: Season) -> RenderableType | None:
    """Episode ratings across a season. None when there is nothing to plot."""
    scores = [e.vote_average for e in season.episodes if e.vote_average]
    if len(scores) < 2:
        return None
    low, high = min(scores), max(scores)
    # A flat season would otherwise draw a line along the very edge.
    pad = max(0.3, (high - low) * 0.15)
    chart = braille_chart(
        scores, cols=min(46, max(8, len(scores) * 2)), rows=3,
        lo=low - pad, hi=high + pad,
    )
    header = Text(f"{high:.1f} high  ", style="dim")
    footer = Text(f"{low:.1f} low   E1-E{len(season.episodes)}", style="dim")
    return Group(header, chart, footer)


def facts_table(movie: Movie) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right", no_wrap=True)
    table.add_column(ratio=1)

    rows: list[tuple[str, str]] = [
        (
            _("creator") if movie.is_series else _("director"),
            movie.director or DASH,
        ),
        (_("writers"), ", ".join(movie.writers) or DASH),
        (_("cast"), ", ".join(person.name for person in movie.cast) or DASH),
        (_("genre"), ", ".join(movie.genres) or DASH),
        (
            _("episode") if movie.is_series else _("runtime"),
            _runtime(movie.runtime),
        ),
        (_("rated"), movie.certificate or DASH),
        (_("language"), ", ".join(filter(None, movie.languages)) or DASH),
        (_("country"), ", ".join(filter(None, movie.countries)) or DASH),
    ]
    if not movie.is_series:
        rows += [
            (_("budget"), _money(movie.budget)),
            (_("revenue"), _money(movie.revenue)),
        ]
    if movie.is_series:
        rows.insert(4, (_("seasons"), str(movie.seasons) if movie.seasons else DASH))
        rows.insert(5, (_("episodes"), str(movie.episodes) if movie.episodes else DASH))
    if stream := movie.providers_of("flatrate", "free", "ads"):
        rows.append((_("stream"), ", ".join(stream)))
    if paid := movie.providers_of("rent", "buy"):
        rows.append((_("rent_buy"), ", ".join(paid)))
    if movie.imdb_url:
        rows.append(("IMDb", movie.imdb_url))

    for label, value in rows:
        table.add_row(label, value)
    return table


def _header(movie: Movie) -> Text:
    header = Text(movie.title, style="bold white")
    if movie.year:
        header.append(f"  ({movie.year})", style="dim")
    badge = _("series_badge") if movie.is_series else _("film_badge")
    header.append(f"  {badge}", style="dim cyan")
    if movie.tagline:
        header.append(f"\n{movie.tagline}", style="italic dim")
    return header


def movie_renderable(movie: Movie) -> RenderableType:
    parts: list[RenderableType] = [_header(movie), Rule(style="dim"), facts_table(movie)]

    if movie.ratings:
        parts += [
            Rule(_("ratings"), style="dim"),
            Group(*(rating_bar(rating) for rating in movie.ratings)),
        ]

    if movie.overview:
        parts += [Panel(movie.overview, title=_("overview"), border_style="dim")]

    if movie.wiki_extract:
        subtitle = movie.wiki_url or None
        parts += [
            Panel(
                movie.wiki_extract,
                title=_("wikipedia"),
                subtitle=subtitle,
                border_style="dim",
            )
        ]

    if movie.reviews:
        parts.append(Rule(_("reviews"), style="dim"))
        for review in movie.reviews[:MAX_REVIEWS]:
            title = review.author
            if review.rating is not None:
                title += f"  ({review.rating:g}/10)"
            parts.append(
                Panel(review.excerpt(), title=title, border_style="dim", title_align="left")
            )

    return Group(*parts)


def reviews_renderable(movie: Movie) -> RenderableType:
    """Every review in full, for the Reviews tab."""
    if not movie.reviews:
        return message_renderable(_("no_reviews", title=movie.label))

    count = len(movie.reviews)
    header = Text(
        _("review_count_one") if count == 1 else _("reviews_count", count=count),
        style="bold",
    )
    header.append(f"  ·  {movie.label}", style="dim")
    parts: list[RenderableType] = [header, Rule(style="dim")]

    for index, review in enumerate(movie.reviews, start=1):
        title = Text(f"{index}. {review.author}", style="bold")
        if review.rating is not None:
            title.append(f"  {review.rating:g}/10", style=_score_style(review.rating * 10))
        if review.date:
            title.append(f"  {review.date}", style="dim")

        body = Text(" ".join(review.content.split()))
        if review.url:
            body.append(f"\n\n{review.url}", style="dim")
        parts.append(Panel(body, title=title, title_align="left", border_style="dim"))

    return Group(*parts)


def episodes_renderable(season: Season) -> RenderableType:
    if not season.episodes:
        return message_renderable(_("no_episodes"))

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right", no_wrap=True)
    table.add_column(ratio=1)
    table.add_column(style="dim", no_wrap=True)

    for episode in season.episodes:
        score = f"{episode.vote_average:.1f}" if episode.vote_average else DASH
        table.add_row(
            f"E{episode.number}", episode.name, f"{episode.air_date}  {score}"
        )

    header = Text(season.name, style="bold")
    header.append(f"  {len(season.episodes)} {_('episodes').lower()}", style="dim")

    parts: list[RenderableType] = [header, Rule(style="dim")]
    if chart := season_chart(season):
        parts += [chart, Rule(style="dim")]
    parts.append(table)
    return Group(*parts)


def _count_bars(pairs: list[tuple[str, int]]) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right", no_wrap=True)
    table.add_column(ratio=1)
    peak = max((count for _, count in pairs), default=1) or 1
    for label, count in pairs:
        filled = round(count / peak * BAR_WIDTH)
        bar = Text("█" * filled, style="green")
        bar.append("░" * (BAR_WIDTH - filled), style="dim")
        bar.append(f"  {count}", style="dim")
        table.add_row(label, bar)
    return table


def stats_renderable(stats: Stats) -> RenderableType:
    if not stats.total:
        return message_renderable(_("nothing_watched"))

    head = Text(_("titles_watched", count=stats.total), style="bold")
    head.append(
        f"\n{stats.films} {_('movies').lower()} · {stats.series} "
        f"{_('series').lower()} · {stats.hours:.0f} {_('hours')}",
        style="dim",
    )
    parts: list[RenderableType] = [head, Rule(style="dim")]
    if stats.genres:
        parts += [Rule(_("genre"), style="dim"), _count_bars(stats.genres)]
    if stats.decades:
        parts += [Rule(_("decades"), style="dim"), _count_bars(stats.decades)]
    if stats.recent:
        recent = Table.grid(padding=(0, 2))
        recent.add_column(style="dim", no_wrap=True)
        recent.add_column(ratio=1)
        for entry in stats.recent:
            recent.add_row(entry.date, entry.title)
        parts += [Rule(_("recently_watched"), style="dim"), recent]
    return Group(*parts)


def message_renderable(text: str, style: str = "dim") -> RenderableType:
    return Text(text, style=style, justify="center")
