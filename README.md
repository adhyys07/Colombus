# Colombus

A terminal movie browser. Search TMDB, then read the metadata, score bars,
Wikipedia summary and reviews for any result — without leaving your shell.

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
| `escape` | jump back to results      |
| `ctrl+r` | clear the cache           |
| `ctrl+q` | quit                      |

## Configuration

| Variable                | Default            | Purpose                          |
| ----------------------- | ------------------ | -------------------------------- |
| `TMDB_API_KEY`          | —                  | TMDB v3 key (one credential required) |
| `TMDB_ACCESS_TOKEN`     | —                  | TMDB v4 token, takes precedence  |
| `OMDB_API_KEY`          | —                  | optional extra ratings           |
| `COLOMBUS_CACHE_DIR`    | `~/.cache/colombus`| cache location                   |
| `COLOMBUS_CACHE_TTL`    | `604800` (7 days)  | cache lifetime in seconds; `0` never expires |
| `COLOMBUS_POSTER_SIZE`  | `w342`             | TMDB poster width                |

## Layout

| Module        | Role                                                    |
| ------------- | ------------------------------------------------------- |
| `main.py`     | CLI entry point and argument parsing                    |
| `app.py`      | Textual app: layout, key bindings, background workers   |
| `service.py`  | Fans one lookup across all sources into a single `Movie` |
| `sources/`    | TMDB (required), OMDb and Wikipedia (both optional)     |
| `widgets/`    | Results list, poster pane, detail pane                  |
| `render.py`   | Rich renderables for the detail pane                    |
| `cache.py`    | SQLite JSON cache plus an on-disk poster store          |
| `models.py`   | `SearchHit`, `Movie`, `Rating`, `Review`                |
| `config.py`   | Environment and `.env` loading                          |

Posters render as real pixels in terminals with Kitty graphics or Sixel
support (via the optional `textual-image` package) and fall back to a text
placeholder everywhere else.
