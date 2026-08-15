"""The Textual application shell."""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Footer,
    Header,
    Input,
    Select,
    Tab,
    TabbedContent,
    TabPane,
    Tabs,
)

from config import Config
from i18n import _
from models import MOVIE, TV, Movie, SearchHit
from service import MovieService
from sources import TMDBError
from widgets import CastPane, DetailPane, EpisodesPane, PosterPane, ResultsList, ReviewsPane

SEARCH_TAB = "tab-search"
TRENDING_TAB = "tab-trending"
CATEGORIES_TAB = "tab-categories"
WATCHLIST_TAB = "tab-watchlist"

DETAILS_PANE = "pane-details"
REVIEWS_PANE = "pane-reviews"
CAST_PANE = "pane-cast"
EPISODES_PANE = "pane-episodes"

MEDIA_OPTIONS = [(_("movies"), MOVIE), (_("series"), TV), (_("both"), "all")]
WINDOW_OPTIONS = [(_("this_week"), "week"), (_("today"), "day")]
LANGUAGE_OPTIONS = [
    (_("any_language"), ""), ("English", "en"), ("हिन्दी / Hindi", "hi"),
    ("தமிழ் / Tamil", "ta"), ("తెలుగు / Telugu", "te"), ("മലയാളം / Malayalam", "ml"),
    ("ಕನ್ನಡ / Kannada", "kn"), ("বাংলা / Bengali", "bn"), ("मराठी / Marathi", "mr"),
    ("ਪੰਜਾਬੀ / Punjabi", "pa"), ("日本語 / Japanese", "ja"), ("한국어 / Korean", "ko"),
    ("Español", "es"), ("Français", "fr"), ("Deutsch", "de"), ("中文 / Mandarin", "zh"),
]


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
        ("ctrl+s", "focus_search", _("search")),
        ("escape", "focus_results", _("results")),
        ("ctrl+t", "next_section", _("next_section")),
        ("f2", "cycle_info", _("details_reviews")),
        ("f3", "recommendations", _("more_like_this")),
        ("f4", "trailer", _("trailer")),
        ("f5", "open_page", _("open_page")),
        ("ctrl+d", "toggle_watchlist", _("watchlist_toggle")),
        ("ctrl+r", "purge_cache", _("clear_cache")),
        ("ctrl+q", "quit", _("quit")),
    ]

    def __init__(self, config: Config, initial_query: str = "") -> None:
        super().__init__()
        self.config = config
        self._service = MovieService(config)
        self._initial_query = initial_query.strip()
        self._warned_omdb = False
        self._section = SEARCH_TAB
        self._genres_loaded_for: tuple[str, str] | None = None
        self._current: Movie | None = None
        self._current_hit: SearchHit | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder=_("search_placeholder"), id="search")
        yield Tabs(
            Tab(_("search"), id=SEARCH_TAB),
            Tab(_("trending"), id=TRENDING_TAB),
            Tab(_("categories"), id=CATEGORIES_TAB),
            Tab(_("watchlist"), id=WATCHLIST_TAB),
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
                    yield Select([], prompt=_("category_prompt"), id="genre")
                    yield Select(
                        LANGUAGE_OPTIONS, value="", allow_blank=False, id="language"
                    )
                yield ResultsList(id="results")
            with Vertical(id="right"):
                yield PosterPane(id="poster", protocol=self.config.poster_protocol)
                with TabbedContent(id="info"):
                    with TabPane(_("details"), id=DETAILS_PANE):
                        yield DetailPane(id="detail")
                    with TabPane(_("reviews"), id=REVIEWS_PANE):
                        yield ReviewsPane(id="reviews")
                    with TabPane(_("cast"), id=CAST_PANE):
                        yield CastPane(id="cast")
                    with TabPane(_("episodes"), id=EPISODES_PANE):
                        yield EpisodesPane(id="episodes")
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

    @property
    def _discover_media(self) -> str:
        """TMDB has no combined genre list, so 'Both' browses movies."""
        media = self._media
        return MOVIE if media == "all" else media

    def _sync_controls(self) -> None:
        """Only show the controls belonging to the active section."""
        self.query_one("#window", Select).display = self._section == TRENDING_TAB
        categories = self._section == CATEGORIES_TAB
        self.query_one("#genre", Select).display = categories
        self.query_one("#language", Select).display = categories

    # ------------------------------------------------------------------ workers

    @work(exclusive=True, group="list")
    async def load_list(self) -> None:
        results = self.query_one(ResultsList)
        detail = self.query_one(DetailPane)
        media = self._media

        try:
            if self._section == TRENDING_TAB:
                window = str(self.query_one("#window", Select).value)
                detail.show_message(_("loading_trending"))
                hits = await self._service.trending(media, window)
                empty = _("nothing_trending")
            elif self._section == CATEGORIES_TAB:
                genre = self.query_one("#genre", Select).value
                language = str(self.query_one("#language", Select).value or "")
                if genre is Select.BLANK and not language:
                    await self._show_nothing(_("pick_category"))
                    return
                detail.show_message(_("loading_category"))
                hits = await self._service.by_genre(
                    self._discover_media,
                    None if genre is Select.BLANK else int(genre),
                    language,
                )
                empty = _("nothing_in_category")
            elif self._section == WATCHLIST_TAB:
                hits = self._service.watchlist()
                empty = _("watchlist_empty")
            else:
                query = self.query_one("#search", Input).value.strip()
                if not query:
                    recent = self._service.recent_searches()
                    await results.show_queries(recent)
                    await self.query_one(PosterPane).clear()
                    detail.show_message(
                        _("recent_searches") if recent else _("type_a_title")
                    )
                    return
                detail.show_message(_("searching", query=query))
                hits = await self._service.search(query, media)
                self._service.remember_search(query, media)
                empty = _("nothing_found", query=query)
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

    async def _show_nothing(self, message: str) -> None:
        await self.query_one(ResultsList).show([])
        await self.query_one(PosterPane).clear()
        self.query_one(DetailPane).show_message(message)

    @work(exclusive=True, group="genres")
    async def load_genres(self) -> None:
        select = self.query_one("#genre", Select)
        media = self._discover_media
        try:
            genres = await self._service.genres(media)
        except TMDBError as exc:
            self.query_one(DetailPane).show_message(str(exc), "red")
            return
        select.set_options([(genre.name, genre.tmdb_id) for genre in genres])
        # Genre names are translated, so the cache is per language too.
        self._genres_loaded_for = (media, self.config.language)

    @work(exclusive=True, group="detail")
    async def load_details(self, hit: SearchHit) -> None:
        detail = self.query_one(DetailPane)
        poster = self.query_one(PosterPane)
        detail.show_message(_("loading_title", title=hit.label))

        try:
            movie = await self._service.details(hit.tmdb_id, hit.media_type)
        except TMDBError as exc:
            detail.show_message(str(exc), "red")
            self.query_one(ReviewsPane).show_message(str(exc), "red")
            self._set_review_count(0)
            return

        self._current, self._current_hit = movie, hit
        detail.show_movie(movie)
        self.query_one(ReviewsPane).show_movie(movie)
        self._set_review_count(len(movie.reviews))
        await self.query_one(CastPane).show_movie(movie)
        self._sync_episodes(movie)
        self._warn_once_about_omdb()

        data = await self._service.poster(movie.poster_path or hit.poster_path)
        await poster.show(data, movie.label)

    @work(exclusive=True, group="list")
    async def load_person(self, person_id: int, name: str) -> None:
        results = self.query_one(ResultsList)
        detail = self.query_one(DetailPane)
        detail.show_message(_("loading_person", name=name))
        try:
            hits = await self._service.person_titles(person_id)
        except TMDBError as exc:
            detail.show_message(str(exc), "red")
            return
        await results.show(hits)
        if hits:
            results.focus()

    @work(exclusive=True, group="season")
    async def load_season(self, tv_id: int, number: int) -> None:
        pane = self.query_one(EpisodesPane)
        pane.show_message(_("loading_season", number=number))
        try:
            pane.show_season(await self._service.season(tv_id, number))
        except TMDBError as exc:
            pane.show_message(str(exc), "red")

    # ----------------------------------------------------------------- messages

    @on(Input.Submitted, "#search")
    def _on_search_submitted(self) -> None:
        tabs = self.query_one("#tabs", Tabs)
        if tabs.active != SEARCH_TAB:
            tabs.active = SEARCH_TAB  # fires TabActivated, which reloads
        else:
            self.load_list()

    @on(Tabs.TabActivated, "#tabs")
    def _on_tab_activated(self, event: Tabs.TabActivated) -> None:
        self._section = event.tab.id or SEARCH_TAB
        self._sync_controls()
        if self._section == CATEGORIES_TAB and self._genres_loaded_for != (
            self._discover_media,
            self.config.language,
        ):
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

    @on(Select.Changed, "#language")
    def _on_language_changed(self) -> None:
        if self._section == CATEGORIES_TAB:
            self.load_list()

    @on(Select.Changed, "#season")
    def _on_season_changed(self, event: Select.Changed) -> None:
        if self._current and event.value is not Select.BLANK:
            self.load_season(self._current.tmdb_id, int(event.value))

    @on(ResultsList.Highlighted)
    def _on_result_highlighted(self, event: ResultsList.Highlighted) -> None:
        if hit := getattr(event.item, "hit", None):
            self.load_details(hit)

    @on(ResultsList.Selected)
    def _on_result_selected(self, event: ResultsList.Selected) -> None:
        """Enter on a remembered search re-runs it."""
        if query := getattr(event.item, "query", None):
            self.query_one("#search", Input).value = query
            self.load_list()

    @on(CastPane.Selected)
    def _on_person_selected(self, event: CastPane.Selected) -> None:
        if person := getattr(event.item, "person", None):
            self.load_person(person.tmdb_id, person.name)

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

    def _set_review_count(self, count: int) -> None:
        tab = self.query_one("#info", TabbedContent).get_tab(REVIEWS_PANE)
        tab.label = f"{_('reviews')} ({count})" if count else _("reviews")

    def _sync_episodes(self, movie: Movie) -> None:
        """The Episodes tab only means anything for a series."""
        pane = self.query_one(EpisodesPane)
        tab = self.query_one("#info", TabbedContent).get_tab(EPISODES_PANE)
        tab.disabled = not movie.is_series
        if movie.is_series and movie.season_numbers:
            pane.set_seasons(movie.season_numbers)
        else:
            pane.clear_seasons()
            pane.show_message(_("episodes_series_only"))

    def action_cycle_info(self) -> None:
        tabs = self.query_one("#info", TabbedContent)
        order = [DETAILS_PANE, REVIEWS_PANE, CAST_PANE, EPISODES_PANE]
        start = order.index(tabs.active) if tabs.active in order else 0
        for step in range(1, len(order) + 1):
            candidate = order[(start + step) % len(order)]
            if not tabs.get_tab(candidate).disabled:
                tabs.active = candidate
                return

    def action_recommendations(self) -> None:
        if not (self._current and self._current.recommendations):
            self.notify(_("no_recommendations"), severity="warning")
            return
        self.show_recommendations(list(self._current.recommendations))

    @work(exclusive=True, group="list")
    async def show_recommendations(self, hits: list[SearchHit]) -> None:
        results = self.query_one(ResultsList)
        await results.show(hits)
        results.focus()

    def action_trailer(self) -> None:
        trailer = self._current.trailer if self._current else None
        if trailer is None:
            self.notify(_("no_trailer"), severity="warning")
            return
        webbrowser.open(trailer.url)
        self.notify(_("opening", name=trailer.name or trailer.kind))

    def action_open_page(self) -> None:
        if self._current:
            webbrowser.open(self._current.imdb_url or self._current.tmdb_url)

    def action_toggle_watchlist(self) -> None:
        hit = self._current_hit
        if hit is None:
            return
        added = self._service.watchlist_toggle(hit)
        self.notify(
            _("watchlist_added" if added else "watchlist_removed", title=hit.title)
        )
        if self._section == WATCHLIST_TAB:
            self.load_list()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_focus_results(self) -> None:
        self.query_one(ResultsList).focus()

    def action_next_section(self) -> None:
        self.query_one("#tabs", Tabs).action_next_tab()

    def action_purge_cache(self) -> None:
        self._service.purge_cache()
        self.notify(_("cache_cleared"))
