# Colombus

A terminal browser for movies and series. Search TMDB, browse what's
trending, or dig through categories — then read the metadata, score bars,
Wikipedia summary and reviews for anything you pick, without leaving your
shell.

## Install

```bash
pip install -r requirements.txt
cp .env.example .env
```

Add a TMDB credential to `.env` — either the v3 `TMDB_API_KEY` or the v4
`TMDB_ACCESS_TOKEN` (the token wins if both are set). Both are free from
<https://www.themoviedb.org/settings/api>.

`OMDB_API_KEY` is optional; it adds the IMDb / Rotten Tomatoes / Metacritic
score line. Everything still works without it.

## Sections

Four sections share one results list, switched with the tabs (or `ctrl+t`):

| Section | What it shows |
| ------- | ------------- |
| **Search** | Titles matching your query |
| **Trending** | What's trending today or this week |
| **Categories** | Everything in a genre or original language |
| **Watchlist** | Titles you marked with `ctrl+d`, newest first |

The right-hand pane has four tabs: **Details**, **Reviews**, **Cast** and
**Episodes**. Cast lists the billed roles - select one to browse that person's
filmography. Episodes is enabled only for series, with a season picker. Details
carries the facts, score bars, overview and Wikipedia summary; Reviews shows
every review TMDB has for the title in full, with author, score and date. The
Reviews tab is labelled with its count, and `f2` cycles the four.

The **Movies / Series / Both** selector applies to every section, so you can
browse trending series, search across both at once, or list every title in a
genre. Series get their own detail layout — creator, season and episode
counts, and the TV content rating in place of budget and revenue.

## Usage

```bash
python main.py                 # start empty and search interactively
python main.py dune            # search on launch
python main.py --purge-cache   # drop cached responses and posters, then exit
python main.py --env path/to/.env
```

| Key      | Action                    |
| -------- | ------------------------- |
| `ctrl+s` | focus the search box      |
| `enter`  | run the search            |
| `↑` `↓`  | move through results      |
| `ctrl+t` | next section              |
| `f2`     | cycle Details/Reviews/Cast/Episodes |
| `f3`     | more like this            |
| `f4`     | play trailer in browser   |
| `f5`     | open IMDb/TMDB page       |
| `ctrl+d` | add/remove from watchlist |
| `escape` | jump back to results      |
| `ctrl+r` | clear the cache           |
| `ctrl+q` | quit                      |

## Building a Windows .exe

```bash
pip install pyinstaller
pyinstaller colombus.spec
```

This produces a single self-contained `dist/colombus.exe`. Put a `.env` next
to the executable — the packaged build looks there first, then falls back to
the current working directory. Run it from a terminal (it is a console app):

```
dist\colombus.exe "blade runner 2049"
```

## Configuration

| Variable                | Default            | Purpose                          |
| ----------------------- | ------------------ | -------------------------------- |
| `TMDB_API_KEY`          | —                  | TMDB v3 key (one credential required) |
| `TMDB_ACCESS_TOKEN`     | —                  | TMDB v4 token, takes precedence  |
| `OMDB_API_KEY`          | —                  | optional extra ratings           |
| `COLOMBUS_CACHE_DIR`    | `~/.cache/colombus`| cache location                   |
| `COLOMBUS_CACHE_TTL`    | `604800` (7 days)  | cache lifetime in seconds; `0` never expires |
| `COLOMBUS_POSTER_SIZE`  | `w342`             | TMDB poster width                |
| `COLOMBUS_HTTP_RETRIES` | `3`                | connection retries; raise it if you see `Could not reach TMDB` |
| `COLOMBUS_REGION`       | `US`               | where-to-watch region, e.g. `IN` |
| `COLOMBUS_LANGUAGE`     | `en-US`            | language of titles and overviews from TMDB |
| `COLOMBUS_UI_LANGUAGE`  | `en`               | language of the app's own labels (`en`, `hi`, `es`) |
| `COLOMBUS_POSTER_PROTOCOL` | `auto`          | poster backend, see below |

## Layout

| Module        | Role                                                    |
| ------------- | ------------------------------------------------------- |
| `main.py`     | CLI entry point and argument parsing                    |
| `app.py`      | Textual app: layout, key bindings, background workers   |
| `service.py`  | Fans one lookup across all sources into a single `Movie` |
| `sources/`    | TMDB (required), OMDb and Wikipedia (both optional)     |
| `widgets/`    | Results list, poster, detail and reviews panes           |
| `render.py`   | Rich renderables for the detail pane                    |
| `cache.py`    | SQLite JSON cache plus an on-disk poster store          |
| `models.py`   | `SearchHit`, `Movie`, `Rating`, `Review`, `Person`, `Season` |
| `i18n.py`     | Message catalogue for the app's own strings             |
| `config.py`   | Environment and `.env` loading                          |

## Posters

`COLOMBUS_POSTER_PROTOCOL` picks how posters are drawn:

| Value | Result | Needs |
| ----- | ------ | ----- |
| `auto` (default) | best the terminal reports it can do | — |
| `tgp` / `sixel` | true pixels | Kitty graphics or Sixel support |
| `halfcell` / `unicode` | coloured blocks | any 24-bit colour terminal |
| `braille` | coloured 2x4 dot art, ~8x the detail of `ascii` | any terminal |
| `ascii` | classic density-ramp character art, tinted | any terminal |
| `none` | text placeholder | — |

`braille` and `ascii` are drawn from the image in-process, so they need no
graphics protocol at all and work in the plain Windows console. Posters are
sized to their real aspect ratio, allowing for terminal cells being about
twice as tall as they are wide.
