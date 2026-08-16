"""Unit conversion and formatting helpers.

All values are stored internally in metric units (as returned by the API):
    temperature  °C
    wind         km/h
    pressure     hPa
    visibility   metres
    precipitation  mm

These helpers convert and format values for display. ``unit`` strings are
validated by SettingsManager, so they are guaranteed to be one of the
supported values.
"""
from __future__ import annotations

_MILES_PER_KM = 0.621371
_INHG_PER_HPA = 0.0295299830714


def convert_temp(celsius: float, unit: str = "C") -> float:
    return celsius * 9.0 / 5.0 + 32.0 if unit == "F" else celsius


def format_temp(celsius: float, unit: str = "C") -> str:
    value = convert_temp(celsius, unit)
    return f"{value:.0f}°{unit}"


def convert_wind(kmh: float, unit: str = "kmh") -> float:
    return kmh * _MILES_PER_KM if unit == "mph" else kmh


def format_wind(kmh: float, unit: str = "kmh") -> str:
    value = convert_wind(kmh, unit)
    return f"{value:.0f} {unit}"


def convert_pressure(hpa: float, unit: str = "hpa") -> float:
    return hpa * _INHG_PER_HPA if unit == "inHg" else hpa


def format_pressure(hpa: float, unit: str = "hpa") -> str:
    value = convert_pressure(hpa, unit)
    if unit == "inHg":
        return f"{value:.2f} inHg"
    return f"{value:.0f} hPa"


def convert_visibility(metres: float, unit: str = "kmh") -> float:
    """Return visibility in km (metric) or miles (imperial)."""
    km = metres / 1000.0
    return km * _MILES_PER_KM if unit == "mph" else km


def format_visibility(metres: float, unit: str = "kmh") -> str:
    value = convert_visibility(metres, unit)
    suffix = "mi" if unit == "mph" else "km"
    return f"{value:.1f} {suffix}"


def wind_direction(degrees: float | None) -> str:
    """Map a bearing in degrees to a 16-point compass label."""
    if degrees is None:
        return "—"
    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    index = int(((degrees % 360) + 11.25) // 22.5) % 16
    return directions[index]


def aqi_category(aqi: float | None) -> str:
    """Map a US AQI value to a category label."""
    if aqi is None:
        return "Unavailable"
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Sensitive"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"
