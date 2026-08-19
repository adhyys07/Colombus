from __future__ import annotations

import atexit
import shutil
import subprocess
import time
import weakref
from collections.abc import Iterator
from dataclasses import dataclass

from PIL import Image

# The bundled extractor breaks against YouTube's bot checks on older
# yt-dlp builds; these clients still resolve. Harmless on current ones.
PLAYER_CLIENTS = "youtube:player_client=android,web_safari"
FORMAT = "best[height<=360]/best[height<=480]/best"
RESOLVE_TIMEOUT = 90
OPEN_TIMEOUT_US = "15000000"  # ffmpeg rw_timeout, in microseconds
# googlevideo drops long-lived connections now and then; without these a
# transient hiccup ends playback with a bare "I/O error".
STREAM_OPTIONS = {
    "rw_timeout": OPEN_TIMEOUT_US,
    "reconnect": "1",
    "reconnect_streamed": "1",
    "reconnect_on_network_error": "1",
    "reconnect_delay_max": "5",
}


class TrailerError(RuntimeError):
    """Playback could not start, with a reason worth showing the user."""


# Every live ffplay is tracked so none can outlive the app: an orphaned
# audio process would keep playing with nothing on screen.
_LIVE_AUDIO: weakref.WeakSet[AudioTrack] = weakref.WeakSet()


@atexit.register
def _stop_all_audio() -> None:
    for track in list(_LIVE_AUDIO):
        track.stop()


def audio_available() -> bool:
    return shutil.which("ffplay") is not None


class AudioTrack:
    """The trailer's sound, played by ffplay with no window.

    Terminal art carries video only, so audio rides alongside through the
    sound card. Both halves are paced against the wall clock, which keeps
    them together well enough for a trailer.
    """

    def __init__(self, stream_url: str) -> None:
        self.url = stream_url
        self._proc: subprocess.Popen | None = None

    def start(self) -> bool:
        if not audio_available():
            return False
        try:
            self._proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-vn", "-autoexit",
                 "-loglevel", "error", self.url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            self._proc = None
            return False
        _LIVE_AUDIO.add(self)
        return True

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    def __enter__(self) -> AudioTrack:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()


@dataclass
class Frame:
    """A decoded frame plus the moment it should be shown."""

    image: Image.Image
    pts: float


def missing_tools() -> list[str]:
    """Names of the tools needed for playback that are not installed."""
    missing = []
    if shutil.which("yt-dlp") is None:
        missing.append("yt-dlp")
    try:
        import av  # noqa: F401
    except ImportError:
        missing.append("av (PyAV)")
    return missing


def resolve_stream(video_url: str, timeout: int = RESOLVE_TIMEOUT) -> str:
    """Ask yt-dlp for a direct stream URL. Blocking; run it off the UI thread."""
    if shutil.which("yt-dlp") is None:
        raise TrailerError(
            "yt-dlp is not installed.\nInstall it with: pip install -U yt-dlp"
        )
    try:
        result = subprocess.run(
            [
                "yt-dlp", "-g", "-f", FORMAT, "--no-warnings",
                "--extractor-args", PLAYER_CLIENTS, video_url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise TrailerError("yt-dlp timed out resolving the trailer.") from exc
    except OSError as exc:
        raise TrailerError(f"Could not run yt-dlp: {exc}") from exc

    url = (result.stdout or "").strip().splitlines()
    if result.returncode != 0 or not url:
        detail = (result.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else "no stream URL returned"
        raise TrailerError(
            f"yt-dlp could not resolve the trailer.\n{reason}\n"
            "An outdated yt-dlp is the usual cause: pip install -U yt-dlp"
        )
    return url[0]


def iter_frames(stream_url: str, stop=None) -> Iterator[Frame]:
    """Decode a stream, yielding frames with their presentation times.

    `stop` is any object with is_set(); decoding ends as soon as it is set.
    """
    try:
        import av
    except ImportError as exc:  # pragma: no cover - guarded by missing_tools
        raise TrailerError("PyAV is not installed (pip install av).") from exc

    try:
        container = av.open(stream_url, options=dict(STREAM_OPTIONS))
    except Exception as exc:  # av raises a family of errors
        raise TrailerError(f"Could not open the video stream: {exc}") from exc

    try:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for frame in container.decode(stream):
            if stop is not None and stop.is_set():
                return
            yield Frame(image=frame.to_image(), pts=float(frame.time or 0.0))
    except Exception:
        # The stream died mid-play despite reconnects. Whatever has been
        # shown stays on screen; ending quietly beats a wall of URL.
        return
    finally:
        container.close()


def play(
    stream_url: str,
    draw,
    cols: int,
    rows: int,
    renderer,
    stop=None,
    max_lag: float = 0.15,
    audio_url: str | None = None,
) -> int:
    """Drive playback in real time, dropping frames rather than falling behind.

    `draw` is called with the rendered frame. Returns the number drawn.
    Rendering is the bottleneck, so on a slow terminal this shows fewer
    frames rather than playing in slow motion.

    With `audio_url`, ffplay plays the sound alongside. The audio clock and
    the video clock are both real time, so they stay together; the residual
    offset is ffplay's own startup latency.
    """
    audio: AudioTrack | None = None
    drawn = 0
    try:
        frames = iter_frames(stream_url, stop=stop)
        first = next(frames, None)
        if first is None:
            return 0

        # Start sound only once the first frame is decoded, so the two do
        # not begin a decode-time apart.
        if audio_url:
            audio = AudioTrack(audio_url)
            audio.start()
        started = time.perf_counter()
        draw(renderer(first.image, cols, rows))
        drawn = 1

        for frame in frames:
            if stop is not None and stop.is_set():
                break
            elapsed = time.perf_counter() - started
            if frame.pts > elapsed:
                time.sleep(min(frame.pts - elapsed, 1.0))  # ahead: wait
            elif frame.pts < elapsed - max_lag:
                continue  # behind: skip this frame entirely
            draw(renderer(frame.image, cols, rows))
            drawn += 1
    finally:
        if audio is not None:
            audio.stop()
    return drawn
