"""Tests for unit conversion utilities."""
from app.utils import units as U


def test_celsius_to_fahrenheit():
    assert U.convert_temp(0, "F") == 32.0
    assert U.convert_temp(100, "F") == 212.0
    assert U.format_temp(25, "F") == "77°F"


def test_celsius_stays_celsius():
    assert U.convert_temp(25, "C") == 25.0
    assert U.format_temp(25, "C") == "25°C"


def test_wind_conversion():
    assert U.convert_wind(10, "kmh") == 10.0
    assert round(U.convert_wind(10, "mph"), 2) == 6.21
    assert U.format_wind(10, "mph") == "6 mph"


def test_pressure_conversion():
    assert U.convert_pressure(1013, "hpa") == 1013.0
    assert round(U.convert_pressure(1013, "inHg"), 2) == 29.91
    assert "inHg" in U.format_pressure(1013, "inHg")


def test_visibility_conversion():
    assert U.convert_visibility(5000, "kmh") == 5.0
    assert round(U.convert_visibility(1609.34, "mph"), 1) == 1.0


def test_wind_direction_labels():
    assert U.wind_direction(0) == "N"
    assert U.wind_direction(90) == "E"
    assert U.wind_direction(180) == "S"
    assert U.wind_direction(270) == "W"
    assert U.wind_direction(337.5) in ("NNW", "N")
    assert U.wind_direction(None) == "—"


def test_aqi_categories():
    assert U.aqi_category(20) == "Good"
    assert U.aqi_category(75) == "Moderate"
    assert U.aqi_category(125) == "Sensitive"
    assert U.aqi_category(250) == "Very Unhealthy"
    assert U.aqi_category(400) == "Hazardous"
    assert U.aqi_category(None) == "Unavailable"
