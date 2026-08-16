"""Favorites persistence service."""
from __future__ import annotations

from app.database.database import DatabaseManager
from app.models.weather_models import Location
from app.utils.helpers import location_from_row


class FavoritesService:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def add(self, location: Location) -> bool:
        return self._db.add_favorite(location)

    def remove(self, location: Location) -> bool:
        return self._db.remove_favorite(location.latitude, location.longitude)

    def remove_by_key(self, latitude: float, longitude: float) -> bool:
        return self._db.remove_favorite(latitude, longitude)

    def contains(self, location: Location) -> bool:
        return self._db.is_favorite(location.latitude, location.longitude)

    def list(self) -> list[Location]:
        return [location_from_row(row) for row in self._db.list_favorites()]
