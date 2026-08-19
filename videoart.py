from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from rich.color import Color
from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip

UPPER_HALF = "▀"
# Six bits per channel. Visually indistinguishable in a terminal, but it
# roughly doubles throughput: more cells compare equal, so runs group and
# the style cache stays small.
COLOUR_MASK = 0xFC
_STYLE_CACHE: dict[tuple[int, int], Style] = {}
_CACHE_LIMIT = 200_000

# Downscaling a 16:9 frame into a cell grid throws away most of the
# pixels, which softens edges badly at this size. LANCZOS keeps the detail
# that survives, then a light unsharp mask puts the edge contrast back so
# faces and text read at a glance. Saturation is nudged up because the
# 6-bit quantisation below flattens colour slightly.
#
# Deliberately no autocontrast: it is computed per frame, so a bright
# object entering the shot would re-map the whole picture and the video
# would pump between frames.
SHARPEN_PERCENT = 80
SHARPEN_THRESHOLD = 2
SATURATION = 1.15
_ENHANCE = True


def set_enhance(enabled: bool) -> None:
    """Turn the sharpening pass on or off (COLOMBUS_TRAILER_SHARPEN)."""
    global _ENHANCE
    _ENHANCE = enabled


def _packed_style(top: int, bottom: int) -> Style:
    """Style for one cell, keyed by packed 0xRRGGBB ints."""
    key = (top, bottom)
    style = _STYLE_CACHE.get(key)
    if style is None:
        if len(_STYLE_CACHE) >= _CACHE_LIMIT:
            _STYLE_CACHE.clear()
        style = Style(
            color=Color.from_rgb(top >> 16, (top >> 8) & 0xFF, top & 0xFF),
            bgcolor=Color.from_rgb(
                bottom >> 16, (bottom >> 8) & 0xFF, bottom & 0xFF
            ),
        )
        _STYLE_CACHE[key] = style
    return style


def frame_strips(image: Image.Image, cols: int, rows: int) -> list[Strip]:
    """Render a frame as `rows` Strips of `cols` half-block cells.

    Effective resolution is cols x (rows * 2) pixels in full colour.
    """
    if cols < 1 or rows < 1:
        return []

    if _ENHANCE:
        resized = image.convert("RGB").resize((cols, rows * 2), Image.LANCZOS)
        resized = resized.filter(
            ImageFilter.UnsharpMask(
                radius=1, percent=SHARPEN_PERCENT, threshold=SHARPEN_THRESHOLD
            )
        )
        resized = ImageEnhance.Color(resized).enhance(SATURATION)
    else:
        resized = image.convert("RGB").resize((cols, rows * 2), Image.BILINEAR)
    pixels = np.asarray(resized, dtype=np.uint32) & COLOUR_MASK
    # pack to 0xRRGGBB so a cell is two ints and comparisons are cheap
    packed = (pixels[:, :, 0] << 16) | (pixels[:, :, 1] << 8) | pixels[:, :, 2]
    top_rows = packed[0::2]
    bottom_rows = packed[1::2]

    strips: list[Strip] = []
    for row in range(rows):
        top = top_rows[row]
        bottom = bottom_rows[row]
        if cols > 1:
            changed = (top[1:] != top[:-1]) | (bottom[1:] != bottom[:-1])
            starts = np.concatenate(([0], np.flatnonzero(changed) + 1))
        else:
            starts = np.array([0])
        ends = np.concatenate((starts[1:], [cols]))

        segments = [
            Segment(
                UPPER_HALF * int(end - start),
                _packed_style(int(top[start]), int(bottom[start])),
            )
            for start, end in zip(starts, ends)
        ]
        strips.append(Strip(segments, cols))
    return strips


def cache_size() -> int:
    return len(_STYLE_CACHE)
