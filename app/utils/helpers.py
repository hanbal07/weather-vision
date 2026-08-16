"""Formatting helpers shared across the application.

Contains the WMO weather-code table, human-readable time formatting and a
friendly error-message mapper for the GUI.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.api.errors import (
    CityNotFoundError,
    InvalidResponseError,
    NetworkError,
    RateLimitError,
)

# WMO weather interpretation codes: code -> (label, day_icon, night_icon)
WMO_CODES: dict[int, tuple[str, str, str]] = {
    0: ("Clear sky", "☀️", "🌙"),
    1: ("Mainly clear", "🌤️", "🌙"),
    2: ("Partly cloudy", "⛅", "☁️"),
    3: ("Overcast", "☁️", "☁️"),
    45: ("Fog", "🌫️", "🌫️"),
    48: ("Rime fog", "🌫️", "🌫️"),
    51: ("Light drizzle", "🌦️", "🌧️"),
    53: ("Drizzle", "🌦️", "🌧️"),
    55: ("Dense drizzle", "🌧️", "🌧️"),
    56: ("Freezing drizzle", "🌧️", "🌧️"),
    57: ("Freezing drizzle", "🌧️", "🌧️"),
    61: ("Light rain", "🌦️", "🌧️"),
    63: ("Rain", "🌧️", "🌧️"),
    65: ("Heavy rain", "🌧️", "🌧️"),
    66: ("Freezing rain", "🌧️", "🌧️"),
    67: ("Freezing rain", "🌧️", "🌧️"),
    71: ("Light snow", "🌨️", "🌨️"),
    73: ("Snow", "❄️", "❄️"),
    75: ("Heavy snow", "❄️", "❄️"),
    77: ("Snow grains", "❄️", "❄️"),
    80: ("Light showers", "🌦️", "🌧️"),
    81: ("Rain showers", "🌧️", "🌧️"),
    82: ("Violent showers", "⛈️", "⛈️"),
    85: ("Snow showers", "🌨️", "🌨️"),
    86: ("Snow showers", "❄️", "❄️"),
    95: ("Thunderstorm", "⛈️", "⛈️"),
    96: ("Thunderstorm + hail", "⛈️", "⛈️"),
    99: ("Thunderstorm + hail", "⛈️", "⛈️"),
}

THUNDERSTORM_CODES = (95, 96, 99)
RAIN_CODES = (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82)
SNOW_CODES = (71, 73, 75, 77, 85, 86)


def condition_from_code(code: int | None, is_day: bool = True) -> tuple[str, str]:
    """Return ``(label, icon)`` for a WMO code, with a safe fallback."""
    if code is None:
        return ("Unknown", "🌡️")
    label, day_icon, night_icon = WMO_CODES.get(code, ("Unknown", "🌡️", "🌡️"))
    return label, (day_icon if is_day else night_icon)


def parse_iso_time(value: str | None, tz_name: str = "UTC") -> datetime | None:
    """Parse an ISO-8601 string such as '2026-08-16T14:00' into a tz-aware dt."""
    if not value:
        return None
    try:
        from zoneinfo import ZoneInfo

        naive = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if naive.tzinfo is None:
            try:
                return naive.replace(tzinfo=ZoneInfo(tz_name))
            except Exception:
                return naive.replace(tzinfo=ZoneInfo("UTC"))
        return naive
    except Exception:
        return None


def format_time(dt: datetime | None, fmt: str = "%H:%M") -> str:
    return dt.strftime(fmt) if dt else "—"


def format_date(dt: datetime | None) -> str:
    return dt.strftime("%a, %b %d") if dt else "—"


def day_name(dt: datetime | None) -> str:
    return dt.strftime("%a") if dt else "—"


def short_time_label(iso_str: str | None, tz_name: str = "UTC") -> str:
    dt = parse_iso_time(iso_str, tz_name)
    return format_time(dt)


def time_ago(dt: datetime | None) -> str:
    """Human-readable 'X minutes ago' relative to now (UTC)."""
    if dt is None:
        return "unknown time"
    from datetime import timezone

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = max(0, int((now - dt).total_seconds()))
    if seconds < 60:
        return "moments ago"
    if seconds < 3600:
        return f"{seconds // 60} minute{'s' if seconds // 60 != 1 else ''} ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def friendly_error(exc: BaseException) -> str:
    """Translate internal exceptions into user-friendly GUI messages."""
    if isinstance(exc, NetworkError):
        return (
            "Cannot reach the weather server. Please check your internet "
            "connection and try again."
        )
    if isinstance(exc, CityNotFoundError):
        return (
            "We couldn't find that location. Check the spelling or try a "
            "nearby city name."
        )
    if isinstance(exc, RateLimitError):
        return "Too many requests. Please wait a moment and try again."
    if isinstance(exc, InvalidResponseError):
        return "The weather service returned unexpected data. Please try again."
    if isinstance(exc, ValueError):
        return str(exc)
    return "Something went wrong while fetching weather data. Please try again."


def location_from_row(row: dict[str, Any]) -> Any:
    """Reconstruct a Location model from a database row (avoiding circular import)."""
    from app.models.weather_models import Location

    return Location(
        name=row.get("name") or "Unknown",
        country=row.get("country") or "",
        country_code=row.get("country_code") or "",
        admin1=row.get("admin1") or "",
        latitude=float(row.get("latitude") or 0.0),
        longitude=float(row.get("longitude") or 0.0),
        timezone=row.get("timezone") or "UTC",
    )
