"""The Textual application shell."""

from __future__ import annotations

import sys
import threading
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
from models import MOVIE, PERSON, TV, Filters, Movie, SearchHit
from player import (
    TrailerError,
    audio_available,
    missing_tools,
    play,
    resolve_streams,
)
from service import MovieService
from videoart import frame_strips, set_enhance
from sources import TMDBError
from widgets import (
    CastPane,
    DetailPane,
    EpisodesPane,
    PersonItem,
    PersonResult,
    PosterPane,
    QueryItem,
    PlayerPane,
    ResultsList,
    ReviewsPane,
    StatsPane,
)

SEARCH_TAB = "tab-search"
TRENDING_TAB = "tab-trending"
CATEGORIES_TAB = "tab-categories"
WATCHLIST_TAB = "tab-watchlist"
WATCHED_TAB = "tab-watched"

DETAILS_PANE = "pane-details"
REVIEWS_PANE = "pane-reviews"
CAST_PANE = "pane-cast"
EPISODES_PANE = "pane-episodes"
STATS_PANE = "pane-stats"
PLAYER_PANE = "pane-trailer"

MEDIA_OPTIONS = [
    (_("movies"), MOVIE),
    (_("series"), TV),
    (_("both"), "all"),
    (_("people"), PERSON),
]
# Each label reads on its own, so a closed dropdown still says what it is.
SORT_OPTIONS = [
    (_("sort_popular"), "popularity.desc"),
    (_("sort_rated"), "vote_average.desc"),
    (_("sort_newest"), "primary_release_date.desc"),
    (_("sort_grossing"), "revenue.desc"),
]
RATING_OPTIONS = [
    (_("any_rating"), 0.0),
    ("6.0+", 6.0),
    ("7.0+", 7.0),
    ("8.0+", 8.0),
]
DECADE_OPTIONS = [(_("any_year"), 0)] + [
    (f"{decade}s", decade) for decade in range(2020, 1949, -10)
]
WINDOW_OPTIONS = [(_("this_week"), "week"), (_("today"), "day")]
# An industry is an origin country plus an original language: "IN" alone
# returns Tamil and Malayalam films, so Bollywood has to be IN + hi.
# Encoded "COUNTRY:LANGUAGE"; either half may be empty.
INDUSTRY_OPTIONS = [
    (_("any_industry"), ""),
    ("Hollywood", "US:en"),
    ("Bollywood (Hindi)", "IN:hi"),
    ("Tollywood (Telugu)", "IN:te"),
    ("Kollywood (Tamil)", "IN:ta"),
    ("Mollywood (Malayalam)", "IN:ml"),
    ("Sandalwood (Kannada)", "IN:kn"),
    ("Bengali cinema", "IN:bn"),
    ("Marathi cinema", "IN:mr"),
    ("Punjabi cinema", "IN:pa"),
    ("British", "GB:en"),
    ("Korean", "KR:ko"),
    ("Japanese / anime", "JP:ja"),
    ("Chinese", "CN:zh"),
    ("Nollywood (Nigeria)", "NG:"),
    ("French", "FR:fr"),
    ("Spanish", "ES:es"),
    ("German", "DE:de"),
    ("Italian", "IT:it"),
    # Language only, when the country does not matter
    (_("lang_only_english"), ":en"),
    (_("lang_only_hindi"), ":hi"),
    (_("lang_only_tamil"), ":ta"),
    (_("lang_only_telugu"), ":te"),
    (_("lang_only_korean"), ":ko"),
    (_("lang_only_japanese"), ":ja"),
    (_("lang_only_spanish"), ":es"),
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
        ("ctrl+f", "toggle_filters", _("filters")),
        ("f6", "toggle_watched", _("mark_watched")),
        ("f7", "play_trailer", _("play_here")),
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
        self._filters_open = False
        self._current: Movie | None = None
        # Starts set: 'set' means nothing is playing, so the first
        # f7 reads as play rather than stop.
        self._stop_player = threading.Event()
        self._stop_player.set()
        self._current_hit: SearchHit | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder=_("search_placeholder"), id="search")
        yield Tabs(
            Tab(_("search"), id=SEARCH_TAB),
            Tab(_("trending"), id=TRENDING_TAB),
            Tab(_("categories"), id=CATEGORIES_TAB),
            Tab(_("watchlist"), id=WATCHLIST_TAB),
            Tab(_("watched"), id=WATCHED_TAB),
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
                with Horizontal(id="filters"):
                    yield Select(
                        INDUSTRY_OPTIONS, value="", allow_blank=False, id="industry"
                    )
                    yield Select(
                        SORT_OPTIONS,
                        value="popularity.desc",
                        allow_blank=False,
                        id="sort",
                    )
                    yield Select(
                        RATING_OPTIONS, value=0.0, allow_blank=False, id="min-rating"
                    )
                    yield Select(
                        DECADE_OPTIONS, value=0, allow_blank=False, id="decade"
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
                    with TabPane(_("stats"), id=STATS_PANE):
                        yield StatsPane(id="stats")
                    with TabPane(_("trailer"), id=PLAYER_PANE):
                        yield PlayerPane(id="player")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(PlayerPane).max_cols = self.config.trailer_max_cols
        if self.config.offline:
            self.sub_title = f"{self.SUB_TITLE} - {_('offline')}"
        self._sync_controls()
        search = self.query_one("#search", Input)
        if self._initial_query:
            search.value = self._initial_query
            self.load_list()
        else:
            search.focus()
        self.check_series_updates()

    async def on_unmount(self) -> None:
        self.stop_playback()
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
        """Show only what the active section can act on.

        The filter row stays hidden until ctrl+f, so the default view is
        two dropdowns rather than six.
        """
        self.query_one("#window", Select).display = self._section == TRENDING_TAB
        categories = self._section == CATEGORIES_TAB
        self.query_one("#genre", Select).display = categories
        self.query_one("#filters").display = categories and self._filters_open
        self._sync_results_title()

    def _sync_results_title(self) -> None:
        """Name the live filters, since the row itself may be hidden."""
        summary = (
            self._discover_filters.summary() if self._section == CATEGORIES_TAB else ""
        )
        self.query_one(ResultsList).border_title = (
            f"{_('results')} - {summary}" if summary else _("results")
        )

    @property
    def _industry(self) -> tuple[str, str, str]:
        """(origin country, original language, label) for the picker."""
        raw = str(self.query_one("#industry", Select).value or "")
        if not raw:
            return "", "", ""
        country, _sep, language = raw.partition(":")
        label = next(
            (name for name, value in INDUSTRY_OPTIONS if value == raw), ""
        )
        return country, language, label

    @property
    def _discover_filters(self) -> Filters:
        decade = int(self.query_one("#decade", Select).value or 0)
        country, _language, label = self._industry
        return Filters(
            sort_by=str(self.query_one("#sort", Select).value),
            min_rating=float(self.query_one("#min-rating", Select).value or 0),
            year_from=decade or None,
            year_to=(decade + 9) if decade else None,
            origin_country=country,
            industry_label=label,
        )

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
                _country, language, _label = self._industry
                if (
                    genre is Select.BLANK
                    and not language
                    and self._discover_filters.is_default
                ):
                    await self._show_nothing(_("pick_category"))
                    return
                detail.show_message(_("loading_category"))
                hits = await self._service.by_genre(
                    self._discover_media,
                    None if genre is Select.BLANK else int(genre),
                    language,
                    self._discover_filters,
                )
                empty = _("nothing_in_category")
            elif self._section == WATCHLIST_TAB:
                hits = self._service.watchlist()
                empty = _("watchlist_empty")
            elif self._section == WATCHED_TAB:
                hits = self._service.watched()
                self._refresh_stats()
                empty = _("nothing_watched")
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
                if media == PERSON:
                    people = await self._service.search_people(query)
                    self._service.remember_search(query, media)
                    await results.show_people(people)
                    if people:
                        results.focus()
                    else:
                        detail.show_message(_("nothing_found", query=query))
                    return
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

        self.stop_playback()
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

    @on(Select.Changed, "#industry")
    @on(Select.Changed, "#sort")
    @on(Select.Changed, "#min-rating")
    @on(Select.Changed, "#decade")
    def _on_filter_changed(self) -> None:
        if self._section == CATEGORIES_TAB:
            self._sync_results_title()
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
        # Type checks, not getattr: every Textual widget owns a .query()
        # method, so duck-typing on the name matches every row.
        item = event.item
        if isinstance(item, QueryItem):
            self.query_one("#search", Input).value = item.query
            self.load_list()
        elif isinstance(item, PersonResult):
            self.load_person(item.person.tmdb_id, item.person.name)

    @on(CastPane.Selected)
    def _on_person_selected(self, event: CastPane.Selected) -> None:
        if isinstance(event.item, PersonItem):
            self.load_person(event.item.person.tmdb_id, event.item.person.name)

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
        order = [
            DETAILS_PANE,
            REVIEWS_PANE,
            CAST_PANE,
            EPISODES_PANE,
            STATS_PANE,
            PLAYER_PANE,
        ]
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

    # ------------------------------------------------------------ trailer

    # Widgets folded away while a trailer plays. The picture is sized from
    # the pane, so every row and column these give back becomes real
    # resolution - hiding them roughly doubles the pixel count.
    CINEMA_HIDDEN = ("#left", "#search", "#tabs")

    def _set_cinema(self, on: bool) -> None:
        """Collapse the surrounding UI so the trailer fills the window."""
        for selector in self.CINEMA_HIDDEN:
            try:
                self.query_one(selector).display = not on
            except Exception:
                pass  # a widget may be gone during shutdown
        try:
            self.query_one(PosterPane).display = not on
        except Exception:
            pass
        self.refresh(layout=True)

    def stop_playback(self) -> None:
        self._stop_player.set()
        self._set_cinema(False)

    def action_play_trailer(self) -> None:
        """f7 toggles: play the trailer here, or stop one already running."""
        pane = self.query_one(PlayerPane)
        if not self._stop_player.is_set():
            # a run is in flight - treat f7 as stop
            self.stop_playback()
            pane.show_message(_("trailer_stopped"))
            return

        trailer = self._current.trailer if self._current else None
        if trailer is None:
            self.notify(_("no_trailer"), severity="warning")
            return
        if missing := missing_tools():
            pane.show_message(
                _("trailer_missing_tools", tools=", ".join(missing)), "red"
            )
            self.query_one("#info", TabbedContent).active = PLAYER_PANE
            return

        self.query_one("#info", TabbedContent).active = PLAYER_PANE
        self._set_cinema(True)
        set_enhance(self.config.trailer_sharpen)
        pane.show_message(_("trailer_resolving"))
        self._stop_player = threading.Event()  # clear: a run is now in flight
        # The grid is measured inside the worker: hiding the poster above
        # only takes effect after Textual relayouts, and reading it here
        # would size the picture to the old, smaller pane.
        self.run_trailer(trailer.url, self._stop_player)

    @work(thread=True, exclusive=True, group="player")
    def run_trailer(self, url: str, stop: threading.Event) -> None:
        """Decoding and rendering are blocking work, so this is a thread
        worker that paints through call_from_thread."""
        pane = self.query_one(PlayerPane)
        try:
            stream_url, audio_url = resolve_streams(url)
            if stop.is_set():
                return
            self.call_from_thread(pane.show_message, _("trailer_buffering"))
            # Layout has settled by now, so this is the real pane size.
            cols, rows = self.call_from_thread(pane.grid)
            # A separate audio stream is the better one when yt-dlp offers
            # it; otherwise the sound rides in the muxed video URL.
            with_audio = self.config.trailer_audio and audio_available()
            play(
                stream_url,
                lambda frame: self.call_from_thread(pane.show_frame, frame),
                cols,
                rows,
                frame_strips,
                stop=stop,
                audio_url=(audio_url or stream_url) if with_audio else None,
                # Once the letterbox bars are measured the picture is
                # wider than 16:9, so it gets a fresh grid to fill.
                regrid=lambda aspect: self.call_from_thread(pane.grid, aspect),
            )
        except TrailerError as exc:
            self.call_from_thread(pane.show_message, str(exc), "red")
            return
        finally:
            stop.set()
            self.call_from_thread(self._set_cinema, False)
        self.call_from_thread(pane.show_message, _("trailer_ended"))

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

    def _refresh_stats(self) -> None:
        self.query_one(StatsPane).show_stats(self._service.stats())

    def action_toggle_watched(self) -> None:
        if self._current is not None:
            self.mark_watched(self._current)

    @work(exclusive=True, group="watched")
    async def mark_watched(self, movie: Movie) -> None:
        # Async because a series with no episode_run_time needs one
        # season fetched to work out how long it actually is.
        marked = await self._service.watched_toggle(movie)
        self.notify(
            _(
                "watched_added" if marked else "watched_removed",
                title=movie.title,
            )
        )
        self._refresh_stats()
        if self._section == WATCHED_TAB:
            self.load_list()

    @work(exclusive=True, group="updates")
    async def check_series_updates(self) -> None:
        """Runs once on mount; silent unless something actually grew."""
        if self.config.offline:
            return
        try:
            updates = await self._service.series_updates()
        except Exception:
            return  # a background nicety must never surface as an error
        for update in updates:
            self.notify(
                _("new_episodes", title=update.hit.title, count=update.added),
                title=_("watchlist"),
                timeout=12,
            )

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

    def action_toggle_filters(self) -> None:
        """Filters sit behind one key so the default view stays clean."""
        if self._section != CATEGORIES_TAB:
            self._filters_open = True
            self.query_one("#tabs", Tabs).active = CATEGORIES_TAB
            return
        self._filters_open = not self._filters_open
        self._sync_controls()
        if self._filters_open:
            self.query_one("#sort", Select).focus()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_focus_results(self) -> None:
        self.query_one(ResultsList).focus()

    def action_next_section(self) -> None:
        self.query_one("#tabs", Tabs).action_next_tab()

    def action_purge_cache(self) -> None:
        self._service.purge_cache()
        self.notify(_("cache_cleared"))
