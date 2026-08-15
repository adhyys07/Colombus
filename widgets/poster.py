"""Poster pane.

Renders real pixels when textual-image and the terminal both cooperate
(Kitty graphics / Sixel), and degrades to a text placeholder otherwise.
"""

from __future__ import annotations

import io

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from render import message_renderable

try:  # optional dependency
    from textual_image.widget import Image as _Image
except ImportError:  # pragma: no cover - depends on the install
    _Image = None


class PosterPane(Container):
    BORDER_TITLE = "Poster"

    def compose(self) -> ComposeResult:
        yield Static(message_renderable("No poster"), id="poster-body")

    async def show(self, data: bytes | None, caption: str = "") -> None:
        await self.remove_children()

        if data and _Image is not None:
            try:
                await self.mount(_Image(io.BytesIO(data), id="poster-body"))
                return
            except Exception:
                # Terminal or backend can't render pixels; fall through to text.
                await self.remove_children()

        placeholder = caption or ("Poster unavailable" if data is None else "No poster")
        await self.mount(Static(message_renderable(placeholder), id="poster-body"))

    async def clear(self) -> None:
        await self.show(None, "No poster")
