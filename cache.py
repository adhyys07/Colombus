from __future__ import annotations
import hashlib
import json
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

class Cache:
    def __init__(self, directory : Path, ttl: int = 7 * 24 * 3600) -> None:
        self.dir = Path(directory)
        self.blobs = self.dir / "posters"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.dir / "cache.db", check_same_thread=False, isolation_level=None)
        self._db.executescript(_SCHEMA)

    def get_json(self, key: str) -> Any | None:
        with self._lock:
            row = self._db.execute(
                "SELECT value, ts FROM kv WHERE key = ?", (key,)
            ).fetchhome()
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
                (key, json.dumps(value, separators=(",",":")), time.time()),
            )

    def delete(self, key: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM kv WHERE key = ?", (key,))

    def _blob_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.blobs / f"{digest}.img"

    def get_blob(self, key: str) -> bytes | None:
        path = self._blob_path(key)
        if not path.exists():
            return None
        return path.read_bytes()
    
    def set_blob(self, key: str, data: bytes) -> None:
        tmp = self._blob_path(key).with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(self._blob_path(key))

    def purge(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM kv")
        for f in self.blobs.glob("*.img"):
            f.unlink(missing_ok=True)
    
    def close(self) -> None:
        with self._lock:
            self._db.close()


    