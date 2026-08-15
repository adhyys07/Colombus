"""Poster pane.

`textual-image` picks a rendering backend by probing the terminal. That probe
can pick a graphics protocol the terminal advertises but does not actually
draw, so the backend is overridable with COLOMBUS_POSTER_PROTOCOL.
"""

from __future__ import annotations

import io

from PIL import Image as PILImage
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from render import message_renderable

from widgets.artposter import AsciiImage, BrailleImage

# Character art needs no graphics protocol, so it is always available.
BACKENDS = {"ascii": AsciiImage, "braille": BrailleImage}

try:  # optional dependency
    from textual_image.widget import (
        HalfcellImage,
        Image as AutoImage,
        SixelImage,
        TGPImage,
        UnicodeImage,
    )

    BACKENDS |= {
        "auto": AutoImage,
        "tgp": TGPImage,
        "kitty": TGPImage,
        "sixel": SixelImage,
        "halfcell": HalfcellImage,
        "unicode": UnicodeImage,
    }
except ImportError:  # pragma: no cover - depends on the install
    pass

# A terminal cell is roughly twice as tall as it is wide.
CELL_ASPECT = 2.0


class PosterPane(Container):
    BORDER_TITLE = "Poster"

    def __init__(self, *args, protocol: str = "auto", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.protocol = protocol
        self._aspect: float | None = None

    def compose(self) -> ComposeResult:
        yield Static(message_renderable("No poster"), id="poster-body")

    def _backend(self):
        if self.protocol == "none":
            return None
        # Character art is the last resort: it always renders.
        return (
            BACKENDS.get(self.protocol)
            or BACKENDS.get("auto")
            or BACKENDS["braille"]
        )

    def _fit(self, widget) -> None:
        """Size the image to the poster's aspect ratio inside the pane."""
        if not self._aspect:
            return
        height = max(1, self.size.height)
        width = max(1, round(height * self._aspect * CELL_ASPECT))
        if width > self.size.width:                # too wide: fit by width instead
            width = max(1, self.size.width)
            height = max(1, round(width / (self._aspect * CELL_ASPECT)))
        widget.styles.width = width
        widget.styles.height = height

    async def show(self, data: bytes | None, caption: str = "") -> None:
        await self.remove_children()
        self._aspect = None
        backend = self._backend()

        if data and backend is not None:
            try:
                image = PILImage.open(io.BytesIO(data))
                image.load()
                self._aspect = image.width / image.height
                widget = backend(image, id="poster-body")
                self._fit(widget)
                await self.mount(widget)
                return
            except Exception:
                # Backend or terminal can't render pixels; fall back to text.
                self._aspect = None
                await self.remove_children()

        placeholder = caption or ("Poster unavailable" if data is None else "No poster")
        await self.mount(Static(message_renderable(placeholder), id="poster-body"))

    def on_resize(self) -> None:
        if self._aspect and self.children:
            self._fit(self.children[0])

    async def clear(self) -> None:
        await self.show(None, "No poster")
