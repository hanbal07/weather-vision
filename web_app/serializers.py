"""Serialize WeatherVision domain objects into JSON for the web frontend.

The desktop GUI used QPainter/QLabel to render values; the web frontend
receives the same data as JSON. All unit conversion happens here so the
browser never needs to duplicate formatting logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.models.weather_models import WeatherData
from app.services.alert_engine import WeatherAlert
from app.services.intelligence_engine import (
    ActivityResult,
    Insight,
    ScoreResult,
)
from app.utils import units as U
from app.utils.helpers import parse_iso_time

GRADE_COLORS = {
    "Excellent": "#22c55e",
    "Good": "#84cc16",
    "Moderate": "#f59e0b",
    "Poor": "#f97316",
    "Very Poor": "#ef4444",
}

LEVEL_COLORS = {
    "INFO": "#64748b",
    "LOW": "#38bdf8",
    "MODERATE": "#f59e0b",
    "HIGH": "#f97316",
    "CRITICAL": "#ef4444",
}


def _local_time(tz_name: str) -> str:
    try:
        now = datetime.now(ZoneInfo(tz_name))
        return now.strftime("%H:%M")
    except Exception:
        return datetime.now().strftime("%H:%M")


def _clock(value: str, tz_name: str) -> str:
    dt = parse_iso_time(value, tz_name)
    return dt.strftime("%H:%M") if dt else "—"


def serialize_weather(
    weather: WeatherData,
    temp_unit: str,
    wind_unit: str,
    pressure_unit: str,
    is_favorite: bool,
    score: ScoreResult | None = None,
    why_lines: list[str] | None = None,
    activities: list[ActivityResult] | None = None,
    insights: list[Insight] | None = None,
    alerts: list[WeatherAlert] | None = None,
) -> dict[str, Any]:
    cur = weather.current
    tz = weather.location.tz_name

    payload: dict[str, Any] = {
        "meta": {
            "app": "WeatherVision",
            "source": weather.source,
            "demo": weather.source == "demo",
            "fetched_at": weather.fetched_at.isoformat(),
            "is_favorite": is_favorite,
        },
        "location": {
            **weather.location.to_dict(),
            "display_name": weather.location.display_name,
            "local_time": _local_time(tz),
        },
        "units": {
            "temp": temp_unit,
            "wind": wind_unit,
            "pressure": pressure_unit,
        },
        "current": {
            "temperature": round(cur.temperature, 1),
            "temperature_display": U.format_temp(cur.temperature, temp_unit),
            "feels_like": round(cur.feels_like, 1),
            "feels_like_display": U.format_temp(cur.feels_like, temp_unit),
            "condition": cur.condition_text,
            "icon": cur.icon,
            "humidity": f"{cur.humidity}%",
            "pressure": U.format_pressure(cur.pressure, pressure_unit),
            "wind": U.format_wind(cur.wind_speed, wind_unit),
            "wind_direction": U.wind_direction(cur.wind_direction),
            "wind_gusts": U.format_wind(cur.wind_gusts, wind_unit),
            "visibility": U.format_visibility(cur.visibility_m, wind_unit),
            "uv": f"{cur.uv_index:.1f}" if cur.uv_index is not None else "n/a",
            "precipitation": f"{cur.precipitation:.1f} mm",
            "precipitation_probability": f"{cur.precipitation_probability}%",
            "cloud_cover": f"{cur.cloud_cover}%",
            "sunrise": _clock(cur.sunrise, tz),
            "sunset": _clock(cur.sunset, tz),
            "is_day": cur.is_day,
        },
        "hourly": [
            {
                "time": _clock(h.time, tz),
                "icon": h.icon,
                "condition": h.condition_text,
                "temperature": round(U.convert_temp(h.temperature, temp_unit), 1),
                "precip_prob": h.precipitation_probability,
                "precipitation": round(h.precipitation, 1),
                "wind": round(U.convert_wind(h.wind_speed, wind_unit), 1),
                "is_day": h.is_day,
            }
            for h in weather.hourly
        ],
        "daily": [
            {
                "day": _day_label(d.date, tz),
                "date": _date_label(d.date, tz),
                "icon": d.icon,
                "condition": d.condition_text,
                "high": round(U.convert_temp(d.temp_max, temp_unit), 1),
                "low": round(U.convert_temp(d.temp_min, temp_unit), 1),
                "high_display": U.format_temp(d.temp_max, temp_unit),
                "low_display": U.format_temp(d.temp_min, temp_unit),
                "precip_prob": d.precipitation_probability,
                "precipitation_sum": round(d.precipitation_sum, 1),
                "uv": d.uv_index_max,
                "sunrise": _clock(d.sunrise, tz),
                "sunset": _clock(d.sunset, tz),
            }
            for d in weather.daily
        ],
        "air_quality": _air_quality(weather),
    }

    if score is not None:
        payload["score"] = {
            "total": score.total,
            "grade": score.grade,
            "color": GRADE_COLORS.get(score.grade, "#64748b"),
            "components": [
                {
                    "label": c.label,
                    "score": c.score,
                    "weight": round(c.weight, 2),
                    "value": _component_value(c.label, weather, temp_unit, wind_unit),
                    "note": c.note,
                }
                for c in score.components
            ],
        }
    if why_lines:
        payload["why"] = why_lines
    if activities is not None:
        payload["activities"] = [
            {
                "name": a.name,
                "icon": a.icon,
                "score": a.score,
                "label": a.label,
                "reasons": a.reasons,
            }
            for a in activities
        ]
    if insights is not None:
        payload["insights"] = [_insight(i) for i in insights]
    if alerts is not None:
        payload["alerts"] = [_alert(a) for a in alerts]

    return payload


def _air_quality(weather: WeatherData) -> dict[str, Any] | None:
    aq = weather.air_quality
    if aq is None or not aq.available:
        return None
    return {
        "aqi": aq.aqi,
        "label": U.aqi_category(aq.aqi),
        "pm25": aq.pm2_5,
        "pm10": aq.pm10,
    }


def _component_value(label: str, weather: WeatherData, temp_unit: str, wind_unit: str) -> str:
    cur = weather.current
    if label == "Temperature":
        return U.format_temp(cur.temperature, temp_unit)
    if label == "Humidity":
        return f"{cur.humidity}%"
    if label == "Wind":
        return U.format_wind(cur.wind_speed, wind_unit)
    if label == "Rain probability":
        return f"{cur.precipitation_probability}%"
    if label == "Visibility":
        return U.format_visibility(cur.visibility_m, wind_unit)
    if label == "UV index":
        return f"{cur.uv_index:.1f}" if cur.uv_index is not None else "n/a"
    return "—"


def _day_label(date_str: str, tz: str) -> str:
    dt = parse_iso_time(f"{date_str}T12:00", tz)
    return dt.strftime("%a") if dt else date_str


def _date_label(date_str: str, tz: str) -> str:
    dt = parse_iso_time(f"{date_str}T12:00", tz)
    return dt.strftime("%b %d") if dt else date_str


def _insight(insight: Insight) -> dict[str, Any]:
    return {
        "icon": insight.icon,
        "title": insight.title,
        "message": insight.message,
        "level": insight.level,
        "color": LEVEL_COLORS.get(insight.level, "#64748b"),
    }


def _alert(alert: WeatherAlert) -> dict[str, Any]:
    return {
        "level": alert.level,
        "icon": alert.icon,
        "title": alert.title,
        "message": alert.message,
        "color": LEVEL_COLORS.get(alert.level, "#64748b"),
    }
