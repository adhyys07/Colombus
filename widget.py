from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from config import Config
from models import MOVIE, TV, SearchHit
from service import MovieService

BG = "#0c0c0c"
FG = "#cccccc"
DIM = "#6a6a6a"
ACCENT = "#4ec9b0"
GREEN = "#6a9955"
YELLOW = "#d7ba7d"
RED = "#f14c4c"
WHITE = "#eaeaea"

FONTS = ("Cascadia Mono", "Consolas", "Courier New")
ROWS = 10
BAR_WIDTH = 9
REFRESH_SECONDS = 900


@dataclass
class Mode:
    label: str
    kind: str  # "trending" | "genre"
    media_type: str = MOVIE
    window: str = "week"
    genre_id: int | None = None


def _pick_font(root: tk.Misc) -> str:
    from tkinter import font as tkfont

    available = set(tkfont.families(root))
    for name in FONTS:
        if name in available:
            return name
    return "TkFixedFont"


def _bar(score: float) -> tuple[str, str]:
    """A 0-10 score as a block bar plus the colour tag to draw it in."""
    filled = max(0, min(BAR_WIDTH, round(score / 10 * BAR_WIDTH)))
    bar = "█" * filled + "░" * (BAR_WIDTH - filled)
    if score >= 7.0:
        return bar, "good"
    if score >= 5.0:
        return bar, "ok"
    return bar, "bad"


class MovieWidget:
    """Terminal-styled always-on-top panel driven by MovieService."""

    def __init__(
        self,
        config: Config,
        media_type: str = MOVIE,
        refresh: int = REFRESH_SECONDS,
    ) -> None:
        self.config = config
        self.media_type = media_type
        self.refresh = max(60, refresh)
        self.modes: list[Mode] = [
            Mode("trending / today", "trending", media_type, "day"),
            Mode("trending / this week", "trending", media_type, "week"),
        ]
        self.index = 0
        self.hits: list[SearchHit] = []
        self.status = "starting..."

        self._requests: queue.Queue[Mode | None] = queue.Queue()
        self._results: queue.Queue[tuple[str, object]] = queue.Queue()
        self._stop = threading.Event()
        self._last_fetch = 0.0

        self.root = tk.Tk()
        self._build_ui()
        self._restore_position()
        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()
        self._request(self.modes[self.index])
        self.root.after(80, self._poll)

    # --------------------------------------------------------------------- ui

    def _build_ui(self) -> None:
        root = self.root
        root.title("Colombus")
        root.overrideredirect(True)          # no title bar: it is a widget
        root.attributes("-topmost", True)
        root.configure(bg=BG)

        font_name = _pick_font(root)
        self.font = (font_name, 10)
        self.font_bold = (font_name, 10, "bold")

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=10, pady=(8, 0))
        self.title_label = tk.Label(
            header, text="colombus", font=self.font_bold, fg=ACCENT, bg=BG
        )
        self.title_label.pack(side="left")
        self.mode_label = tk.Label(
            header, text="", font=self.font, fg=DIM, bg=BG
        )
        self.mode_label.pack(side="left", padx=(8, 0))
        close = tk.Label(header, text="✕", font=self.font_bold, fg=DIM, bg=BG)
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self.quit())
        close.bind("<Enter>", lambda _e: close.configure(fg=RED))
        close.bind("<Leave>", lambda _e: close.configure(fg=DIM))

        self.body = tk.Text(
            root,
            width=54,
            height=ROWS + 1,
            bg=BG,
            fg=FG,
            font=self.font,
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=6,
            cursor="arrow",
            wrap="none",
        )
        self.body.pack(fill="both", expand=True)
        self.body.configure(state="disabled")
        for tag, colour in (
            ("rank", DIM), ("title", WHITE), ("year", DIM),
            ("good", GREEN), ("ok", YELLOW), ("bad", RED), ("dim", DIM),
        ):
            self.body.tag_configure(tag, foreground=colour)

        self.footer = tk.Label(
            root,
            text="[r]efresh  [tab] next  [o]pen  [q]uit",
            font=self.font,
            fg=DIM,
            bg=BG,
            anchor="w",
        )
        self.footer.pack(fill="x", padx=10, pady=(0, 8))

        # dragging by the header, since there is no title bar
        for widget in (header, self.title_label, self.mode_label):
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        root.bind("<KeyPress-q>", lambda _e: self.quit())
        root.bind("<Escape>", lambda _e: self.quit())
        root.bind("<KeyPress-r>", lambda _e: self._request(self._mode, force=True))
        root.bind("<Tab>", lambda _e: self._cycle())
        root.bind("<KeyPress-o>", lambda _e: self._open_current())
        root.focus_force()

    @property
    def _mode(self) -> Mode:
        return self.modes[self.index % len(self.modes)]

    def _drag_start(self, event: tk.Event) -> None:
        self._drag_origin = (event.x_root, event.y_root)
        self._win_origin = (self.root.winfo_x(), self.root.winfo_y())

    def _drag_move(self, event: tk.Event) -> None:
        dx = event.x_root - self._drag_origin[0]
        dy = event.y_root - self._drag_origin[1]
        self.root.geometry(f"+{self._win_origin[0] + dx}+{self._win_origin[1] + dy}")

    # ------------------------------------------------------------- rendering

    def render(self) -> None:
        self.mode_label.configure(text=f"~ {self._mode.label}")
        body = self.body
        body.configure(state="normal")
        body.delete("1.0", "end")

        if not self.hits:
            body.insert("end", f"\n  {self.status}\n", "dim")
        else:
            for position, hit in enumerate(self.hits[:ROWS], start=1):
                title = hit.title
                if len(title) > 30:
                    title = title[:29] + "…"
                body.insert("end", f" {position:02d}  ", "rank")
                body.insert("end", f"{title:<30}", "title")
                body.insert("end", f" {hit.year or '----':>4}  ", "year")
                bar, tag = _bar(hit.vote_average)
                body.insert("end", bar, tag)
                body.insert("end", f" {hit.vote_average:>4.1f}\n", tag)

        body.configure(state="disabled")
        self.footer.configure(
            text=f"[r]efresh  [tab] next  [o]pen  [q]uit     {self.status}"
        )

    # ---------------------------------------------------------------- worker

    def _request(self, mode: Mode, force: bool = False) -> None:
        if force or time.time() - self._last_fetch > 1:
            self.status = "loading..."
            self.render()
            self._requests.put(mode)

    def _cycle(self) -> str:
        self.index = (self.index + 1) % len(self.modes)
        self._request(self._mode, force=True)
        return "break"          # stop Tab from moving focus

    def _open_current(self) -> None:
        if self.hits:
            hit = self.hits[0]
            webbrowser.open(
                f"https://www.themoviedb.org/{hit.media_type}/{hit.tmdb_id}"
            )

    def _next_request(self) -> Mode | None:
        """Blocking get that still notices _stop, so the process can exit.

        A bare queue.get() parks a thread-pool thread forever, and
        concurrent.futures joins those at interpreter exit - which hangs
        the whole process on shutdown.
        """
        while not self._stop.is_set():
            try:
                return self._requests.get(timeout=0.25)
            except queue.Empty:
                continue
        return None

    def _run_worker(self) -> None:
        asyncio.run(self._work())

    async def _work(self) -> None:
        loop = asyncio.get_running_loop()
        async with MovieService(self.config) as svc:
            # Genres become extra modes once they arrive.
            try:
                genres = await svc.genres(self.media_type)
                self._results.put(("genres", genres[:8]))
            except Exception:
                pass

            while not self._stop.is_set():
                mode = await loop.run_in_executor(None, self._next_request)
                if mode is None:
                    break
                try:
                    if mode.kind == "genre":
                        hits = await svc.by_genre(self.media_type, mode.genre_id)
                    else:
                        hits = await svc.trending(self.media_type, mode.window)
                    self._results.put(("hits", hits))
                except Exception as exc:  # never kill the widget over a fetch
                    self._results.put(("error", str(exc).splitlines()[0]))

    def _poll(self) -> None:
        while True:
            try:
                kind, payload = self._results.get_nowait()
            except queue.Empty:
                break
            if kind == "hits":
                self.hits = payload
                self._last_fetch = time.time()
                self.status = f"updated {time.strftime('%H:%M')}"
            elif kind == "genres":
                self.modes.extend(
                    Mode(g.name.lower(), "genre", self.media_type, genre_id=g.tmdb_id)
                    for g in payload
                )
            elif kind == "error":
                self.status = payload[:40]
            self.render()

        if time.time() - self._last_fetch > self.refresh and self.hits:
            self._request(self._mode, force=True)
        self.root.after(200, self._poll)

    # -------------------------------------------------------------- lifecycle

    def _state_file(self) -> Path:
        return Path(self.config.cache_dir) / "widget.json"

    def _restore_position(self) -> None:
        try:
            state = json.loads(self._state_file().read_text(encoding="utf-8"))
            self.root.geometry(f"+{int(state['x'])}+{int(state['y'])}")
        except (OSError, ValueError, KeyError):
            self.root.update_idletasks()
            width = self.root.winfo_width()
            screen = self.root.winfo_screenwidth()
            self.root.geometry(f"+{max(0, screen - width - 40)}+60")

    def _save_position(self) -> None:
        try:
            self._state_file().parent.mkdir(parents=True, exist_ok=True)
            self._state_file().write_text(
                json.dumps({"x": self.root.winfo_x(), "y": self.root.winfo_y()}),
                encoding="utf-8",
            )
        except OSError:
            pass

    def quit(self) -> None:
        self._save_position()
        self._stop.set()
        self._requests.put(None)
        self.root.destroy()

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.mainloop()


def run_widget(config: Config, media_type: str = MOVIE, refresh: int = REFRESH_SECONDS):
    MovieWidget(config, media_type=media_type, refresh=refresh).run()
