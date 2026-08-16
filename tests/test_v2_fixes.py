"""Regression tests for the v2 data-accuracy fixes.

Covers: (1) timezone-correct current-hour rain probability, (2) no fabricated
defaults for missing measurements, (3) score weight renormalization when
factors are unavailable, (4) the one-line summary / structured "why",
(5) dew point parsing, (6) None-safe alert engine, and (7) the new web payload
shape.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.weather_models import Location, WeatherData
from app.services.alert_engine import AlertEngine
from app.services.intelligence_engine import IntelligenceEngine

from tests.helpers import make_weather, sample_forecast_payload

engine = IntelligenceEngine()
alert_engine = AlertEngine()


# ---------------------------------------------------------------------------
# Timezone-correct current-hour rain probability
# ---------------------------------------------------------------------------
def _payload_with_utc_times(offset_seconds: int, probs: list[int]) -> dict:
    payload = sample_forecast_payload()
    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    payload["utc_offset_seconds"] = offset_seconds
    payload["hourly"]["time"] = [
        (base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(24)
    ]
    payload["hourly"]["precipitation_probability"] = list(probs) + [0] * (24 - len(probs))
    return payload


def test_current_rain_probability_uses_local_hour_offset():
    probs = [10, 20, 30, 40]
    location = Location(name="UTCville", latitude=0.0, longitude=0.0, timezone="UTC")

    # offset 0: local now == UTC now -> times[0] -> prob 10
    weather = WeatherData.from_api_json(_payload_with_utc_times(0, probs), location)
    assert weather.current.precipitation_probability == 10

    # offset +1h: local now == UTC now + 1h -> times[1] -> prob 20
    weather = WeatherData.from_api_json(_payload_with_utc_times(3600, probs), location)
    assert weather.current.precipitation_probability == 20


def test_current_rain_probability_none_when_hourly_missing():
    payload = sample_forecast_payload()
    payload["hourly"] = {}
    weather = WeatherData.from_api_json(payload, Location(timezone="UTC"))
    assert weather.current.precipitation_probability is None


# ---------------------------------------------------------------------------
# No fabricated defaults
# ---------------------------------------------------------------------------
def test_missing_optional_current_values_stay_none():
    payload = sample_forecast_payload()
    for key in (
        "pressure_msl", "visibility", "wind_speed_10m", "wind_gusts_10m",
        "cloud_cover", "apparent_temperature", "precipitation", "weather_code",
    ):
        del payload["current"][key]
    weather = WeatherData.from_api_json(payload, Location(timezone="UTC"))
    assert weather.current.pressure is None
    assert weather.current.visibility_m is None
    assert weather.current.wind_speed is None
    assert weather.current.wind_gusts is None
    assert weather.current.cloud_cover is None
    assert weather.current.feels_like is None
    assert weather.current.precipitation is None
    assert weather.current.condition_text == "Unknown"  # never "Clear sky"


def test_missing_hourly_values_stay_none():
    payload = sample_forecast_payload()
    del payload["hourly"]["precipitation_probability"]
    weather = WeatherData.from_api_json(payload, Location(timezone="UTC"))
    assert all(h.precipitation_probability is None for h in weather.hourly)
    assert len(weather.hourly) == 24


# ---------------------------------------------------------------------------
# Dew point
# ---------------------------------------------------------------------------
def test_dew_point_parsed_when_provided():
    payload = sample_forecast_payload()
    payload["current"]["dew_point_2m"] = 15.0
    weather = WeatherData.from_api_json(payload, Location(timezone="UTC"))
    assert weather.current.dew_point == 15.0


def test_dew_point_none_when_missing():
    weather = WeatherData.from_api_json(sample_forecast_payload(), Location(timezone="UTC"))
    assert weather.current.dew_point is None


# ---------------------------------------------------------------------------
# Score weight renormalization over available factors
# ---------------------------------------------------------------------------
def test_score_renormalizes_weights_when_factors_missing():
    result = engine.comfort_score(make_weather(uv=None, visibility_m=None))
    assert result.available_factors == 4
    assert result.factor_count == 6
    labels = {c.label for c in result.components}
    assert "UV index" not in labels and "Visibility" not in labels
    assert abs(sum(c.weight for c in result.components) - 1.0) < 0.005
    assert 0 <= result.total <= 100


def test_score_uses_all_six_factors_when_present():
    result = engine.comfort_score(make_weather())
    assert result.available_factors == 6
    assert abs(sum(c.weight for c in result.components) - 1.0) < 0.001


def test_activity_scores_skip_missing_factors():
    results = engine.activity_scores(make_weather(uv=None, visibility_m=None))
    assert len(results) == 8
    assert all(0 <= r.score <= 100 for r in results)
    assert all(r.reasons for r in results)


# ---------------------------------------------------------------------------
# Summary + structured "why"
# ---------------------------------------------------------------------------
def test_summary_builds_human_sentence():
    summary = engine.summary(make_weather(temp=22, rain_prob=5))
    assert "Clear sky" in summary and "22°" in summary


def test_summary_mentions_rain_when_likely():
    summary = engine.summary(make_weather(temp=22, rain_prob=70))
    assert "rain is likely (70%)" in summary


def test_why_structured_returns_title_body_pairs():
    lines = engine.why_structured(make_weather(temp=34, humidity=72))
    assert lines and all({"title", "body"} <= set(line) for line in lines)
    assert any("Bottom line" in line["title"] for line in lines)


# ---------------------------------------------------------------------------
# None-safe alert engine
# ---------------------------------------------------------------------------
def test_alerts_no_crash_and_no_fake_alerts_when_values_missing():
    weather = make_weather(visibility_m=None, wind=None, rain_prob=None, uv=None)
    assert alert_engine.evaluate(weather, comfort_score=90) == []


def test_alerts_extreme_heat_still_fires_with_other_values_missing():
    weather = make_weather(temp=41, visibility_m=None, wind=None)
    alerts = alert_engine.evaluate(weather, comfort_score=20)
    assert any("heat" in a.title.lower() for a in alerts)


# ---------------------------------------------------------------------------
# Web payload shape
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(tmp_path: Path):
    os.environ["DATABASE_PATH"] = str(tmp_path / "web.db")
    os.environ["SETTINGS_PATH"] = str(tmp_path / "settings.json")
    os.environ["DEMO_MODE"] = "1"

    from web_app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client
    app.extensions["db"].close()


def test_weather_payload_v2_shape(client):
    body = client.get("/api/weather?q=31.55, 74.34").get_json()
    assert body["summary"]
    assert body["why"] and all(
        {"title", "body"} <= set(item) for item in body["why"]
    )
    assert body["activity"]["verdict"]["text"]
    assert body["activity"]["items"]
    assert body["activities"]  # kept for backward compatibility
    assert body["score"]["available_factors"] == body["score"]["factor_count"]
    assert "dew_point_display" in body["current"]
    assert "wind_direction_deg" in body["current"]
    assert body["hourly"][0]["is_now"] is True
    assert body["current"]["feels_like_display"]
    assert body["alerts"] is not None


def test_weather_payload_units_switch_keeps_raw_numbers(client):
    metric = client.get("/api/weather?q=31.55, 74.34").get_json()
    imperial = client.get("/api/weather?q=31.55, 74.34&units=imperial").get_json()
    assert metric["units"]["temp"] == "C"
    assert imperial["units"]["temp"] == "F"
    # Raw metric values are preserved regardless of display units.
    assert metric["current"]["temperature"] == imperial["current"]["temperature"]
    assert imperial["current"]["temperature_display"].endswith("°F")
