"""Geocoding helpers: free-text search and coordinate detection."""
from __future__ import annotations

import re
from typing import Any

from app.api.errors import CityNotFoundError
from app.api.weather_api import WeatherAPI
from app.models.weather_models import Location
from app.utils.validators import fval, sval

_COORDINATES_PATTERN = re.compile(
    r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,;]\s*(-?\d{1,3}(?:\.\d+)?)\s*$"
)


class Geocoder:
    """Resolves free-text queries into structured :class:`Location` objects."""

    def __init__(self, api: WeatherAPI) -> None:
        self._api = api

    def search(self, query: str, limit: int = 8) -> list[Location]:
        """Search by city / region / country name."""
        query = query.strip()
        if not query:
            raise CityNotFoundError("Please enter a location name")

        coordinates = self.detect_coordinates(query)
        if coordinates:
            latitude, longitude = coordinates
            return [
                Location(
                    name=f"{latitude:.2f}, {longitude:.2f}",
                    country="Coordinates",
                    latitude=latitude,
                    longitude=longitude,
                )
            ]

        raw = self._api.search_cities(query, limit=limit)
        return [self._from_raw(row) for row in raw]

    @staticmethod
    def detect_coordinates(text: str) -> tuple[float, float] | None:
        """Return ``(lat, lon)`` if ``text`` looks like coordinates, else None."""
        match = _COORDINATES_PATTERN.match(text)
        if not match:
            return None
        latitude = float(match.group(1))
        longitude = float(match.group(2))
        if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
            return None
        return latitude, longitude

    @staticmethod
    def _from_raw(row: dict[str, Any]) -> Location:
        return Location(
            name=sval(row, "name", default="Unknown"),
            country=sval(row, "country"),
            country_code=sval(row, "country_code"),
            admin1=sval(row, "admin1"),
            latitude=fval(row, "latitude", default=0.0),
            longitude=fval(row, "longitude", default=0.0),
            timezone=sval(row, "timezone", default="UTC") or "UTC",
            population=fval(row, "population"),
        )
