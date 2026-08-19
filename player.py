from __future__ import annotations

import atexit
import shutil
import subprocess
import time
import weakref
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
from PIL import Image

# This pin is load-bearing, and not only for old yt-dlp builds. The
# default clients do resolve on a current yt-dlp and advertise far better
# formats - separate opus audio, video past 1080p - but every one of those
# URLs answers 403 to ffmpeg: they are bound to a client handshake we
# cannot reproduce, and sending the matching User-Agent is not enough.
# The `android` client's muxed 360p stream is the only one that actually
# plays, so it stays pinned. Do not "upgrade" this without checking that
# ffprobe can still open the URL it returns.
PLAYER_CLIENTS = "youtube:player_client=android,web_safari"
# Muxed first, deliberately. A separate video+audio pair would carry
# better sound, but those formats are exactly the ones YouTube now blocks
# (see PLAYER_CLIENTS). yt-dlp -g prints one URL per selected stream, so
# resolve_streams still handles a pair should one ever become playable.
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


# Trailer audio arrives already peaking at full scale (measured +0.2 dBTP,
# mean -23.7 dB) with a very wide dynamic range (15.6 LU). There is no
# headroom, so plain gain just clips: the quiet dialogue is the problem,
# not the overall level.
#
# dynaudnorm normalises level over a moving window, which lifts the quiet
# passages without pushing the peaks any higher - measured +4.0 dB mean at
# a peak of -0.5 dB, where a flat 1.5x gain reached the ceiling for +3.5.
# A plain compressor was tried first and is a trap: without makeup gain it
# pulls the loud parts down faster than the gain lifts them (+0.2 dB net),
# and with makeup=6 it clips hard.
NORMALISE = "dynaudnorm=f=250:g=15"
# level=disabled matters: alimiter otherwise auto-levels its output back
# up to full scale after limiting, which throws away the headroom the
# limiter just bought. Off, it holds the ceiling at -0.26 dBFS.
LIMITER = "alimiter=limit=0.97:level=disabled"


def _volume_filter(volume: int) -> list[str]:
    """ffplay -af arguments for a volume percentage (100 = untouched).

    Above 100 the normaliser comes first so the boost works on an evened
    out signal, with the limiter last to catch whatever still overshoots.
    """
    if volume == 100:
        return []
    gain = volume / 100
    chain = (
        f"{NORMALISE},volume={gain:.2f},{LIMITER}"
        if volume > 100
        else f"volume={gain:.2f}"
    )
    return ["-af", chain]


class AudioTrack:
    """The trailer's sound, played by ffplay with no window.

    Terminal art carries video only, so audio rides alongside through the
    sound card. Both halves are paced against the wall clock, which keeps
    them together well enough for a trailer.
    """

    def __init__(self, stream_url: str, volume: int = 100) -> None:
        self.url = stream_url
        self.volume = volume
        self._proc: subprocess.Popen | None = None

    def start(self) -> bool:
        if not audio_available():
            return False
        try:
            self._proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-vn", "-autoexit",
                 # An audio dropout is far more noticeable than a dropped
                 # frame, so let the buffer grow without limit rather than
                 # underrun on a slow stretch of network.
                 #
                 # Only these two: ffplay's parser rejects the http
                 # protocol's -reconnect* options and exits on an unknown
                 # flag, which would leave the trailer silent. The video
                 # side gets its reconnects through STREAM_OPTIONS instead.
                 "-infbuf",
                 "-rw_timeout", OPEN_TIMEOUT_US,
                 *_volume_filter(self.volume),
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



class Letterbox:
    """Finds the black bars a widescreen trailer carries inside its frame.

    Most trailers are 2.39:1 pillar-boxed into a 16:9 stream, so around a
    quarter of every frame is black. Those rows cost real resolution: the
    grid is sized from the picture's aspect, so cropping them lets the
    remaining picture claim the width the bars were wasting.

    The bars are measured over several frames and then fixed for the rest
    of playback. Re-measuring per frame would let a dark shot pull the
    crop inwards and make the picture breathe.
    """

    SAMPLES = 20  # usable frames to look at before locking the crop
    BLACK = 18  # luma at or below this counts as bar, not picture
    MIN_BAR = 0.02  # ignore anything smaller; it is just a dark edge

    def __init__(self) -> None:
        self.box: tuple[int, int, int, int] | None = None
        self.locked = False
        self._seen: list[tuple[int, int, int, int]] = []

    def _measure(self, image: Image.Image) -> tuple[int, int, int, int] | None:
        grey = np.asarray(image.convert("L"))
        rows = np.flatnonzero(grey.max(axis=1) > self.BLACK)
        cols = np.flatnonzero(grey.max(axis=0) > self.BLACK)
        if rows.size == 0 or cols.size == 0:
            return None  # a fade to black tells us nothing
        return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1

    def feed(self, image: Image.Image) -> None:
        """Offer a frame towards the measurement, until the crop locks."""
        if self.locked:
            return
        box = self._measure(image)
        if box is None:
            return
        self._seen.append(box)
        if len(self._seen) < self.SAMPLES:
            return

        # The widest extent any sampled frame showed: a crop that never
        # cuts into real picture, whatever the darkest shot suggested.
        left = min(b[0] for b in self._seen)
        top = min(b[1] for b in self._seen)
        right = max(b[2] for b in self._seen)
        bottom = max(b[3] for b in self._seen)
        width, height = image.size
        trimmed = (width - (right - left)) / width, (height - (bottom - top)) / height
        self.box = (
            (left, top, right, bottom)
            if max(trimmed) >= self.MIN_BAR
            else None
        )
        self.locked = True

    def apply(self, image: Image.Image) -> Image.Image:
        return image.crop(self.box) if self.box else image

    @property
    def aspect(self) -> float | None:
        """Aspect of the cropped picture, once known."""
        if not self.locked or self.box is None:
            return None
        left, top, right, bottom = self.box
        return (right - left) / max(1, bottom - top)


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


def resolve_streams(
    video_url: str, timeout: int = RESOLVE_TIMEOUT
) -> tuple[str, str | None]:
    """Direct stream URLs for a video, as (video, audio).

    `audio` is None when yt-dlp fell back to a muxed stream, in which case
    the sound already rides in the video URL. Blocking; run it off the UI
    thread.
    """
    if shutil.which("yt-dlp") is None:
        raise TrailerError(
            "yt-dlp is not installed.\nInstall it with: pip install -U yt-dlp"
        )
    def run(extra: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["yt-dlp", "-g", "-f", FORMAT, "--no-warnings", *extra, video_url],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    try:
        result = run(["--extractor-args", PLAYER_CLIENTS])
    except subprocess.TimeoutExpired as exc:
        raise TrailerError("yt-dlp timed out resolving the trailer.") from exc
    except OSError as exc:
        raise TrailerError(f"Could not run yt-dlp: {exc}") from exc

    urls = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    if result.returncode != 0 or not urls:
        detail = (result.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else "no stream URL returned"
        raise TrailerError(
            f"yt-dlp could not resolve the trailer.\n{reason}\n"
            "An outdated yt-dlp is the usual cause: pip install -U yt-dlp"
        )
    # Two lines means a video+audio pair, in that order; one means muxed.
    return (urls[0], urls[1] if len(urls) > 1 else None)


def resolve_stream(video_url: str, timeout: int = RESOLVE_TIMEOUT) -> str:
    """The video URL alone, for callers that do not handle a pair."""
    return resolve_streams(video_url, timeout)[0]


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
    regrid=None,
    volume: int = 100,
) -> int:
    """Drive playback in real time, dropping frames rather than falling behind.

    `draw` is called with the rendered frame. Returns the number drawn.
    Rendering is the bottleneck, so on a slow terminal this shows fewer
    frames rather than playing in slow motion.

    With `audio_url`, ffplay plays the sound alongside. The audio clock and
    the video clock are both real time, so they stay together; the residual
    offset is ffplay's own startup latency.

    Black letterbox bars are detected over the first frames and cropped
    away. `regrid`, if given, is called once with the cropped picture's
    aspect and returns the (cols, rows) to use from then on - the picture
    is wider than 16:9 once the bars are gone, so it earns back the width
    they were occupying.
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
            audio = AudioTrack(audio_url, volume)
            audio.start()
        started = time.perf_counter()
        bars = Letterbox()
        bars.feed(first.image)
        draw(renderer(bars.apply(first.image), cols, rows))
        drawn = 1

        for frame in frames:
            if stop is not None and stop.is_set():
                break
            elapsed = time.perf_counter() - started
            if frame.pts > elapsed:
                time.sleep(min(frame.pts - elapsed, 1.0))  # ahead: wait
            elif frame.pts < elapsed - max_lag:
                continue  # behind: skip this frame entirely

            if not bars.locked:
                bars.feed(frame.image)
                if bars.locked and regrid is not None:
                    aspect = bars.aspect
                    if aspect is not None:
                        cols, rows = regrid(aspect)
            draw(renderer(bars.apply(frame.image), cols, rows))
            drawn += 1
    finally:
        if audio is not None:
            audio.stop()
    return drawn
