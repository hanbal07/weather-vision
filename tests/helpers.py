"""Shared fixtures: realistic weather objects and Open-Meteo-style payloads."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.weather_models import (
    AirQuality,
    CurrentWeather,
    DailyForecast,
    HourlyForecast,
    Location,
    WeatherData,
)


def make_weather(
    temp: float = 22.0,
    feels_like: float | None = None,
    humidity: int = 50,
    wind: float = 12.0,
    pressure: float = 1013.0,
    visibility_m: float = 15000.0,
    uv: float | None = 2.0,
    is_day: bool = True,
    code: int = 0,
    cloud: int = 10,
    rain_prob: int = 5,
    precipitation: float = 0.0,
    wind_direction: int = 200,
    tz: str = "Asia/Karachi",
    source: str = "live",
) -> WeatherData:
    location = Location(
        name="Testville",
        country="Testland",
        country_code="TT",
        latitude=31.5,
        longitude=74.3,
        timezone=tz,
    )
    current = CurrentWeather(
        temperature=temp,
        feels_like=feels_like if feels_like is not None else temp,
        condition_code=code,
        condition_text="Clear sky",
        icon="☀️" if is_day else "🌙",
        humidity=humidity,
        wind_speed=wind,
        wind_direction=wind_direction,
        wind_gusts=wind + 8.0,
        pressure=pressure,
        visibility_m=visibility_m,
        cloud_cover=cloud,
        uv_index=uv,
        is_day=is_day,
        precipitation=precipitation,
        precipitation_probability=rain_prob,
        sunrise="2026-08-16T06:10",
        sunset="2026-08-16T18:50",
    )
    hourly = []
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for i in range(24):
        hourly.append(HourlyForecast(
            time=(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00"),
            temperature=temp + 2.0 * (i % 6) - 3.0,
            precipitation_probability=rain_prob,
            precipitation=0.0,
            condition_code=code,
            condition_text="Clear sky",
            icon="☀️",
            wind_speed=wind,
            is_day=True,
        ))
    daily = [
        DailyForecast(
            date=(base + timedelta(days=d)).strftime("%Y-%m-%d"),
            temp_max=temp + 4,
            temp_min=temp - 4,
            condition_code=code,
            condition_text="Clear sky",
            icon="☀️",
            precipitation_probability=rain_prob,
            precipitation_sum=0.0,
            uv_index_max=6.0,
            sunrise="2026-08-16T06:10",
            sunset="2026-08-16T18:50",
        )
        for d in range(7)
    ]
    return WeatherData(
        location=location,
        current=current,
        hourly=hourly,
        daily=daily,
        air_quality=AirQuality(aqi=40.0, pm2_5=10.0, pm10=20.0),
        fetched_at=datetime.now(timezone.utc),
        source=source,
    )


def sample_forecast_payload() -> dict[str, Any]:
    """A minimal but structurally complete Open-Meteo forecast response.

    Times are generated in the location's local timezone (Asia/Karachi) so the
    24 hourly entries are all in the future, matching real API behaviour.
    """
    from zoneinfo import ZoneInfo

    base = datetime.now(ZoneInfo("Asia/Karachi")).replace(minute=0, second=0, microsecond=0)
    times = [(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(24)]
    days = [(base + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(7)]
    return {
        "latitude": 31.5,
        "longitude": 74.3,
        "timezone": "Asia/Karachi",
        "current": {
            "temperature_2m": 30.2,
            "relative_humidity_2m": 61,
            "apparent_temperature": 32.4,
            "is_day": 1,
            "precipitation": 0.0,
            "weather_code": 2,
            "cloud_cover": 35,
            "pressure_msl": 1011.2,
            "wind_speed_10m": 12.4,
            "wind_direction_10m": 240,
            "wind_gusts_10m": 20.1,
            "visibility": 12000.0,
            "uv_index": 6.5,
        },
        "hourly": {
            "time": times,
            "temperature_2m": [20.0 + (i % 6) for i in range(24)],
            "precipitation_probability": [10] * 24,
            "precipitation": [0.0] * 24,
            "weather_code": [2] * 24,
            "wind_speed_10m": [10.0] * 24,
            "wind_direction_10m": [240] * 24,
            "is_day": [1] * 24,
            "visibility": [12000.0] * 24,
        },
        "daily": {
            "time": days,
            "weather_code": [2] * 7,
            "temperature_2m_max": [34.0] * 7,
            "temperature_2m_min": [22.0] * 7,
            "apparent_temperature_max": [36.0] * 7,
            "precipitation_probability_max": [15] * 7,
            "precipitation_sum": [0.0] * 7,
            "uv_index_max": [7.5] * 7,
            "sunrise": ["2026-08-16T06:10"] * 7,
            "sunset": ["2026-08-16T18:50"] * 7,
        },
    }


def sample_air_quality_payload() -> dict[str, Any]:
    return {"current": {"us_aqi": 78.0, "pm2_5": 22.4, "pm10": 38.1}}


def make_location(name: str = "Lahore", lat: float = 31.55, lon: float = 74.34) -> Location:
    return Location(
        name=name,
        country="Pakistan",
        country_code="PK",
        latitude=lat,
        longitude=lon,
        timezone="Asia/Karachi",
    )
