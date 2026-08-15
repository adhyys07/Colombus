from __future__ import annotations
import webbrowser
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Footer, Header, Input, Static

from config import Config
from models import Movie, SearchHit
from service import MovieService
from widgets import DetailPane, Poster, ResultsList

SEARCH_DEBOUNCE = 0.3
HIGHLIGHT_DEBOUNCE = 0.15

class Colombus(App):
    CSS_PATH = "app.tcss"
    TITLE = "Colombus"

    BINDINGS = [
        Binding("ctrl+c,q", "quit", "quit", priority=True),
        Binding("slash", "focus_search", "search"),
        Binding("escape", "focus_search", show=False),
        Binding("j", "cursor_down", "down", show=False),
        Binding("k", "cursor_up", "up", show=False),
        Binding("o", "open_imdb", "open imdb"),
        Binding("w", "open_wiki", "open wiki"),
        Binding("ctrl+r", "purge_cache", "clear cache"),
    ]

    def __init__(self, config: Config, initial_query: str = "") -> None:
        super().__init__()
        self.config = config
        self.service = MovieService(config)
        self.initial_query = initial_query
        self.current: Movie | None = None
        self._search_timer: Timer | None = None
        self._highlight_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Input(placeholder="search a film…", id="search")
                yield ResultsList(id="results")
                yield Static("", id="status")
            with Horizontal(id="detail-wrap"):
                yield Poster(cols=28, id="poster")
                yield DetailPane(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(DetailPane).show_message("Type to search.")
        search = self.query_one("#search", Input)
        if self.initial_query:
            search.value = self.initial_query
            self.run_search(self.initial_query)
        search.focus()
        if not self.config.has_omdb:
            self._status("no OMDB_API_KEY — critic scores disabled")

    async def on_unmount(self) -> None:
        await self.service.aclose()

    @on(Input.Changed, "#search")
    def _on_search_changed(self, event: Input.Changed) -> None:
        if self._search_timer is not None:
            self._search_timer.stop()
        query = event.value.strip()
        if len(query) < 2:
            return
        self._search_timer = self.set_timer(SEARCH_DEBOUNCE, lambda: self.run_search(query))

    @on(Input.Submitted, "#search")
    def _on_search_submitted(self, event: Input.Submitted) -> None:
        if self._search_timer is not None:
            self._search_timer.stop()
        self.run_search(event.value.strip())

    @on(ResultsList.Highlighted, "#results")
    def _on_highlighted(self, event: ResultsList.Highlighted) -> None:
        if self._highlight_timer is not None:
            self._highlight_timer.stop()
        hit = self.query_one(ResultsList).current_hit
        if hit is None:
            return
        self._highlight_timer = self.set_timer(
            HIGHLIGHT_DEBOUNCE, lambda: self.load_movie(hit)
        )

    @on(ResultsList.Selected, "#results")
    def _on_selected(self) -> None:
        self.query_one(DetailPane).focus()

    @work(exclusive=True, group="search")
    async def run_search(self, query: str) -> None:
        if not query:
            return
        self._status("searching…")
        try:
            hits = await self.service.search(query)
        except Exception as exc:
            self._status(f"search failed: {exc}", error=True)
            return

        await self.query_one(ResultsList).set_hits(hits)
        if hits:
            self._status(f"{len(hits)} result{'s' if len(hits) != 1 else ''}")
        else:
            self._status("no results found")
            self.query_one(DetailPane).show_message("No results found.")
            self.query_one(Poster).clear()

    @work(exclusive=True, group="detail")
    async def load_movie(self, hit: SearchHit) -> None:
        detail = self.query_one(DetailPane)
        poster = self.query_one(Poster)
        detail.show_message(f"Loading {hit.label}…")
        poster.clear()

        try:
            movie = await self.service.get_movie(hit.imdb_id)
        except Exception as exc:
            detail.show_message(f"Could not load that title: {exc}")
            return

        self.current = movie
        detail.show_movie(movie)
        self.load_poster(movie)

    @work(exclusive=True, group="poster")
    async def load_poster(self, movie: Movie) -> None:
        data = await self.service.poster(movie)
        if self.current is not None and self.current.imdb_id == movie.imdb_id:
            self.query_one(Poster).show(data, movie.title)

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_cursor_down(self) -> None:
        self.query_one(ResultsList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(ResultsList).action_cursor_up()

    def action_open_imdb(self) -> None:
        if self.current and self.current.imdb_url:
            webbrowser.open(self.current.imdb_url)
            self._status("opened IMDb")

    def action_open_wiki(self) -> None:
        if self.current and self.current.wiki_url:
            webbrowser.open(self.current.wiki_url)
            self._status("opened Wikipedia")

    def action_purge_cache(self) -> None:
        self.service.purge_cache()
        self._status("cache cleared")

    def _status(self, message: str, error: bool = False) -> None:
        widget = self.query_one("#status", Static)
        widget.update(message)
        widget.set(error, "error")
