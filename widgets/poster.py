from __future__ import annotations
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static
import render

class Poster(Container):
    DEFAULT_CSS = """
    Poster {
        width: auto;
        height: 1fr;
        padding: 0 1;
    }
    Poster > Static {
        width:auto;
        height: auto;
    }
    """

    def __init__(self, * , cols:int = 28, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cols = cols
        self.title = ""
        self._image_widget = None
        self._fallback: Static | None = None

    def compose(self) -> ComposeResult:
        if render.BACKEND == "textual-image":
            from textual_image.widget import Image as TextualImage

            self._image_widget = TextualImage(id="poster-image")
        else:
            self._fallback = Static("", id="poster-fallback")
            yield self._fallback

    def show(self, data: bytes | None, title: str = "") -> None:
        self.title = title
        rows = render.rows_for_width(self.cols)

        if data and self._image_widget is not None:
            try:
                self._image_widget.image = render.open_image(data)
                self._image_widget.styles.width = self.cols
                self._image_widget.styles.height = rows
                return
            except Exception:
                self._swap_to_fallback()
        target = self._fallback
        if target is None:
            return
        if data and render.BACKEND != "none":
            ansi = render.chafa_ansi(data, self.cols, rows)
            if ansi:
                target.update(Text.from_ansi(ansi))
                return

        target.update(Text(render.placeholder(title, self.cols, rows), style="dim"))

    def clear(self) -> None:
        rows = render.rows_for_width(self.cols)
        if self._fallback is not None:
            self._fallback.update(Text(render.placeholder("", self.cols, rows), "dim"))

    def _swap_to_fallback(self) -> None:
        if self._fallback is not None:
            return
        if self._image_widget is not None:
            self._image_widget.remove()
            self._image_widget = None
        self._fallback = Static("", id="poster-fallback")
        self.mount(self._fallback)