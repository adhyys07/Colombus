from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
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
