"""The Textual application shell."""

from __future__ import annotations

import sys
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Select, Tab, Tabs

from config import Config
from models import MOVIE, TV, SearchHit
from service import MovieService
from sources import TMDBError
from widgets import DetailPane, PosterPane, ResultsList

SEARCH_TAB = "tab-search"
TRENDING_TAB = "tab-trending"
CATEGORIES_TAB = "tab-categories"

MEDIA_OPTIONS = [("Movies", MOVIE), ("Series", TV), ("Both", "all")]
WINDOW_OPTIONS = [("This week", "week"), ("Today", "day")]


def _css_path() -> Path:
    """Works both from source and from a frozen one-file bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "app.tcss"


class ColombusApp(App[None]):
    CSS_PATH = _css_path()
    TITLE = "Colombus"
    SUB_TITLE = "terminal movie & series browser"

    # Deliberately no bare-letter bindings: they would be swallowed while
    # typing in the search Input.
    BINDINGS = [
        ("ctrl+s", "focus_search", "Search"),
        ("escape", "focus_results", "Results"),
        ("ctrl+t", "next_section", "Next section"),
        ("ctrl+r", "purge_cache", "Clear cache"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, config: Config, initial_query: str = "") -> None:
        super().__init__()
        self.config = config
        self._service = MovieService(config)
        self._initial_query = initial_query.strip()
        self._warned_omdb = False
        self._section = SEARCH_TAB
        self._genres_loaded_for: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Search for a film or series...", id="search")
        yield Tabs(
            Tab("Search", id=SEARCH_TAB),
            Tab("Trending", id=TRENDING_TAB),
            Tab("Categories", id=CATEGORIES_TAB),
            id="tabs",
        )
        with Horizontal(id="body"):
            with Vertical(id="left"):
                with Horizontal(id="controls"):
                    yield Select(
                        MEDIA_OPTIONS, value=MOVIE, allow_blank=False, id="media"
                    )
                    yield Select(
                        WINDOW_OPTIONS, value="week", allow_blank=False, id="window"
                    )
                    yield Select([], prompt="Category...", id="genre")
                yield ResultsList(id="results")
            with Vertical(id="right"):
                yield PosterPane(id="poster", protocol=self.config.poster_protocol)
                yield DetailPane(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self._sync_controls()
        search = self.query_one("#search", Input)
        if self._initial_query:
            search.value = self._initial_query
            self.load_list()
        else:
            search.focus()

    async def on_unmount(self) -> None:
        await self._service.aclose()

    # ------------------------------------------------------------------ helpers

    @property
    def _media(self) -> str:
        return str(self.query_one("#media", Select).value)

    def _sync_controls(self) -> None:
        """Only show the control that belongs to the active section."""
        self.query_one("#window", Select).display = self._section == TRENDING_TAB
        self.query_one("#genre", Select).display = self._section == CATEGORIES_TAB

    # ------------------------------------------------------------------ workers

    @work(exclusive=True, group="list")
    async def load_list(self) -> None:
        results = self.query_one(ResultsList)
        detail = self.query_one(DetailPane)
        media = self._media

        try:
            if self._section == TRENDING_TAB:
                window = str(self.query_one("#window", Select).value)
                detail.show_message("Loading trending titles...")
                hits = await self._service.trending(media, window)
                empty = "Nothing trending right now."
            elif self._section == CATEGORIES_TAB:
                genre = self.query_one("#genre", Select).value
                if genre is Select.BLANK:
                    await results.show([])
                    await self.query_one(PosterPane).clear()
                    detail.show_message("Pick a category to browse.")
                    return
                detail.show_message("Loading category...")
                hits = await self._service.by_genre(
                    MOVIE if media == "all" else media, int(genre)
                )
                empty = "Nothing in that category."
            else:
                query = self.query_one("#search", Input).value.strip()
                if not query:
                    await results.show([])
                    await self.query_one(PosterPane).clear()
                    detail.show_message("Type a title and press enter.")
                    return
                detail.show_message(f"Searching for '{query}'...")
                hits = await self._service.search(query, media)
                empty = f"Nothing found for '{query}'."
        except TMDBError as exc:
            await results.show([])
            detail.show_message(str(exc), "red")
            return

        await results.show(hits)
        if not hits:
            await self.query_one(PosterPane).clear()
            detail.show_message(empty)
            return
        results.focus()

    @work(exclusive=True, group="genres")
    async def load_genres(self) -> None:
        select = self.query_one("#genre", Select)
        media = self._media
        try:
            genres = await self._service.genres(MOVIE if media == "all" else media)
        except TMDBError as exc:
            self.query_one(DetailPane).show_message(str(exc), "red")
            return
        select.set_options([(genre.name, genre.tmdb_id) for genre in genres])
        self._genres_loaded_for = media

    @work(exclusive=True, group="detail")
    async def load_details(self, hit: SearchHit) -> None:
        detail = self.query_one(DetailPane)
        poster = self.query_one(PosterPane)
        detail.show_message(f"Loading {hit.label}...")

        try:
            movie = await self._service.details(hit.tmdb_id, hit.media_type)
        except TMDBError as exc:
            detail.show_message(str(exc), "red")
            return

        detail.show_movie(movie)
        self._warn_once_about_omdb()
        data = await self._service.poster(movie.poster_path or hit.poster_path)
        await poster.show(data, movie.label)

    # ----------------------------------------------------------------- messages

    @on(Input.Submitted, "#search")
    def _on_search_submitted(self) -> None:
        tabs = self.query_one("#tabs", Tabs)
        if tabs.active != SEARCH_TAB:
            tabs.active = SEARCH_TAB          # fires TabActivated, which reloads
        else:
            self.load_list()

    @on(Tabs.TabActivated)
    def _on_tab_activated(self, event: Tabs.TabActivated) -> None:
        self._section = event.tab.id or SEARCH_TAB
        self._sync_controls()
        if self._section == CATEGORIES_TAB and self._genres_loaded_for != self._media:
            self.load_genres()
        self.load_list()

    @on(Select.Changed, "#media")
    def _on_media_changed(self) -> None:
        if self._section == CATEGORIES_TAB:
            self.load_genres()
        self.load_list()

    @on(Select.Changed, "#window")
    def _on_window_changed(self) -> None:
        if self._section == TRENDING_TAB:
            self.load_list()

    @on(Select.Changed, "#genre")
    def _on_genre_changed(self) -> None:
        if self._section == CATEGORIES_TAB:
            self.load_list()

    @on(ResultsList.Highlighted)
    def _on_result_highlighted(self, event: ResultsList.Highlighted) -> None:
        if hit := getattr(event.item, "hit", None):
            self.load_details(hit)

    # ------------------------------------------------------------------ actions

    def _warn_once_about_omdb(self) -> None:
        """A rejected OMDb key silently costs ratings; say so, once."""
        if self._service.omdb.auth_failed and not self._warned_omdb:
            self._warned_omdb = True
            self.notify(
                "OMDb rejected your API key, so extra ratings are unavailable. "
                "Check OMDB_API_KEY in your .env (new keys need the activation "
                "link e-mailed to you).",
                title="OMDb unavailable",
                severity="warning",
                timeout=10,
            )

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_focus_results(self) -> None:
        self.query_one(ResultsList).focus()

    def action_next_section(self) -> None:
        self.query_one("#tabs", Tabs).action_next_tab()

    def action_purge_cache(self) -> None:
        self._service.purge_cache()
        self.notify("Cached responses and posters cleared.")
