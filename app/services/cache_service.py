"""Offline cache for weather data.

Stores the raw API payloads per location key. On a live fetch the cache is
updated; if a live fetch fails the cache can be served, clearly labelled with
its age so the UI can display 'Offline Mode - showing data from X minutes ago'.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.api.errors import InvalidResponseError
from app.config import CACHE_MAX_AGE_MINUTES, CACHE_TTL_MINUTES
from app.database.database import DatabaseManager
from app.models.weather_models import Location, WeatherData

logger = logging.getLogger("weathervision.cache")


@dataclass
class CachedWeather:
    weather: WeatherData
    fetched_at: datetime
    age_minutes: float


class WeatherCache:
    """Thin service over the ``cache`` database table."""

    def __init__(
        self, db: DatabaseManager, ttl_minutes: int = CACHE_TTL_MINUTES
    ) -> None:
        self._db = db
        self.ttl_minutes = ttl_minutes

    # ------------------------------------------------------------------
    def save(self, location: Location, weather: WeatherData) -> None:
        """Persist a fresh snapshot for later offline use."""
        try:
            self._db.save_cache(
                cache_key=location.cache_key(),
                location_json=json.dumps(location.to_dict()),
                forecast_json=json.dumps(
                    self._weather_to_payload(weather), default=str
                ),
                air_quality_json=self._air_quality_to_json(weather),
            )
            logger.debug("Cache updated for %s", location.cache_key())
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("Could not write cache: %s", exc)

    def get(
        self, location: Location, max_age_minutes: int = CACHE_MAX_AGE_MINUTES
    ) -> CachedWeather | None:
        """Return cached weather if it exists and is younger than max_age."""
        row = self._db.get_cache(location.cache_key())
        if not row:
            return None

        fetched_at = datetime.fromisoformat(row["fetched_at"])
        age_minutes = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 60.0
        if age_minutes > max_age_minutes:
            logger.info(
                "Cached data for %s is too old (%.0f min)", location.cache_key(), age_minutes
            )
            return None

        try:
            loc = Location.from_dict(json.loads(row["location_json"]))
            payload = json.loads(row["forecast_json"])
            aq_payload = json.loads(row["air_quality_json"]) if row.get("air_quality_json") else None
            weather = WeatherData.from_api_json(
                payload, loc, aq_payload, source="cache"
            )
            weather.fetched_at = fetched_at
            return CachedWeather(weather=weather, fetched_at=fetched_at, age_minutes=age_minutes)
        except (ValueError, TypeError, json.JSONDecodeError, InvalidResponseError) as exc:
            logger.warning("Discarding corrupt cache entry: %s", exc)
            return None

    def clear(self) -> None:
        self._db.clear_cache()
        logger.info("Cache cleared")

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _weather_to_payload(weather: WeatherData) -> dict[str, Any]:
        """Pack a WeatherData object into a minimal JSON-able dict."""
        current = weather.current
        return {
            "current": {
                "temperature_2m": current.temperature,
                "relative_humidity_2m": current.humidity,
                "apparent_temperature": current.feels_like,
                "is_day": int(current.is_day),
                "precipitation": current.precipitation,
                "weather_code": current.condition_code,
                "cloud_cover": current.cloud_cover,
                "pressure_msl": current.pressure,
                "wind_speed_10m": current.wind_speed,
                "wind_direction_10m": current.wind_direction,
                "wind_gusts_10m": current.wind_gusts,
                "visibility": current.visibility_m,
                "uv_index": current.uv_index,
            },
            "hourly": {
                "time": [h.time for h in weather.hourly],
                "temperature_2m": [h.temperature for h in weather.hourly],
                "precipitation_probability": [h.precipitation_probability for h in weather.hourly],
                "precipitation": [h.precipitation for h in weather.hourly],
                "weather_code": [h.condition_code for h in weather.hourly],
                "wind_speed_10m": [h.wind_speed for h in weather.hourly],
                "is_day": [int(h.is_day) for h in weather.hourly],
            },
            "daily": {
                "time": [d.date for d in weather.daily],
                "weather_code": [d.condition_code for d in weather.daily],
                "temperature_2m_max": [d.temp_max for d in weather.daily],
                "temperature_2m_min": [d.temp_min for d in weather.daily],
                "precipitation_probability_max": [d.precipitation_probability for d in weather.daily],
                "precipitation_sum": [d.precipitation_sum for d in weather.daily],
                "uv_index_max": [d.uv_index_max for d in weather.daily],
                "sunrise": [d.sunrise for d in weather.daily],
                "sunset": [d.sunset for d in weather.daily],
            },
        }

    @staticmethod
    def _air_quality_to_json(weather: WeatherData) -> str | None:
        aq = weather.air_quality
        if aq is None or aq.aqi is None:
            return None
        return json.dumps(
            {"current": {"us_aqi": aq.aqi, "pm2_5": aq.pm2_5, "pm10": aq.pm10}}
        )
