"""Pane that plays a trailer as colour half-block art.

Frames are pushed in as ready-made Strips and returned straight from
render_line, which is Textual's fastest drawing path - no Rich markup
parsing per frame.
"""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.widget import Widget

from i18n import _

# Above this the renderer stops keeping real time on a modest machine.
MAX_COLS = 200
MAX_ROWS = 60
# Trailers are 16:9; a half-block cell is one pixel wide and two tall, so
# the pixel grid is cols x (rows*2) and stays square.
ASPECT = 16 / 9


class PlayerPane(Widget):
    """Draws either a message or the current video frame."""

    DEFAULT_CSS = """
    PlayerPane {
        height: 1fr;
        background: $panel;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._strips: list[Strip] = []
        self._offset = 0
        self._message: tuple[str, str] | None = (_("trailer_idle"), "dim")
        # 0 = fill the pane; set from COLOMBUS_TRAILER_WIDTH
        self.max_cols = 0

    # ------------------------------------------------------------- sizing

    def grid(self) -> tuple[int, int]:
        """Largest 16:9 grid that fits the pane, capped for speed."""
        cap = self.max_cols or MAX_COLS
        width = max(10, min(cap, MAX_COLS, self.size.width))
        height = max(4, self.size.height)
        rows = max(2, min(MAX_ROWS, height, round(width / ASPECT / 2)))
        cols = max(10, min(width, cap, MAX_COLS, round(rows * 2 * ASPECT)))
        return cols, rows

    # ------------------------------------------------------------ content

    def show_frame(self, strips: list[Strip]) -> None:
        self._strips = strips
        self._message = None
        # keep the picture vertically centred in the pane
        self._offset = max(0, (self.size.height - len(strips)) // 2)
        self.refresh()

    def show_message(self, text: str, style: str = "dim") -> None:
        self._message = (text, style)
        self._strips = []
        self.refresh()

    # ------------------------------------------------------------ drawing

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        if self._message is not None:
            return self._message_line(y, width)

        index = y - self._offset
        if 0 <= index < len(self._strips):
            strip = self._strips[index]
            pad = max(0, (width - strip.cell_length) // 2)
            if pad:
                strip = Strip(
                    [Segment(" " * pad), *strip._segments], strip.cell_length + pad
                )
            return strip.adjust_cell_length(width)
        return Strip.blank(width)

    def _message_line(self, y: int, width: int) -> Strip:
        text, style = self._message or ("", "dim")
        lines = text.splitlines() or [""]
        top = max(0, (self.size.height - len(lines)) // 2)
        if not (top <= y < top + len(lines)):
            return Strip.blank(width)
        line = lines[y - top][:width]
        pad = max(0, (width - len(line)) // 2)
        return Strip(
            [Segment(" " * pad + line, Style.parse(style))], pad + len(line)
        ).adjust_cell_length(width)
