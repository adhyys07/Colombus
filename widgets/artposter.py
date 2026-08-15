"""Character-art poster backends.

Neither needs a terminal graphics protocol - they are just coloured text, so
they work anywhere, including the plain Windows console.

  ascii    one character per cell, picked from a density ramp
  braille  2x4 dithered dots per cell, so roughly 8x the detail
"""

from __future__ import annotations

from PIL import Image as PILImage, ImageOps
from rich.color import Color
from rich.console import RenderableType
from rich.style import Style
from rich.text import Text
from textual.widget import Widget

# Dark to light.
RAMP = " .:-=+*#%@"

# Braille dot bit for each (x, y) position inside a 2x4 cell.
DOTS = {
    (0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (0, 3): 0x40,
    (1, 0): 0x08, (1, 1): 0x10, (1, 2): 0x20, (1, 3): 0x80,
}
BRAILLE_BASE = 0x2800


def _luminance(rgb: tuple[int, int, int]) -> float:
    red, green, blue = rgb
    return (0.299 * red + 0.587 * green + 0.114 * blue) / 255


def ascii_art(image: PILImage.Image, cols: int, rows: int) -> Text:
    """One ramp character per cell, tinted with that cell's colour."""
    rgb = image.convert("RGB").resize((cols, rows))
    # Posters are often very dark; stretch the range so the ramp uses it all.
    grey = ImageOps.autocontrast(rgb.convert("L"), cutoff=2)
    colours = list(rgb.getdata())
    levels = list(grey.getdata())

    text = Text(no_wrap=True)
    for y in range(rows):
        for x in range(cols):
            offset = y * cols + x
            index = min(len(RAMP) - 1, int(levels[offset] / 255 * len(RAMP)))
            text.append(RAMP[index], Style(color=Color.from_rgb(*colours[offset])))
        if y < rows - 1:
            text.append("\n")
    return text


def braille_art(image: PILImage.Image, cols: int, rows: int) -> Text:
    """2x4 dots per cell, tinted with the cell's average colour.

    How many dots light up comes from the cell's overall brightness, and
    *which* ones from ranking the eight sub-pixels. That keeps edges in the
    right place without a global threshold, which would black out a dark
    poster or white out a bright one.
    """
    rgb = image.convert("RGB").resize((cols * 2, rows * 4))
    grey = ImageOps.autocontrast(rgb.convert("L"), cutoff=2)
    colours = list(rgb.getdata())
    levels = list(grey.getdata())
    stride = cols * 2

    text = Text(no_wrap=True)
    for cell_y in range(rows):
        for cell_x in range(cols):
            samples = []
            red = green = blue = 0
            for (dx, dy), bit in DOTS.items():
                offset = (cell_y * 4 + dy) * stride + (cell_x * 2 + dx)
                samples.append((levels[offset], bit))
                pixel = colours[offset]
                red += pixel[0]
                green += pixel[1]
                blue += pixel[2]

            lit = round(sum(level for level, _ in samples) / 8 / 255 * 8)
            samples.sort(key=lambda pair: pair[0], reverse=True)
            mask = 0
            for _, bit in samples[:lit]:
                mask |= bit

            colour = Color.from_rgb(red / 8, green / 8, blue / 8)
            text.append(chr(BRAILLE_BASE + mask), Style(color=colour))
        if cell_y < rows - 1:
            text.append("\n")
    return text


class ArtImage(Widget):
    """Renders a PIL image as coloured character art, sized to the widget."""

    MODE = "ascii"

    def __init__(self, image: PILImage.Image, id: str | None = None) -> None:
        super().__init__(id=id)
        self._image = image

    def render(self) -> RenderableType:
        cols, rows = self.size.width, self.size.height
        if cols < 1 or rows < 1:
            return Text("")
        draw = braille_art if self.MODE == "braille" else ascii_art
        return draw(self._image, cols, rows)

    def on_resize(self) -> None:
        self.refresh()


class AsciiImage(ArtImage):
    MODE = "ascii"


class BrailleImage(ArtImage):
    MODE = "braille"
