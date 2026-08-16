"""Open-Meteo HTTP client.

Uses ``requests.Session`` so TCP connections and TLS handshakes are reused
across requests. The client implements a small retry policy for transient
server errors and maps HTTP / transport failures to typed exceptions.

Open-Meteo requires no API key. The ``.env`` file is still supported so the
project can be extended with a keyed provider without code changes.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from app.api.errors import (
    CityNotFoundError,
    InvalidResponseError,
    NetworkError,
    RateLimitError,
    ServerError,
    WeatherAPIError,
)
from app.config import (
    AIR_QUALITY_URL,
    API_MAX_RETRIES,
    API_TIMEOUT,
    API_USER_AGENT,
    FORECAST_DAYS,
    FORECAST_URL,
    GEOCODING_URL,
)

logger = logging.getLogger("weathervision.api")

# Fields requested from the forecast endpoint.
_CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,"
    "precipitation,weather_code,cloud_cover,pressure_msl,"
    "wind_speed_10m,wind_direction_10m,wind_gusts_10m,visibility,uv_index"
)
_HOURLY_FIELDS = (
    "temperature_2m,precipitation_probability,precipitation,weather_code,"
    "wind_speed_10m,wind_direction_10m,is_day,visibility"
)
_DAILY_FIELDS = (
    "weather_code,temperature_2m_max,temperature_2m_min,"
    "apparent_temperature_max,precipitation_probability_max,precipitation_sum,"
    "uv_index_max,sunrise,sunset"
)


class WeatherAPI:
    """Thin, typed client for the Open-Meteo forecast / air-quality APIs."""

    def __init__(
        self,
        timeout: float = API_TIMEOUT,
        max_retries: int = API_MAX_RETRIES,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": API_USER_AGENT})

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------
    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                response = self._session.get(
                    url, params=params, timeout=self.timeout
                )
            except requests.exceptions.Timeout as exc:
                raise NetworkError(
                    f"Request timed out after {self.timeout}s"
                ) from exc
            except requests.exceptions.RequestException as exc:
                raise NetworkError(f"Network error: {exc}") from exc

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise InvalidResponseError(
                        "Response was not valid JSON"
                    ) from exc

            if response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")
            if response.status_code == 404:
                raise CityNotFoundError("Location not found")
            if response.status_code >= 500 and attempt < self.max_retries:
                attempt += 1
                delay = 0.5 * (2 ** attempt)
                logger.warning(
                    "Server error %s, retrying in %.1fs (attempt %d/%d)",
                    response.status_code, delay, attempt, self.max_retries,
                )
                time.sleep(delay)
                continue

            raise ServerError(f"API returned HTTP {response.status_code}")

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------
    def get_forecast(
        self, latitude: float, longitude: float, timezone: str = "auto"
    ) -> dict[str, Any]:
        """Fetch current + hourly + daily forecast as raw JSON."""
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone,
            "current": _CURRENT_FIELDS,
            "hourly": _HOURLY_FIELDS,
            "daily": _DAILY_FIELDS,
            "forecast_days": FORECAST_DAYS,
        }
        logger.info(
            "Fetching forecast for (%.3f, %.3f) tz=%s",
            latitude, longitude, timezone,
        )
        return self._get(FORECAST_URL, params)

    def get_air_quality(
        self, latitude: float, longitude: float
    ) -> dict[str, Any] | None:
        """Fetch air quality; return None if the endpoint is unavailable."""
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "us_aqi,pm2_5,pm10",
        }
        try:
            return self._get(AIR_QUALITY_URL, params)
        except WeatherAPIError as exc:
            logger.warning("Air quality unavailable: %s", exc)
            return None

    def search_cities(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Return raw geocoding results for a free-text query."""
        params = {"name": query, "count": limit, "language": "en", "format": "json"}
        payload = self._get(GEOCODING_URL, params)
        results = payload.get("results")
        if not results:
            raise CityNotFoundError(f"No results for {query!r}")
        return results[:limit]
