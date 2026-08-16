"""Recent-search history persistence service."""
from __future__ import annotations

from datetime import datetime, timezone

from app.database.database import DatabaseManager
from app.models.weather_models import Location
from app.utils.helpers import location_from_row


class HistoryService:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def record(self, location: Location) -> None:
        self._db.add_history(location)

    def list(self) -> list[tuple[Location, datetime]]:
        entries = []
        for row in self._db.list_history():
            try:
                when = datetime.fromisoformat(row.get("searched_at", ""))
            except ValueError:
                when = datetime.now(timezone.utc)
            entries.append((location_from_row(row), when))
        return entries

    def clear(self) -> None:
        self._db.clear_history()
