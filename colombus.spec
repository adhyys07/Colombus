# PyInstaller spec for Colombus. Build with:  pyinstaller colombus.spec
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [("app.tcss", ".")], [], []
for pkg in ("textual", "textual_image", "rich"):
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
    excludes=["matplotlib", "numpy", "pytest"],  # tkinter is needed by widget.py
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="colombus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,          # a TUI needs a console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
