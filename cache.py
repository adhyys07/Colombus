from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from models import SearchHit


_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS kv_ts ON kv (ts);

CREATE TABLE IF NOT EXISTS watchlist (
    tmdb_id INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    title TEXT NOT NULL,
    year TEXT NOT NULL DEFAULT '',
    poster_path TEXT,
    added REAL NOT NULL,
    PRIMARY KEY (tmdb_id, media_type)
);
CREATE TABLE IF NOT EXISTS history (
    query TEXT NOT NULL,
    media_type TEXT NOT NULL DEFAULT 'movie',
    last_used REAL NOT NULL,
    uses INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (query, media_type)
);
"""


class Cache:
    """SQLite key/value store for JSON, plus an on-disk blob store for posters."""

    def __init__(self, directory: Path, ttl: int = 7 * 24 * 3600) -> None:
        self.dir = Path(directory)
        self.blobs = self.dir / "posters"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self._lock = threading.Lock()
        self._db = sqlite3.connect(
            self.dir / "cache.db", check_same_thread=False, isolation_level=None
        )
        # Readers and the writer are serialised by _lock, but WAL plus a busy
        # timeout keeps a second Colombus process from erroring out.
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.executescript(_SCHEMA)

    def _expired(self, ts: float) -> bool:
        return bool(self.ttl) and (time.time() - ts) > self.ttl

    def get_json(self, key: str) -> Any | None:
        with self._lock:
            row = self._db.execute(
                "SELECT value, ts FROM kv WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        value, ts = row
        if self._expired(ts):
            self.delete(key)
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            self.delete(key)
            return None

    def set_json(self, key: str, value: Any) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO kv (key, value, ts) VALUES (?, ?, ?)",
                (key, json.dumps(value, separators=(",", ":")), time.time()),
            )

    def watchlist_add(self, hit: SearchHit) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO watchlist (tmdb_id, media_type, title, year, poster_path, added) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    hit.tmdb_id,
                    hit.media_type,
                    hit.title,
                    hit.year,
                    hit.poster_path,
                    time.time(),
                ),
            )

    def watchlist_remove(self, tmdb_id: int, media_type: str) -> None:
        with self._lock:
            self._db.execute(
                "DELETE FROM watchlist WHERE tmdb_id = ? AND media_type = ?",
                (tmdb_id, media_type),
            )

    def watchlist_has(self, tmdb_id: int, media_type: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM watchlist WHERE tmdb_id = ? AND media_type = ?",
                (tmdb_id, media_type),
            ).fetchone()
        return row is not None

    def watchlist_toggle(self, hit: SearchHit) -> bool:
        """Returns True if the title is now on the list."""
        if self.watchlist_has(hit.tmdb_id, hit.media_type):
            self.watchlist_remove(hit.tmdb_id, hit.media_type)
            return False
        self.watchlist_add(hit)
        return True

    def watchlist_all(self) -> list[SearchHit]:
        with self._lock:
            rows = self._db.execute(
                "SELECT tmdb_id, media_type, title, year, poster_path "
                "FROM watchlist ORDER BY added DESC"
            ).fetchall()
        return [
            SearchHit(
                tmdb_id=row[0], title=row[2], year=row[3], overview="",
                poster_path=row[4], media_type=row[1],
            )
            for row in rows
        ]

    def history_add(self, query: str, media_type: str) -> None:
        query = query.strip()
        if not query:
            return
        with self._lock:
            self._db.execute(
                "INSERT INTO history (query, media_type, last_used, uses) "
                "VALUES (?, ?, ?, 1) "
                "ON CONFLICT(query, media_type) DO UPDATE SET "
                "last_used = excluded.last_used, uses = uses + 1",
                (query, media_type, time.time()),
            )

    def history_recent(self, limit: int = 20) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT query FROM history ORDER BY last_used DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [row[0] for row in rows]

    def history_clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM history")
            
    def delete(self, key: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM kv WHERE key = ?", (key,))

    def _blob_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.blobs / f"{digest}.img"

    def get_blob(self, key: str) -> bytes | None:
        path = self._blob_path(key)
        try:
            if self._expired(path.stat().st_mtime):
                path.unlink(missing_ok=True)
                return None
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            return None

    def set_blob(self, key: str, data: bytes) -> None:
        target = self._blob_path(key)
        # Unique temp name: two threads may fetch the same poster at once.
        tmp = target.with_name(f"{target.stem}.{uuid.uuid4().hex}.tmp")
        try:
            self.blobs.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(data)
            tmp.replace(target)
        except OSError:
            tmp.unlink(missing_ok=True)

    def purge(self) -> None:
        """Clears cached API responses and posters.

        Deliberately leaves `watchlist` and `history` alone - those are the
        user's own data, not a cache.
        """
        with self._lock:
            self._db.execute("DELETE FROM kv")
        for pattern in ("*.img", "*.tmp"):
            for f in self.blobs.glob(pattern):
                f.unlink(missing_ok=True)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> Cache:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
