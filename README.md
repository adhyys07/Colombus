# Colombus

A terminal browser for films and series. Search TMDB, follow what's trending,
or mine a category by genre, language, decade and rating — then read the
facts, score bars, Wikipedia summary, full reviews, cast and per-episode
charts for anything you pick, without leaving your shell.

Posters render as real images where the terminal supports it, and as coloured
braille or ASCII art where it doesn't.

```
Colombus ───────────────────────────────────────────────────────────────────
 Search   Trending   Categories   Watchlist   Watched

 01  Blade Runner 2049          ⣿⣿⣿⣶⣤   Blade Runner 2049  (2017)  FILM
 02  Dune: Part Two             ⣿⣿⣿⣿⣷   Director  Denis Villeneuve
 03  Arrival                    ⢿⣿⣿⣿⡿   Runtime   2h 44m
                                          Stream    Prime Video, JioHotstar
```

## Install

```bash
pip install -r requirements.txt
cp .env.example .env
```

Add a TMDB credential to `.env` — either the v3 `TMDB_API_KEY` or the v4
`TMDB_ACCESS_TOKEN` (the token wins if both are set). Both are free from
<https://www.themoviedb.org/settings/api>.

`OMDB_API_KEY` is optional and adds the IMDb / Rotten Tomatoes / Metacritic
score line. Everything else works without it.

## Running

```bash
python main.py                    # start empty and search interactively
python main.py dune               # search on launch
python main.py --offline          # cache only, no network
python main.py --widget           # desktop widget instead of the full app
python main.py --purge-cache      # drop cached responses and posters, then exit
python main.py --env path/to/.env
```

## The interface

Five sections share one results list, switched with the tabs or `ctrl+t`:

| Section | What it shows |
| ------- | ------------- |
| **Search** | Titles — or people — matching your query |
| **Trending** | What's trending today or this week |
| **Categories** | Everything in a genre, industry, decade or rating band |
| **Watchlist** | Titles you saved with `ctrl+d`, newest first |
| **Watched** | Titles you marked seen with `f6` |

The **Movies / Series / Both / People** selector applies throughout, so you can
browse trending series, search across both at once, or look someone up and
open their filmography. Series get their own detail layout: creator, season
and episode counts, and the TV content rating in place of budget and revenue.

The right-hand pane carries six tabs, cycled with `f2`:

| Tab | Contents |
| --- | -------- |
| **Details** | Facts, score bars, overview, Wikipedia summary, where to watch |
| **Reviews** | Every TMDB review in full, with author, score and date; the tab shows the count |
| **Cast** | Billed roles — pick one to browse that person's filmography |
| **Episodes** | Season picker, a braille chart of episode ratings, then the episode list. Series only |
| **Stats** | Your watch history: hours, top genres, decades, recent titles |
| **Trailer** | The trailer played as full-colour half-block art, in the terminal |

## Keys

| Key | Action |
| --- | ------ |
| `ctrl+s` | focus the search box |
| `enter` | run the search |
| `↑` `↓` | move through results |
| `escape` | jump back to the results list |
| `ctrl+t` | next section |
| `ctrl+f` | show or hide the filter row |
| `f2` | cycle the right-hand tabs |
| `f3` | reload the list with recommendations for this title |
| `f4` | play the trailer in your browser |
| `f7` | play the trailer **in the terminal** (press again to stop) |
| `f5` | open the IMDb or TMDB page |
| `ctrl+d` | add to / remove from the watchlist |
| `f6` | mark watched / unmark |
| `ctrl+r` | clear the cache |
| `ctrl+q` | quit |

Nothing is bound to a bare letter, so typing in the search box never triggers
an action.

## Filtering

Categories opens with two dropdowns. `ctrl+f` reveals the rest — industry,
sort order, minimum rating and decade — and hides them again. Whatever is
active is named in the results border, so the state stays visible even with
the row collapsed.

The **industry** picker covers Hollywood, Bollywood, Tollywood, Kollywood,
Mollywood, Sandalwood, Bengali, Marathi and Punjabi cinema, plus British,
Korean, Japanese, Chinese, Nollywood and the major European industries. TMDB
has no notion of an industry, so each is an origin country paired with an
original language — and the pairing matters: filtering on India alone returns
Tamil and Malayalam films, so Bollywood is specifically India + Hindi. The
same list ends with language-only entries for when the country does not
matter.

Combining them works as you would expect: Bollywood + 7.0+ + 1990s returns
Dilwale Dulhania Le Jayenge, Kuch Kuch Hota Hai, Jo Jeeta Wohi Sikandar
and Satya.

Sorting by rating applies a vote-count floor automatically; without one TMDB
returns obscure titles carrying a single 10/10 vote. Series are filtered on
`first_air_date` rather than `primary_release_date`, which TMDB ignores for TV.

## Watchlist, watched and alerts

`ctrl+d` saves a title to the watchlist; `f6` marks it watched. Both live
in SQLite beside the cache and **survive `ctrl+r`** — clearing the cache never
touches your own data.

Marking a series watched records its total runtime. TMDB increasingly returns
an empty `episode_run_time`, so the per-episode length is averaged from the
first season's real episode runtimes and multiplied out. That makes the hours
total an estimate rather than an exact figure.

On startup, any series on your watchlist is checked against the episode count
last seen and you get a notification if it grew. The first sighting only
records a baseline, so you hear about episodes added after you started
tracking, not the whole back catalogue.

## Offline

```bash
python main.py --offline          # or COLOMBUS_OFFLINE=1
```

Serves everything from the cache and never opens a connection. Cached entries
are used **even past their expiry** — there is nothing to refresh from, so a
stale answer beats no answer. Anything not already cached says so plainly
instead of hanging, and the header is marked `offline`.

## Desktop widget

```bash
python main.py --widget           # trending films
python main.py --widget --widget-series
```

A borderless, always-on-top panel styled like a terminal, listing the top ten
trending titles with score bars. Drag it by the header; it remembers where you
left it and refreshes every 15 minutes.

| Key | Action |
| --- | ------ |
| `tab` | next mode — trending today, this week, then each genre |
| `r` | refresh now |
| `o` | open the top title on TMDB |
| `q` / `esc` | close |

This is a desktop widget, not a panel in the Windows 11 Widgets Board. That
board only accepts MSIX-packaged apps implementing the `IWidgetProvider` COM
interface through the Windows App SDK, which a Python project cannot provide.

## Playing trailers in the terminal

`f7` plays the selected title's trailer as colour art in the Trailer tab;
pressing it again stops. `f4` still opens it in a browser, which is what you
want to actually watch something.

It needs two extra tools, both optional to the rest of the app:

```bash
pip install -U yt-dlp av
```

yt-dlp resolves the YouTube trailer to a stream URL and PyAV decodes it. If
either is missing the tab says so instead of failing.

**Sound plays too.** The terminal only renders the picture, so the audio
track is handed to `ffplay` (part of ffmpeg) which plays it with no window.
Both halves are paced against the wall clock, so they stay together; the
residual offset is ffplay's own startup latency. Set
`COLOMBUS_TRAILER_AUDIO=0` for silent playback, and note that without ffmpeg
installed you simply get no sound rather than an error.

Frames are drawn with half-block characters (`▀`), which carry two
true-colour pixels per cell - the foreground paints the top pixel, the
background the bottom. That is why the picture is in full colour rather than
the monochrome dots braille would give. The poster hides while a trailer
plays, so the picture gets the whole right-hand column: on a 200-column
terminal that is about 123x70 pixels.

Playback keeps real time by **dropping frames** rather than running in slow
motion, so a smaller pane plays more smoothly than a large one. Cap the width
with `COLOMBUS_TRAILER_WIDTH=80` if you would rather have smoothness than
size.

If playback fails with a yt-dlp error, update it: `pip install -U yt-dlp`.
YouTube's bot checks break older builds regularly.

## Posters

`COLOMBUS_POSTER_PROTOCOL` picks how posters are drawn:

| Value | Looks like | Needs |
| ----- | ---------- | ----- |
| `auto` (default) | the best the terminal reports it can do | — |
| `tgp` / `sixel` / `kitty` | true pixels | Kitty graphics or Sixel support |
| `halfcell` / `unicode` | coloured blocks | any 24-bit colour terminal |
| `braille` | coloured 2×4 dot art, roughly 8× the detail of `ascii` | a braille-capable font |
| `ascii` | classic density-ramp character art, tinted per cell | any terminal |
| `none` | text placeholder | — |

`auto` detects capabilities but can be over-optimistic; if posters come out
blank or garbled, set `braille` explicitly.

## Languages and region

`COLOMBUS_LANGUAGE` sets the language of titles, overviews and genre names
from TMDB (`hi-IN`, `ta-IN`, `es-ES`, …). Where a translation has no overview,
the English one fills the gap rather than leaving the pane empty.

`COLOMBUS_UI_LANGUAGE` translates the app's own labels — `en`, `hi` and `es`
ship today, and partial catalogues fall back to English key by key, so a new
language can be filled in gradually. It is read at import, so changing it
needs a restart.

`COLOMBUS_REGION` decides which streaming services the Details tab reports —
set it to your own country (`IN`, `GB`, `DE`) or the providers will be
whoever serves the US.

Right-to-left scripts are not supported: terminals do not do bidirectional
layout, so Arabic and Hebrew would render incorrectly.

## Configuration

Every setting is an environment variable, read from the environment or `.env`.
For the packaged `.exe`, a `.env` beside the executable is picked up too.

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `TMDB_API_KEY` | — | TMDB v3 key (one credential required) |
| `TMDB_ACCESS_TOKEN` | — | TMDB v4 token, takes precedence |
| `OMDB_API_KEY` | — | optional extra ratings |
| `COLOMBUS_CACHE_DIR` | `~/.cache/colombus` | cache, watchlist and watch history |
| `COLOMBUS_CACHE_TTL` | `604800` (7 days) | cache lifetime in seconds; `0` never expires |
| `COLOMBUS_OFFLINE` | unset | `1` to serve only what is cached |
| `COLOMBUS_TRAILER_AUDIO` | `1` | `0` plays in-terminal trailers silently |
| `COLOMBUS_TRAILER_WIDTH` | `0` | cap the trailer width in cells; `0` fills the pane |
| `COLOMBUS_REGION` | `US` | where-to-watch region |
| `COLOMBUS_LANGUAGE` | `en-US` | language of TMDB content |
| `COLOMBUS_UI_LANGUAGE` | `en` | language of the app's own labels |
| `COLOMBUS_POSTER_PROTOCOL` | `auto` | poster backend, see above |
| `COLOMBUS_POSTER_SIZE` | `w342` | TMDB poster width |
| `COLOMBUS_HTTP_RETRIES` | `3` | connection retries; raise it if you see `Could not reach TMDB` |
| `COLOMBUS_USER_AGENT` | project string | Wikimedia rejects generic agents; theirs must carry a contact URL |

Note that `COLOMBUS_CACHE_DIR` holds your watchlist and watch history as well
as the cache, so pointing it somewhere temporary loses them.

## Building a Windows .exe

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm colombus.spec
```

The result is `dist/colombus.exe`. Keep a `.env` beside it and run it from a
terminal.

It is a one-file build, so it unpacks its runtime (~150 MB) into `%TEMP%` on
every launch and needs that much free space to start. On a nearly full disk it
will fail with `Failed to extract python3xx.dll`; switch the spec to a onedir
build if that is a concern.

## Layout

| Path | Responsibility |
| ---- | -------------- |
| `main.py` | CLI entry point and argument parsing |
| `app.py` | Textual app: layout, key bindings, background workers |
| `widget.py` | Always-on-top desktop widget (tkinter) |
| `service.py` | Fans one lookup across all sources into a single `Movie` |
| `sources/` | TMDB (required), OMDb and Wikipedia (both optional) |
| `widgets/` | Results, poster, detail, reviews, cast, episodes and stats panes |
| `render.py` | Rich renderables: facts, score bars, charts, stats |
| `cache.py` | SQLite store for cached JSON, posters, watchlist and history |
| `models.py` | `SearchHit`, `Movie`, `Person`, `Season`, `Filters`, `Stats` |
| `config.py` | Environment and `.env` loading |
| `i18n.py` | Message catalogue for the app's own strings |

## Requirements

Python 3.10 or newer. `textual`, `httpx`, `rich`, `pillow` and
`python-dotenv` are required. `textual-image` is installed by
`requirements.txt` too, but only powers the pixel-accurate poster backends —
without it the app falls back to `braille`, `ascii` or `halfcell` rather than
failing. `tkinter` ships with Python on Windows and is what the widget uses.
