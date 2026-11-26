"""SQLite persistence for L2 quota (P2 2.7). One connection guarded by a lock: hooks run from the
threadpool (/api/ask) and the event loop (/api/ask_stream) of ONE process, so a process-level lock
plus single-statement updates is enough; WAL + busy_timeout cover a second process opening the file.

Money model (pessimistic): `reserve` charges the estimate to the day's spend immediately, so a
reservation that is never settled nor finalized (Starlette may never close the body iterator) is
already paid for — expiry needs no extra charge, it only closes the row so a late settle cannot
refund. `settle` replaces the estimate with the actual cost exactly once (open -> settled);
`close` (finalize / expiry) keeps the estimate (open -> charged). Rowcount 0 => no-op (idempotent).
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS counters (key TEXT NOT NULL, day TEXT NOT NULL, n INTEGER NOT NULL,
                                     PRIMARY KEY (key, day));
CREATE TABLE IF NOT EXISTS spend (day TEXT PRIMARY KEY, usd REAL NOT NULL);
CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, day TEXT NOT NULL, usd REAL NOT NULL,
                                         status TEXT NOT NULL, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS reservations_open ON reservations (status, created);
"""


class QuotaStore:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None,
                                   timeout=10.0)
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.executescript(_SCHEMA)

    # ── counters (free questions, BYOK web searches) ──
    def count(self, key: str, day: str) -> int:
        with self._lock:
            row = self._db.execute("SELECT n FROM counters WHERE key=? AND day=?",
                                   (key, day)).fetchone()
        return row[0] if row else 0

    def take(self, limits: list[tuple[str, int]], day: str) -> bool:
        """Increment every key by 1 iff ALL are below their limit (all-or-nothing)."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for key, limit in limits:
                    row = self._db.execute("SELECT n FROM counters WHERE key=? AND day=?",
                                           (key, day)).fetchone()
                    if (row[0] if row else 0) >= limit:
                        self._db.execute("ROLLBACK")
                        return False
                for key, _ in limits:
                    self._db.execute(
                        "INSERT INTO counters (key, day, n) VALUES (?, ?, 1) "
                        "ON CONFLICT (key, day) DO UPDATE SET n = n + 1", (key, day))
                self._db.execute("COMMIT")
                return True
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    # ── site-wide spend ──
    def spent(self, day: str) -> float:
        with self._lock:
            row = self._db.execute("SELECT usd FROM spend WHERE day=?", (day,)).fetchone()
        return row[0] if row else 0.0

    def reserve(self, rid: str, day: str, usd: float, cap: float | None, now: float) -> bool:
        """Charge `usd` now. cap=None => never refuse (still charged). False => over cap, nothing
        written."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute("INSERT OR IGNORE INTO spend (day, usd) VALUES (?, 0)", (day,))
                cur = self._db.execute(
                    "UPDATE spend SET usd = usd + ? WHERE day=? AND (? IS NULL OR usd + ? <= ? + 1e-9)",
                    (usd, day, cap, usd, cap))   # epsilon: float sums of exact-cap reservations
                if cur.rowcount != 1:
                    self._db.execute("ROLLBACK")
                    return False
                self._db.execute("INSERT INTO reservations (id, day, usd, status, created) "
                                 "VALUES (?, ?, ?, 'open', ?)", (rid, day, usd, now))
                self._db.execute("COMMIT")
                return True
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def settle(self, rid: str, actual_usd: float) -> bool:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute("SELECT day, usd FROM reservations WHERE id=? AND status='open'",
                                       (rid,)).fetchone()
                cur = self._db.execute(
                    "UPDATE reservations SET status='settled' WHERE id=? AND status='open'", (rid,))
                if row is None or cur.rowcount != 1:
                    self._db.execute("ROLLBACK")
                    return False
                self._db.execute("UPDATE spend SET usd = usd + ? WHERE day=?",
                                 (actual_usd - row[1], row[0]))
                self._db.execute("COMMIT")
                return True
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def close(self, rid: str) -> bool:
        """Keep the reserved charge (finalize of an unsettled call)."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE reservations SET status='charged' WHERE id=? AND status='open'", (rid,))
        return cur.rowcount == 1

    def expire(self, older_than: float) -> int:
        with self._lock:
            cur = self._db.execute(
                "UPDATE reservations SET status='charged' WHERE status='open' AND created < ?",
                (older_than,))
        return cur.rowcount

    def status(self, rid: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT status FROM reservations WHERE id=?", (rid,)).fetchone()
        return row[0] if row else None
