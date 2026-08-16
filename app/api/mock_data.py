"""Deterministic mock weather provider for Demonstration Mode.

Used ONLY when the user explicitly enables Demo Mode. Every returned value is
realistic (temperature falls with latitude and night, rain probability follows
random-but-seeded patterns) but is clearly labelled with ``source="demo"`` so
the UI can always show the **DEMO DATA — NOT REAL-TIME** badge.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.models.weather_models import (
    AirQuality,
    CurrentWeather,
    DailyForecast,
    HourlyForecast,
    Location,
    WeatherData,
)
from app.utils.helpers import condition_from_code

_CLEAR_CODES = (0, 1, 2, 3)
_RAIN_CODES = (61, 63, 65, 80, 81)
_CLOUDY_CODES = (2, 3)
_THUNDER_CODES = (95, 96)


class MockWeatherProvider:
    """Generates a full :class:`WeatherData` snapshot without network access."""

    def get_weather(self, location: Location) -> WeatherData:
        rng = self._seeded_rng(location)
        base_temp = self._base_temp(location.latitude, rng)

        now = datetime.now(timezone.utc)
        hour_of_day = now.hour

        is_day = 6 <= hour_of_day <= 19
        code = rng.choice(_CLEAR_CODES + _RAIN_CODES if rng.random() < 0.55 else _CLEAR_CODES)
        if rng.random() < 0.05:
            code = rng.choice(_THUNDER_CODES)
        text, icon = condition_from_code(code, is_day)

        diurnal = 4.0 * (1.0 - abs(hour_of_day - 14) / 10.0)
        temperature = base_temp + diurnal + rng.uniform(-1.5, 1.5)
        humidity = 40 + (0 if code in _CLEAR_CODES else rng.randint(10, 35))
        wind = rng.uniform(4, 26)
        rain_prob = rng.randint(0, 15) if code in _CLEAR_CODES else rng.randint(45, 90)
        uv = max(0.0, (temperature - 12) / 2.5 + rng.uniform(-0.5, 1.0)) if is_day else 0.0
        visibility_m = rng.randint(8, 20) * 1000.0

        current = CurrentWeather(
            temperature=temperature,
            feels_like=temperature + (2.5 if humidity > 70 else -2.0 if wind > 18 else 0.0),
            condition_code=code,
            condition_text=text,
            icon=icon,
            humidity=round(humidity),
            wind_speed=wind,
            wind_direction=rng.randint(0, 359),
            wind_gusts=wind + rng.uniform(2, 12),
            pressure=rng.randint(995, 1030),
            visibility_m=visibility_m,
            cloud_cover=rng.randint(5, 80) if code not in _CLEAR_CODES[:1] else rng.randint(0, 20),
            uv_index=uv,
            is_day=is_day,
            precipitation=0.0 if code in _CLEAR_CODES else rng.uniform(0, 3),
            precipitation_probability=rain_prob,
            sunrise=f"{now.strftime('%Y-%m-%d')}T06:15",
            sunset=f"{now.strftime('%Y-%m-%d')}T18:45",
        )

        hourly: list[HourlyForecast] = []
        for offset in range(24):
            h = (hour_of_day + offset) % 24
            h_is_day = 6 <= h <= 19
            h_code = code if offset < 8 else (rng.choice(_CLEAR_CODES) if rng.random() > 0.7 else code)
            h_text, h_icon = condition_from_code(h_code, h_is_day)
            h_diurnal = 4.0 * (1.0 - abs(h - 14) / 10.0)
            h_prob = max(0, min(95, rain_prob + rng.randint(-25, 15)))
            hourly.append(
                HourlyForecast(
                    time=(now + timedelta(hours=offset)).strftime("%Y-%m-%dT%H:00"),
                    temperature=base_temp + h_diurnal + rng.uniform(-1, 1),
                    precipitation_probability=h_prob,
                    precipitation=max(0.0, (h_prob - 60) / 25) if h_prob > 60 else 0.0,
                    condition_code=h_code,
                    condition_text=h_text,
                    icon=h_icon,
                    wind_speed=max(1.0, wind + rng.uniform(-4, 6)),
                    is_day=h_is_day,
                )
            )

        daily: list[DailyForecast] = []
        for day_offset in range(7):
            day = now + timedelta(days=day_offset)
            d_code = rng.choice(_CLEAR_CODES + _RAIN_CODES)
            d_text, d_icon = condition_from_code(d_code, True)
            d_max = base_temp + 6 + rng.uniform(-2, 2)
            d_min = base_temp - 3 + rng.uniform(-2, 2)
            daily.append(
                DailyForecast(
                    date=day.strftime("%Y-%m-%d"),
                    temp_max=d_max,
                    temp_min=d_min,
                    condition_code=d_code,
                    condition_text=d_text,
                    icon=d_icon,
                    precipitation_probability=rng.randint(0, 85),
                    precipitation_sum=rng.uniform(0, 12) if d_code in _RAIN_CODES else 0.0,
                    uv_index_max=8.0 + rng.uniform(-3, 2),
                    sunrise=f"{day.strftime('%Y-%m-%d')}T06:15",
                    sunset=f"{day.strftime('%Y-%m-%d')}T18:45",
                )
            )

        return WeatherData(
            location=location,
            current=current,
            hourly=hourly,
            daily=daily,
            air_quality=AirQuality(
                aqi=round(rng.randint(22, 95)),
                pm2_5=round(rng.uniform(6, 28), 1),
                pm10=round(rng.uniform(12, 45), 1),
            ),
            source="demo",
        )

    @staticmethod
    def _seeded_rng(location: Location) -> random.Random:
        seed = int(abs(location.latitude) * 1000) + int(abs(location.longitude) * 1000) + 7
        return random.Random(seed + datetime.now(timezone.utc).day)

    @staticmethod
    def _base_temp(latitude: float, rng: random.Random) -> float:
        seasonal = rng.randint(0, 12)  # crude seasonal drift
        return max(-5.0, 32.0 - abs(latitude) * 0.55 + seasonal)
