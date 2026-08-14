from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS kv_ts ON kv (ts);
"""

_REPLACE_ATTEMPTS = 5
_REPLACE_BACKOFF = 0.05


class Cache:
    def __init__(self, directory: Path, ttl: int = 7 * 24 * 3600) -> None:
        self.dir = Path(directory)
        self.blobs = self.dir / "posters"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self._lock = threading.Lock()
        self._db = sqlite3.connect(
            self.dir / "cache.db", check_same_thread=False, isolation_level=None
        )
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.executescript(_SCHEMA)

    def get_json(self, key: str) -> Any | None:
        with self._lock:
            row = self._db.execute(
                "SELECT value, ts FROM kv WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        value, ts = row
        if self.ttl and (time.time() - ts) > self.ttl:
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

    def delete(self, key: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM kv WHERE key = ?", (key,))

    def _blob_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.blobs / f"{digest}.img"

    def get_blob(self, key: str) -> bytes | None:
        path = self._blob_path(key)
        try:
            if self.ttl and (time.time() - path.stat().st_mtime) > self.ttl:
                path.unlink(missing_ok=True)
                return None
            return path.read_bytes()
        except OSError:
            # Absent, locked mid-replace, or unreadable: all are cache misses.
            return None

    def set_blob(self, key: str, data: bytes) -> None:
        """Best-effort write. A cache failure must never break the caller."""
        path = self._blob_path(key)
        # Unique temp name so concurrent writers for the same key cannot
        # clobber each other's partial file before the atomic replace.
        tmp = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            tmp.write_bytes(data)
            # Windows refuses to replace a file another thread holds open, so
            # retry briefly rather than propagating a transient PermissionError.
            for attempt in range(_REPLACE_ATTEMPTS):
                try:
                    tmp.replace(path)
                    return
                except PermissionError:
                    if attempt == _REPLACE_ATTEMPTS - 1:
                        return
                    time.sleep(_REPLACE_BACKOFF)
        except OSError:
            return
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def purge(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM kv")
        for pattern in ("*.img", "*.tmp"):
            for f in self.blobs.glob(pattern):
                f.unlink(missing_ok=True)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "Cache":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
