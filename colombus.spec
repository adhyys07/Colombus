# PyInstaller spec for Colombus. Build with:  pyinstaller colombus.spec
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [("app.tcss", ".")], [], []
# av ships compiled extensions plus bundled ffmpeg libraries; without
# collecting them the Trailer tab would fail only at runtime.
for pkg in ("textual", "textual_image", "rich", "av"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Backends are chosen at runtime, so nothing statically imports them.
hiddenimports += [
    "textual_image.widget.sixel",
    "textual_image.renderable.tgp",
    "textual_image.renderable.sixel",
    "textual_image.renderable.halfcell",
    "textual_image.renderable.unicode",
    "sources.tmdb",
    "sources.omdb",
    "sources.wikipedia",
    "widgets.detail",
    "widgets.poster",
    "widgets.results",
    "widgets.reviews",
    "widgets.cast",
    "widgets.episodes",
    "widgets.stats",
    "widgets.artposter",
    "widget",
    "player",
    "widgets.player",
    "videoart",
    "i18n",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "pytest"],  # numpy powers videoart; tkinter the widget
    noarchive=False,
)
pyz = PYZ(a.pure)

# A onedir build: the app runs straight from the folder.
#
# The onefile format packs everything into one .exe and unpacks it to %TEMP%
# on every launch. With numpy and av's ffmpeg libraries bundled that is well
# over 200MB per run, which fails outright on a nearly full disk:
#   Failed to extract av.libs\avcodec-*.dll: decompression resulted in
#   return code -1
# onedir needs no extraction, starts faster, and never touches %TEMP%.
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="colombus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # a TUI needs a console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="colombus",
)
