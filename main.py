from __future__ import annotations
import argparse
import asyncio
import dataclasses
import json
import sys
from config import Config, ConfigError
from render import BACKEND, rich_poster

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="colombus",
        description="Search for movies and view details in the terminal.",
    )
    p.add_argument("query", nargs="*", help="film title to search for")
    p.add_argument(
        "-p", "--print", dest="oneshot", action="store_true",
        help="print the top match and exit instead of opening the TUI",
    )
    p.add_argument("--json", action="store_true", help="emit JSON and exit")
    p.add_argument(
        "--poster-width", type=int, default=32,
        help="poster width in terminal columns for --print (default: 32)",
    )
    p.add_argument("--clear-cache", action="store_true", help="wipe the cache and exit")
    p.add_argument("--doctor", action="store_true", help="report what is configured")
    return p

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    query = " ".join(args.query).strip()

    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.doctor:
        return _doctor(config)

    if args.clear_cache:
        from cache import Cache

        cache = Cache(config.cache_dir, ttl=config.cache_ttl)
        config.purge()
        cache.close()
        print(f"cleared {config.cache_dir}")
        return 0

    if args.json or args.oneshot:
        if not query:
            print("error: --print and --json need a query", file=sys.stderr)
            return 2
        return asyncio.run(_oneshot(config, query, args))

    from app import Columbus

    Columbus(config, initial_query=query).run()
    return 0

def _doctor(config: Config) -> int:
    import shutil
    print("Columbus configuration")
    print(f"  TMDB           : {'ok' if (config.tmdb_api_key or config.tmdb_access_token) else 'MISSING'}")
    print(f"  OMDb           : {'ok' if config.has_omdb else 'not set (no critic scores)'}")
    print(f"  cache dir      : {config.cache_dir}")
    print(f"  poster size    : {config.poster_size}")
    print(f"  poster backend : {BACKEND}")
    if BACKEND == "none":
        print("     -> pip install textual-image, or install chafa")
    print(f"  chafa on PATH  : {'yes' if shutil.which('chafa') else 'no'}")
    print(f"  TERM           : {__import__('os').environ.get('TERM', '?')}")
    return 0

async def _oneshot(config: Config, query: str, args) -> int:
    from rich.columns import Columns
    from rich.console import Console, Group
    from rich.text import Text
    from service import MovieService
    from widgets.detail import rating_bar
    console = Console()
    service = MovieService(config)
    try:
        hits = await service.search(query, limit=1)
        if not hits:
            print(f"no results for {query!r}", file=sys.stderr)
            return 1

        movie = await service.get_details(hits[0].tmdb_id)

        if args.json:
            print(json.dumps(dataclasses.asdict(movie), indent=2, ensure_ascii=False))
            return 0
        poster_bytes = await service.poster(movie)
        poster = rich_poster(poster_bytes, movie.title, cols=args.poster_width)

        body = [Text(movie.title, style="bold"), Text("")]
        if movie.tagline:
            body.append(Text(f"“{movie.tagline}”", style="italic dim"))
        body.append(
            Text(
                " · ".join(
                    x for x in (movie.year, movie.runtime_str, ", ".join(movie.genres)) if x
                ),
                style="dim",
            )
        )
        body.append(Text(""))
        if movie.director:
            body.append(Text(f"Directed by {movie.director}"))
        if movie.cast:
            body.append(Text(f"Starring {', '.join(movie.cast[:5])}", style="dim"))
        body.append(Text(""))
        body.extend(rating_bar(r) for r in movie.ratings)
        body.append(Text(""))
        body.append(Text(movie.overview))

        console.print(Columns([poster, Group(*body)], padding=(0, 3)))
        return 0
    finally:
        await service.aclose()


if __name__ == "__main__":
    raise SystemExit(main())
