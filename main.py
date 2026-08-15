"""Entry point for the Colombus terminal movie browser."""

from __future__ import annotations

import argparse
import sys

from config import Config, ConfigError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="colombus", description="Browse films from your terminal."
    )
    parser.add_argument("query", nargs="*", help="film to search for on launch")
    parser.add_argument("--env", metavar="PATH", help="path to a .env file")
    parser.add_argument(
        "--widget",
        action="store_true",
        help="run the always-on-top desktop widget instead of the full app",
    )
    parser.add_argument(
        "--widget-series",
        action="store_true",
        help="make the widget show series instead of films",
    )
    parser.add_argument(
        "--purge-cache",
        action="store_true",
        help="clear cached API responses and posters, then exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = Config.load(args.env)
    except ConfigError as exc:
        print(f"colombus: {exc}", file=sys.stderr)
        return 1

    if args.purge_cache:
        from cache import Cache

        with Cache(config.cache_dir, config.cache_ttl) as cache:
            cache.purge()
        print(f"Cleared cache at {config.cache_dir}")
        return 0

    if args.widget:
        from models import MOVIE, TV
        from widget import run_widget

        run_widget(config, media_type=TV if args.widget_series else MOVIE)
        return 0

    from app import ColombusApp

    ColombusApp(config, " ".join(args.query)).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
