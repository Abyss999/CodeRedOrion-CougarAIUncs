"""sha1 ledger (sqlite) so re-runs only process files they have not seen."""
from __future__ import annotations
import hashlib
import sqlite3
import time
from pathlib import Path


def sha1_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute("CREATE TABLE IF NOT EXISTS seen (kind TEXT, sha1 TEXT, status TEXT, ref TEXT, "
                        "ts REAL, PRIMARY KEY (kind, sha1))")

    def seen(self, kind: str, sha1: str) -> bool:
        return self.db.execute("SELECT 1 FROM seen WHERE kind=? AND sha1=?", (kind, sha1)).fetchone() is not None

    def status(self, kind: str, sha1: str) -> str | None:
        r = self.db.execute("SELECT status FROM seen WHERE kind=? AND sha1=?", (kind, sha1)).fetchone()
        return r[0] if r else None

    def ref(self, kind: str, sha1: str) -> str | None:
        """The ref stored for a seen file ('' if none), or None if never seen."""
        r = self.db.execute("SELECT ref FROM seen WHERE kind=? AND sha1=?", (kind, sha1)).fetchone()
        return (r[0] or "") if r else None

    def mark(self, kind: str, sha1: str, status: str, ref: str = ""):
        self.db.execute("INSERT OR REPLACE INTO seen VALUES (?,?,?,?,?)", (kind, sha1, status, ref, time.time()))
        self.db.commit()

    def count(self, kind: str, status: str | None = None) -> int:
        q, args = "SELECT COUNT(*) FROM seen WHERE kind=?", [kind]
        if status:
            q, args = q + " AND status=?", args + [status]
        return self.db.execute(q, args).fetchone()[0]

    def close(self):
        self.db.close()
