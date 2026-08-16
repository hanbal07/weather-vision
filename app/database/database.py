"""Thread-safe SQLite database manager for WeatherVision.

Stores three kinds of persistent data:

* ``favorites`` -- locations the user saved with the star button.
* ``history``   -- recently searched locations (capped at HISTORY_LIMIT).
* ``cache``     -- latest raw API payload per location for offline mode.

All public methods acquire an RLock, so the database can be used from
worker threads as well as from the GUI thread.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config import HISTORY_LIMIT

if TYPE_CHECKING:
    from app.models.weather_models import Location

logger = logging.getLogger("weathervision.db")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DatabaseManager:
    """Owns the SQLite connection and exposes typed CRUD helpers."""

    def __init__(self, db_path: Path) -> None:
        self._path = str(db_path)
        self._lock = threading.RLock()
        # check_same_thread=False + the RLock allow access from worker threads.
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _create_tables(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    name         TEXT NOT NULL,
                    country      TEXT DEFAULT '',
                    country_code TEXT DEFAULT '',
                    admin1       TEXT DEFAULT '',
                    latitude     REAL NOT NULL,
                    longitude    REAL NOT NULL,
                    timezone     TEXT DEFAULT 'UTC',
                    created_at   TEXT NOT NULL,
                    UNIQUE (latitude, longitude)
                );

                CREATE TABLE IF NOT EXISTS history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    name         TEXT NOT NULL,
                    country      TEXT DEFAULT '',
                    country_code TEXT DEFAULT '',
                    admin1       TEXT DEFAULT '',
                    latitude     REAL NOT NULL,
                    longitude    REAL NOT NULL,
                    timezone     TEXT DEFAULT 'UTC',
                    searched_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cache (
                    cache_key       TEXT PRIMARY KEY,
                    location_json   TEXT NOT NULL,
                    forecast_json   TEXT NOT NULL,
                    air_quality_json TEXT,
                    fetched_at      TEXT NOT NULL
                );
                """
            )

    # ------------------------------------------------------------------
    # Favorites
    # ------------------------------------------------------------------
    def add_favorite(self, location: "Location") -> bool:
        """Insert a favorite. Returns False if it already exists."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO favorites
                    (name, country, country_code, admin1, latitude, longitude,
                     timezone, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    location.name,
                    location.country,
                    location.country_code,
                    location.admin1,
                    location.latitude,
                    location.longitude,
                    location.timezone,
                    _utc_now(),
                ),
            )
            return cur.rowcount > 0

    def remove_favorite(self, latitude: float, longitude: float) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM favorites WHERE latitude=? AND longitude=?",
                (latitude, longitude),
            )
            return cur.rowcount > 0

    def is_favorite(self, latitude: float, longitude: float) -> bool:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT 1 FROM favorites WHERE latitude=? AND longitude=?",
                (latitude, longitude),
            ).fetchone()
            return row is not None

    def list_favorites(self) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT * FROM favorites ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def add_history(self, location: "Location") -> None:
        """Insert a search record, de-duplicating the most recent same location."""
        with self._lock, self._conn:
            self._conn.execute(
                """
                DELETE FROM history
                WHERE latitude=? AND longitude=?
                """,
                (location.latitude, location.longitude),
            )
            self._conn.execute(
                """
                INSERT INTO history
                    (name, country, country_code, admin1, latitude, longitude,
                     timezone, searched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    location.name,
                    location.country,
                    location.country_code,
                    location.admin1,
                    location.latitude,
                    location.longitude,
                    location.timezone,
                    _utc_now(),
                ),
            )
            # Keep the table bounded.
            self._conn.execute(
                """
                DELETE FROM history WHERE id NOT IN (
                    SELECT id FROM history
                    ORDER BY searched_at DESC
                    LIMIT ?
                )
                """,
                (HISTORY_LIMIT,),
            )

    def list_history(self) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT * FROM history ORDER BY searched_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def clear_history(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM history")

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    def get_cache(self, cache_key: str) -> dict[str, Any] | None:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM cache WHERE cache_key=?", (cache_key,)
            ).fetchone()
            return dict(row) if row else None

    def save_cache(
        self,
        cache_key: str,
        location_json: str,
        forecast_json: str,
        air_quality_json: str | None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO cache
                    (cache_key, location_json, forecast_json, air_quality_json,
                     fetched_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    location_json,
                    forecast_json,
                    air_quality_json,
                    _utc_now(),
                ),
            )

    def clear_cache(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM cache")

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._conn.close()
