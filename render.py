from __future__ import annotations
import io
import shutil
import subprocess
from typing import Literal

Backend = Literal[ "textual-image", "chafa", "none"]

CELL_ASPECT = 2.0
POSTER_ASPECT = 3 / 2

def _try_textual_image() -> bool:
    try:
        import textual_image.widget
    except Exception:
        return False

def detect_backend() -> Backend:
    if _try_textual_image():
        return "textual-image"
    if shutil.which("chafa"):
        return "chafa"
    return "none"

BACKEND : Backend = detect_backend()

def rows_for_width(cols:int) -> int:
    return max(1, round(cols * POSTER_ASPECT / CELL_ASPECT))

def open_image(data: bytes):
    from PIL import Image as PILImage
    img = PILimage.open(io.BytesIO(data))
    img.load()
    return img.convert("RGB")

def chafa_ansi(data: bytes, cols: int, rows: int, *, symbols: bool = False) -> str:
    cmd = [
        "chafa",
        f"--size={cols}x{rows}",
        "--clear=off",
        "--animate=off",
        "--polite=on",
        "-",
    ]
    if symbols:
        cmd.insert(1, "--format=symbols")
    try:
        proc = subprocess.run(
            cmd, input=data, capture_output=True, timeout=8, check=True
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    return proc.stdout.decode("utf-8", errors="replace")

def placeholder(title: str, cols: int, rows: int) -> str:
    cols = max(cols, 8)
    rows = max(rows, 3)
    inner = cols - 2
    lines = ["┌" + "─" * inner + "┐"]
    body = rows - 2
    label = (title[: inner - 2] if len(title) > inner - 2 else title).center(inner)
    for i in range(body):
        lines.append("│" + (label if i == body // 2 else " " * inner) + "│")
    lines.append("└" + "─" * inner + "┘")
    return "\n".join(lines)

def rich_poster(data: bytes | None, title: str, cols: int = 30):
    from rich.text import Text

    rows = rows_for_width(cols)

    if data and BACKEND == "textual-image":
        try:
            from textual_image.renderable import Image as RichImage
            return RichImage(open_image(data), width=cols, height=rows)
        except Exception:
            pass

    if data and shutil.which("chafa"):
        if ansi := chafa_ansi(data, cols, rows):
            return Text.from_ansi(ansi)
    return Text(placeholder(title, cols, rows), style="dim")