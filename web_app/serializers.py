"""Serialize WeatherVision domain objects into JSON for the web frontend.

Mirrors the payload produced by ``site/js/weather.js`` (the GitHub-Pages
frontend): every measurement is emitted as its raw metric number PLUS a ready
formatted ``*_display`` string, missing values are ``null`` (never invented),
and the derived sections (score / why / insights / activity / alerts) follow
the same rules as the static-site data layer.

The desktop GUI used QPainter/QLabel to render values; the web frontend
receives the same data as JSON. All unit conversion happens here so the
browser never needs to duplicate formatting logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.config import VERSION
from app.models.weather_models import WeatherData
from app.services.alert_engine import WeatherAlert
from app.services.intelligence_engine import (
    ActivityResult,
    Insight,
    ScoreResult,
)
from app.utils import units as U
from app.utils.helpers import parse_iso_time

NOT_AVAILABLE = "Not available"

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

# ScoreComponent.label -> payload factor key (parity with the static site).
_LABEL_KEY = {
    "Temperature": "temperature",
    "Humidity": "humidity",
    "Wind": "wind",
    "Rain probability": "rain",
    "Visibility": "visibility",
    "UV index": "uv",
}


def _local_time(tz_name: str) -> str:
    try:
        now = datetime.now(ZoneInfo(tz_name))
        return now.strftime("%H:%M")
    except Exception:
        return datetime.now().strftime("%H:%M")


def _utc_offset_seconds(tz_name: str) -> int | None:
    try:
        offset = datetime.now(ZoneInfo(tz_name)).utcoffset()
        return int(offset.total_seconds()) if offset is not None else 0
    except Exception:
        return 0


def _clock(value: str, tz_name: str) -> str:
    dt = parse_iso_time(value, tz_name)
    return dt.strftime("%H:%M") if dt else ""


def _disp(value: Any, formatter: Any) -> str:
    """Return a formatted display string, or "Not available" when null."""
    if value is None:
        return NOT_AVAILABLE
    return formatter(value)


def _round(value: float | None, ndigits: int = 1) -> float | None:
    if value is None:
        return None
    return round(value, ndigits)


def _compass(degrees: int | None) -> str:
    if degrees is None:
        return NOT_AVAILABLE
    return U.wind_direction(degrees)


def serialize_weather(
    weather: WeatherData,
    temp_unit: str,
    wind_unit: str,
    pressure_unit: str,
    is_favorite: bool,
    score: ScoreResult | None = None,
    why_lines: list[dict[str, str]] | None = None,
    activities: list[ActivityResult] | None = None,
    insights: list[Insight] | None = None,
    alerts: list[WeatherAlert] | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    cur = weather.current
    tz = weather.location.tz_name
    utc_offset = _utc_offset_seconds(tz)

    payload: dict[str, Any] = {
        "meta": {
            "app": "WeatherVision",
            "version": VERSION,
            "source": weather.source,
            "demo": weather.source == "demo",
            "fetched_at": weather.fetched_at.isoformat(),
            "is_favorite": is_favorite,
            "data_note": "Latest available observations and model data",
            "attribution": "Open-Meteo",
        },
        "location": {
            **weather.location.to_dict(),
            "display_name": weather.location.display_name,
            "local_time": _local_time(tz),
            "utc_offset_seconds": utc_offset,
        },
        "units": {
            "temp": temp_unit,
            "wind": wind_unit,
            "pressure": pressure_unit,
        },
        "current": {
            "temperature": _round(cur.temperature),
            "temperature_display": _disp(cur.temperature, lambda v: U.format_temp(v, temp_unit)),
            "feels_like": _round(cur.feels_like),
            "feels_like_display": _disp(cur.feels_like, lambda v: U.format_temp(v, temp_unit)),
            "condition": cur.condition_text,
            "icon": cur.icon,
            "humidity": cur.humidity,
            "humidity_display": f"{cur.humidity}%",
            "pressure": _round(cur.pressure, 0),
            "pressure_display": _disp(cur.pressure, lambda v: U.format_pressure(v, pressure_unit)),
            "wind": _round(cur.wind_speed, 0),
            "wind_display": _disp(cur.wind_speed, lambda v: U.format_wind(v, wind_unit)),
            "wind_direction": _compass(cur.wind_direction),
            "wind_direction_deg": cur.wind_direction,
            "wind_gusts": _round(cur.wind_gusts, 0),
            "wind_gusts_display": _disp(cur.wind_gusts, lambda v: U.format_wind(v, wind_unit)),
            "visibility": _round(cur.visibility_m, 0),
            "visibility_display": _disp(cur.visibility_m, lambda v: U.format_visibility(v, wind_unit)),
            "visibility_km": _round(cur.visibility_m / 1000.0, 1) if cur.visibility_m is not None else None,
            "uv": _round(cur.uv_index, 1),
            "uv_display": _uv_display(cur.uv_index, cur.is_day),
            "precipitation": _round(cur.precipitation, 1),
            "precipitation_display": _disp(cur.precipitation, lambda v: f"{v:.1f} mm"),
            "precipitation_probability": cur.precipitation_probability,
            "precipitation_probability_display": _disp(
                cur.precipitation_probability, lambda v: f"{v}%"
            ),
            "precipitation_period_label": "",
            "cloud_cover": cur.cloud_cover,
            "cloud_cover_display": _disp(cur.cloud_cover, lambda v: f"{v}%"),
            "dew_point": _round(cur.dew_point, 1),
            "dew_point_display": _disp(cur.dew_point, lambda v: U.format_temp(v, temp_unit)),
            "sunrise": _clock(cur.sunrise, tz),
            "sunset": _clock(cur.sunset, tz),
            "is_day": cur.is_day,
        },
        "hourly": [
            {
                "time": _clock(h.time, tz),
                "iso": h.time,
                "icon": h.icon,
                "condition": h.condition_text,
                "is_now": idx == 0,
                "temperature": _round(h.temperature),
                "temperature_display": _disp(h.temperature, lambda v: U.format_temp(v, temp_unit)),
                "feels_like": _round(h.feels_like, 1) if h.feels_like is not None else None,
                "feels_like_display": _disp(h.feels_like, lambda v: U.format_temp(v, temp_unit)),
                "precip_prob": h.precipitation_probability,
                "precipitation": _round(h.precipitation, 1),
                "precipitation_display": _disp(h.precipitation, lambda v: f"{v:.1f} mm"),
                "wind": _round(h.wind_speed, 0),
                "wind_display": _disp(h.wind_speed, lambda v: U.format_wind(v, wind_unit)),
                "wind_direction": _compass(h.wind_direction),
                "wind_direction_deg": h.wind_direction,
                "visibility": _round(h.visibility_m, 0),
                "visibility_display": _disp(h.visibility_m, lambda v: U.format_visibility(v, wind_unit)),
                "is_day": h.is_day,
            }
            for idx, h in enumerate(weather.hourly)
        ],
        "daily": [
            {
                "day": _day_label(d.date, tz),
                "date": _date_label(d.date, tz),
                "iso": d.date,
                "icon": d.icon,
                "condition": d.condition_text,
                "high": _round(d.temp_max),
                "low": _round(d.temp_min),
                "high_display": _disp(d.temp_max, lambda v: U.format_temp(v, temp_unit)),
                "low_display": _disp(d.temp_min, lambda v: U.format_temp(v, temp_unit)),
                "feels_like_max": _round(d.feels_like_max),
                "feels_like_max_display": _disp(d.feels_like_max, lambda v: U.format_temp(v, temp_unit)),
                "precip_prob": d.precipitation_probability,
                "precipitation_sum": _round(d.precipitation_sum, 1),
                "precipitation_sum_display": _disp(d.precipitation_sum, lambda v: f"{v:.1f} mm"),
                "uv": _round(d.uv_index_max, 1),
                "uv_display": _uv_display(d.uv_index_max, True),
                "wind_max": _round(d.wind_max, 0),
                "wind_max_display": _disp(d.wind_max, lambda v: U.format_wind(v, wind_unit)),
                "sunrise": _clock(d.sunrise, tz),
                "sunset": _clock(d.sunset, tz),
            }
            for d in weather.daily
        ],
        "air_quality": _air_quality(weather),
        "summary": summary or "",
    }

    if score is not None:
        payload["score"] = {
            "total": score.total,
            "grade": score.grade,
            "grade_label": score.grade,
            "color": GRADE_COLORS.get(score.grade, "#64748b"),
            "factor_count": score.factor_count,
            "available_factors": score.available_factors,
            "note": _score_note(score),
            "components": [
                {
                    "key": _LABEL_KEY.get(c.label, ""),
                    "label": c.label,
                    "score": c.score,
                    "weight": round(c.weight, 3),
                    "value": c.value,
                    "note": c.note,
                }
                for c in score.components
            ],
        }
    if why_lines:
        payload["why"] = why_lines
    if activities is not None:
        items = [
            {
                "name": a.name,
                "icon": a.icon,
                "score": a.score,
                "label": a.label,
                "reasons": a.reasons,
            }
            for a in activities
        ]
        payload["activities"] = items
        payload["activity"] = {
            "verdict": _activity_verdict(activities[0] if activities else None),
            "items": items,
        }
    if insights is not None:
        payload["insights"] = [_insight(i) for i in insights]
    if alerts is not None:
        payload["alerts"] = [_alert(a) for a in alerts]

    return payload


def _score_note(score: ScoreResult) -> str:
    if score.available_factors >= score.factor_count:
        return "Based on all six measurements."
    return (
        f"Based on {score.available_factors} of 6 available measurements — "
        "the rest are not provided by the data source."
    )


def _uv_display(uv: float | None, is_day: bool) -> str:
    if uv is None:
        return NOT_AVAILABLE
    return f"{uv:.1f}" if is_day else f"{uv:.0f}"


def _activity_verdict(best: ActivityResult | None) -> dict[str, str]:
    if best is None:
        return {"icon": "🛰️", "text": "No data", "detail": "No activity guidance yet — weather data is unavailable."}
    if best.score >= 80:
        return {"icon": "👍", "text": "Great for today",
                "detail": f"{best.name} and similar outdoor plans are well-suited to the current conditions."}
    if best.score >= 60:
        return {"icon": "🙂", "text": "Good for today",
                "detail": f"Outdoor plans like {best.name.lower()} should be fine in the current conditions."}
    if best.score >= 40:
        return {"icon": "😐", "text": "Mixed today",
                "detail": f"Conditions are workable, but {best.name.lower()} needs some planning around the weather."}
    if best.score >= 20:
        return {"icon": "🌧️", "text": "Poor for today",
                "detail": f"Current conditions are not ideal for {best.name.lower()} or similar outdoor plans."}
    return {"icon": "🚫", "text": "Not recommended",
            "detail": "Current conditions are very poor for outdoor activity."}


def _air_quality(weather: WeatherData) -> dict[str, Any] | None:
    aq = weather.air_quality
    if aq is None or not aq.available:
        return None
    return {
        "aqi": aq.aqi,
        "label": U.aqi_category(aq.aqi),
        "color": _aqi_color(aq.aqi),
        "pm25": aq.pm2_5,
        "pm25_display": _disp(aq.pm2_5, lambda v: f"{v:.1f} µg/m³"),
        "pm10": aq.pm10,
        "pm10_display": _disp(aq.pm10, lambda v: f"{v:.1f} µg/m³"),
        "note": "US AQI — Open-Meteo Air Quality API",
    }


def _aqi_color(aqi: float) -> str:
    if aqi <= 50:
        return "#22c55e"
    if aqi <= 100:
        return "#eab308"
    if aqi <= 150:
        return "#f97316"
    if aqi <= 200:
        return "#ef4444"
    if aqi <= 300:
        return "#a855f7"
    return "#7f1d1d"


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
