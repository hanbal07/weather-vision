"""Domain models for WeatherVision.

Dataclasses are used as immutable-ish value objects. The ``from_api_json``
classmethod is the single place where raw provider JSON is converted into
validated domain objects, so the rest of the application never touches
untrusted dicts directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.api.errors import InvalidResponseError
from app.utils.helpers import (
    condition_from_code,
    parse_iso_time,
)
from app.utils.validators import fval, ival, require_keys, sval

DAY_ICONS = ["☀️", "🌤️", "⛅", "☁️", "🌧️", "🌨️", "⛈️", "🌫️"]


@dataclass
class Location:
    """A place the user can ask about."""

    name: str = "Unknown"
    country: str = ""
    country_code: str = ""
    admin1: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    timezone: str = "UTC"
    population: float | None = None

    @property
    def display_name(self) -> str:
        parts = [p for p in (self.name, self.admin1, self.country) if p]
        return ", ".join(parts) if parts else "Unknown location"

    @property
    def short_name(self) -> str:
        return self.name or "Unknown"

    @property
    def tz_name(self) -> str:
        return self.timezone or "UTC"

    def cache_key(self) -> str:
        return f"{self.latitude:.3f},{self.longitude:.3f}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "country": self.country,
            "country_code": self.country_code,
            "admin1": self.admin1,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": self.timezone,
            "population": self.population,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Location":
        return cls(
            name=sval(data, "name", default="Unknown"),
            country=sval(data, "country"),
            country_code=sval(data, "country_code"),
            admin1=sval(data, "admin1"),
            latitude=fval(data, "latitude", default=0.0),
            longitude=fval(data, "longitude", default=0.0),
            timezone=sval(data, "timezone", default="UTC") or "UTC",
            population=fval(data, "population"),
        )


@dataclass
class AirQuality:
    aqi: float | None
    pm2_5: float | None
    pm10: float | None

    @property
    def available(self) -> bool:
        return self.aqi is not None

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "AirQuality | None":
        if not payload:
            return None
        current = payload.get("current") or {}
        aqi = fval(current, "us_aqi")
        if aqi is None:
            return None
        return cls(
            aqi=aqi,
            pm2_5=fval(current, "pm2_5"),
            pm10=fval(current, "pm10"),
        )


@dataclass
class CurrentWeather:
    temperature: float
    feels_like: float | None
    condition_code: int
    condition_text: str
    icon: str
    humidity: int
    wind_speed: float | None
    wind_direction: int | None
    wind_gusts: float | None
    pressure: float | None
    visibility_m: float | None
    cloud_cover: int | None
    uv_index: float | None
    is_day: bool
    precipitation: float | None
    precipitation_probability: int | None
    dew_point: float | None = None
    sunrise: str = ""
    sunset: str = ""


@dataclass
class HourlyForecast:
    time: str
    temperature: float | None
    precipitation_probability: int | None
    precipitation: float | None
    condition_code: int
    condition_text: str
    icon: str
    wind_speed: float | None
    is_day: bool = True
    wind_direction: int | None = None
    visibility_m: float | None = None
    dew_point: float | None = None
    feels_like: float | None = None


@dataclass
class DailyForecast:
    date: str
    temp_max: float | None
    temp_min: float | None
    condition_code: int
    condition_text: str
    icon: str
    precipitation_probability: int | None
    precipitation_sum: float | None
    uv_index_max: float | None
    sunrise: str = ""
    sunset: str = ""
    wind_max: float | None = None
    feels_like_max: float | None = None


@dataclass
class WeatherData:
    """A fully validated weather snapshot for one location."""

    location: Location
    current: CurrentWeather
    hourly: list[HourlyForecast] = field(default_factory=list)
    daily: list[DailyForecast] = field(default_factory=list)
    air_quality: AirQuality | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "live"  # "live" | "cache" | "demo"

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def from_api_json(
        cls,
        payload: dict[str, Any],
        location: Location,
        air_quality_payload: dict[str, Any] | None = None,
        source: str = "live",
    ) -> "WeatherData":
        """Parse and validate a forecast payload into a WeatherData object."""
        try:
            require_keys(payload, "current")
        except ValueError as exc:
            raise InvalidResponseError(str(exc)) from exc
        current = payload["current"]

        temperature = fval(current, "temperature_2m")
        humidity = ival(current, "relative_humidity_2m")
        if temperature is None or humidity is None:
            raise InvalidResponseError(
                "Forecast response is missing essential current fields"
            )

        is_day = bool(ival(current, "is_day", default=1))
        code = ival(current, "weather_code")
        condition_text, icon = condition_from_code(code, is_day)

        tz_name = location.tz_name
        daily = payload.get("daily") or {}
        sunrise = cls._first_daily_value(daily, "sunrise")
        sunset = cls._first_daily_value(daily, "sunset")

        utc_offset = ival(payload, "utc_offset_seconds")
        precip_prob = cls._current_precipitation_probability(payload, utc_offset)

        current_obj = CurrentWeather(
            temperature=temperature,
            feels_like=fval(current, "apparent_temperature"),
            condition_code=code or 0,
            condition_text=condition_text,
            icon=icon,
            humidity=humidity,
            wind_speed=fval(current, "wind_speed_10m"),
            wind_direction=ival(current, "wind_direction_10m"),
            wind_gusts=fval(current, "wind_gusts_10m"),
            pressure=fval(current, "pressure_msl"),
            visibility_m=fval(current, "visibility"),
            cloud_cover=ival(current, "cloud_cover"),
            uv_index=fval(current, "uv_index"),
            is_day=is_day,
            precipitation=fval(current, "precipitation"),
            precipitation_probability=precip_prob,
            dew_point=fval(current, "dew_point_2m"),
            sunrise=sunrise,
            sunset=sunset,
        )

        hourly = cls._parse_hourly(payload, tz_name)
        daily_list = cls._parse_daily(payload, tz_name)

        return cls(
            location=location,
            current=current_obj,
            hourly=hourly,
            daily=daily_list,
            air_quality=AirQuality.from_payload(air_quality_payload),
            source=source,
        )

    @staticmethod
    def _first_daily_value(daily: dict[str, Any], key: str) -> str:
        """Return the first element of a daily array field (e.g. sunrise)."""
        value = daily.get(key)
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, str):
            return value
        return ""

    @staticmethod
    def _current_precipitation_probability(
        payload: dict[str, Any], utc_offset: int | None
    ) -> int | None:
        """Open-Meteo exposes current rain probability inside the hourly arrays.

        The hourly timestamps are local wall-clock strings, so the match is
        made against the location's current LOCAL hour computed from the
        ``utc_offset_seconds`` the API reported for that location.
        """
        hourly = payload.get("hourly") or {}
        times = hourly.get("time")
        probs = hourly.get("precipitation_probability")
        if not times or not probs or len(times) != len(probs):
            return None
        offset = int(utc_offset or 0)
        local_now = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + offset, timezone.utc
        ).strftime("%Y-%m-%dT%H:00")
        for t, p in zip(times, probs):
            if str(t)[:13] == local_now[:13]:
                return int(p) if p is not None else None
        # Hour boundary rolled over mid-request: use the next upcoming hour.
        for t, p in zip(times, probs):
            if str(t)[:13] >= local_now[:13]:
                return int(p) if p is not None else None
        return int(probs[0]) if probs[0] is not None else None

    @staticmethod
    def _parse_hourly(payload: dict[str, Any], tz_name: str) -> list[HourlyForecast]:
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        temps = hourly.get("temperature_2m") or []
        feels = hourly.get("apparent_temperature") or []
        probs = hourly.get("precipitation_probability") or []
        precips = hourly.get("precipitation") or []
        codes = hourly.get("weather_code") or []
        winds = hourly.get("wind_speed_10m") or []
        wind_dirs = hourly.get("wind_direction_10m") or []
        vis = hourly.get("visibility") or []
        dews = hourly.get("dew_point_2m") or []
        is_days = hourly.get("is_day") or []
        if not times:
            return []

        now_naive = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        result: list[HourlyForecast] = []
        for idx, raw_time in enumerate(times):
            dt = parse_iso_time(raw_time, tz_name)
            if dt is not None and dt < now_naive:
                continue
            code = ival({"v": codes[idx]}, "v") if idx < len(codes) else None
            is_day = bool(ival({"v": is_days[idx]}, "v", default=1)) if idx < len(is_days) else True
            text, icon = condition_from_code(code, is_day)
            result.append(
                HourlyForecast(
                    time=str(raw_time),
                    temperature=fval({"v": temps[idx]}, "v") if idx < len(temps) else None,
                    precipitation_probability=ival({"v": probs[idx]}, "v")
                    if idx < len(probs) else None,
                    precipitation=fval({"v": precips[idx]}, "v")
                    if idx < len(precips) else None,
                    condition_code=code or 0,
                    condition_text=text,
                    icon=icon,
                    wind_speed=fval({"v": winds[idx]}, "v") if idx < len(winds) else None,
                    is_day=is_day,
                    wind_direction=ival({"v": wind_dirs[idx]}, "v")
                    if idx < len(wind_dirs) else None,
                    visibility_m=fval({"v": vis[idx]}, "v") if idx < len(vis) else None,
                    dew_point=fval({"v": dews[idx]}, "v") if idx < len(dews) else None,
                    feels_like=fval({"v": feels[idx]}, "v") if idx < len(feels) else None,
                )
            )
            if len(result) >= 24:
                break
        return result

    @staticmethod
    def _parse_daily(payload: dict[str, Any], tz_name: str) -> list[DailyForecast]:
        daily = payload.get("daily") or {}
        dates = daily.get("time") or []
        if not dates:
            return []
        result: list[DailyForecast] = []
        for idx, raw_date in enumerate(dates):
            code = ival({"v": daily.get("weather_code", [])[idx]}, "v") \
                if idx < len(daily.get("weather_code") or []) else None
            text, icon = condition_from_code(code, True)
            result.append(
                DailyForecast(
                    date=str(raw_date),
                    temp_max=fval({"v": (daily.get("temperature_2m_max") or [])[idx]}, "v")
                    if idx < len(daily.get("temperature_2m_max") or []) else None,
                    temp_min=fval({"v": (daily.get("temperature_2m_min") or [])[idx]}, "v")
                    if idx < len(daily.get("temperature_2m_min") or []) else None,
                    condition_code=code or 0,
                    condition_text=text,
                    icon=icon,
                    precipitation_probability=ival(
                        {"v": (daily.get("precipitation_probability_max") or [])[idx]},
                        "v",
                    ) if idx < len(daily.get("precipitation_probability_max") or []) else None,
                    precipitation_sum=fval(
                        {"v": (daily.get("precipitation_sum") or [])[idx]}, "v",
                    ) if idx < len(daily.get("precipitation_sum") or []) else None,
                    uv_index_max=fval(
                        {"v": (daily.get("uv_index_max") or [])[idx]}, "v",
                    ) if idx < len(daily.get("uv_index_max") or []) else None,
                    sunrise=sval({"v": (daily.get("sunrise") or [])[idx]}, "v")
                    if idx < len(daily.get("sunrise") or []) else "",
                    sunset=sval({"v": (daily.get("sunset") or [])[idx]}, "v")
                    if idx < len(daily.get("sunset") or []) else "",
                    wind_max=fval(
                        {"v": (daily.get("wind_speed_10m_max") or [])[idx]}, "v",
                    ) if idx < len(daily.get("wind_speed_10m_max") or []) else None,
                    feels_like_max=fval(
                        {"v": (daily.get("apparent_temperature_max") or [])[idx]}, "v",
                    ) if idx < len(daily.get("apparent_temperature_max") or []) else None,
                )
            )
        return result
