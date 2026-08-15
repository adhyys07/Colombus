"""The Textual application shell."""

from __future__ import annotations

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input

from config import Config
from models import SearchHit
from service import MovieService
from sources import TMDBError
from widgets import DetailPane, PosterPane, ResultsList


class ColombusApp(App[None]):
    CSS_PATH = "app.tcss"
    TITLE = "Colombus"
    SUB_TITLE = "terminal movie browser"

    # Deliberately no bare-letter bindings: they would be swallowed while
    # typing in the search Input.
    BINDINGS = [
        ("ctrl+s", "focus_search", "Search"),
        ("escape", "focus_results", "Results"),
        ("ctrl+r", "purge_cache", "Clear cache"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, config: Config, initial_query: str = "") -> None:
        super().__init__()
        self.config = config
        self._service = MovieService(config)
        self._initial_query = initial_query.strip()
        self._warned_omdb = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Search for a film...", id="search")
        with Horizontal(id="body"):
            yield ResultsList(id="results")
            with Vertical(id="right"):
                yield PosterPane(id="poster")
                yield DetailPane(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        search = self.query_one("#search", Input)
        if self._initial_query:
            search.value = self._initial_query
            self.search(self._initial_query)
        else:
            search.focus()

    async def on_unmount(self) -> None:
        await self._service.aclose()

    # ------------------------------------------------------------------ workers

    @work(exclusive=True, group="search")
    async def search(self, query: str) -> None:
        results = self.query_one(ResultsList)
        detail = self.query_one(DetailPane)
        detail.show_message(f"Searching for '{query}'...")

        try:
            hits = await self._service.search(query)
        except TMDBError as exc:
            await results.show([])
            detail.show_message(str(exc), "red")
            return

        await results.show(hits)
        if not hits:
            await self.query_one(PosterPane).clear()
            detail.show_message(f"No films found for '{query}'.")
            return
        results.focus()

    @work(exclusive=True, group="detail")
    async def load_details(self, hit: SearchHit) -> None:
        detail = self.query_one(DetailPane)
        poster = self.query_one(PosterPane)
        detail.show_message(f"Loading {hit.label}...")

        try:
            movie = await self._service.details(hit.tmdb_id)
        except TMDBError as exc:
            detail.show_message(str(exc), "red")
            return

        detail.show_movie(movie)
        self._warn_once_about_omdb()
        data = await self._service.poster(movie.poster_path or hit.poster_path)
        await poster.show(data, movie.label)

    # ----------------------------------------------------------------- messages

    @on(Input.Submitted, "#search")
    def _on_search_submitted(self, event: Input.Submitted) -> None:
        if query := event.value.strip():
            self.search(query)

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

    def action_purge_cache(self) -> None:
        self._service.purge_cache()
        self.notify("Cached responses and posters cleared.")
