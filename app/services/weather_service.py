"""Weather orchestration service.

Coordinates geocoding, live API fetching, air quality, offline caching and
demo mode. Runs inside a background worker thread, so it must never touch Qt
objects. Returns fully validated :class:`WeatherData` objects.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.api.errors import (
    CityNotFoundError,
    WeatherAPIError,
)
from app.api.geocoding import Geocoder
from app.api.mock_data import MockWeatherProvider
from app.api.weather_api import WeatherAPI
from app.models.weather_models import Location, WeatherData
from app.services.cache_service import WeatherCache
from app.services.history_service import HistoryService
from app.services.settings_manager import SettingsManager

logger = logging.getLogger("weathervision.service")


@dataclass
class SearchResult:
    """Outcome of a search / refresh request."""

    location: Location
    weather: WeatherData
    candidates: list[Location] = None  # type: ignore[assignment]


class WeatherService:
    def __init__(
        self,
        api: WeatherAPI,
        geocoder: Geocoder,
        cache: WeatherCache,
        history: HistoryService,
        settings: SettingsManager,
        mock_provider: MockWeatherProvider | None = None,
    ) -> None:
        self._api = api
        self._geocoder = geocoder
        self._cache = cache
        self._history = history
        self._settings = settings
        self._mock = mock_provider or MockWeatherProvider()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def is_demo_mode(self) -> bool:
        return bool(self._settings.get("demo_mode"))

    def search(self, query: str) -> list[Location]:
        """Resolve a free-text query (city, region, country, or coordinates)."""
        return self._geocoder.search(query)

    def fetch_for_query(self, query: str) -> tuple[Location, WeatherData]:
        """Search + fetch weather for a free-text query."""
        locations = self.search(query)
        if not locations:
            raise CityNotFoundError("No location found for that query")
        location = locations[0]
        weather = self._fetch(location)
        return location, weather

    def fetch_location(self, location: Location) -> WeatherData:
        """Fetch weather for an already-resolved location."""
        return self._fetch(location)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _fetch(self, location: Location) -> WeatherData:
        if self.is_demo_mode():
            weather = self._mock.get_weather(location)
            self._history.record(location)
            logger.info("Demo data returned for %s", location.display_name)
            return weather

        try:
            payload = self._api.get_forecast(
                location.latitude, location.longitude, location.tz_name
            )
            air_quality = self._api.get_air_quality(
                location.latitude, location.longitude
            )
            weather = WeatherData.from_api_json(payload, location, air_quality)
        except WeatherAPIError:
            cached = self._cache.get(location)
            if cached is not None:
                logger.warning(
                    "Live fetch failed for %s; serving cache (%.0f min old)",
                    location.display_name, cached.age_minutes,
                )
                self._history.record(location)
                return cached.weather
            raise

        self._cache.save(location, weather)
        self._history.record(location)
        logger.info("Live weather fetched for %s", location.display_name)
        return weather

    # ------------------------------------------------------------------
    # History / convenience
    # ------------------------------------------------------------------
    def record_history(self, location: Location) -> None:
        self._history.record(location)

    def clear_cache(self) -> None:
        self._cache.clear()
