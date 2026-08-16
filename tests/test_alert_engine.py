"""Tests for the alert engine thresholds."""
from app.services.alert_engine import AlertEngine

from tests.helpers import make_weather

engine = AlertEngine()


def test_no_alerts_in_calm_weather():
    weather = make_weather(temp=22, humidity=50, wind=10, rain_prob=5, uv=2)
    alerts = engine.evaluate(weather, comfort_score=90)
    assert alerts == []


def test_heavy_rain_alert():
    weather = make_weather(code=65, precipitation=8.0)
    alerts = engine.evaluate(weather, comfort_score=40)
    titles = [a.title for a in alerts]
    assert "Heavy rain" in titles


def test_high_uv_alert():
    weather = make_weather(uv=9.5, is_day=True)
    alerts = engine.evaluate(weather, comfort_score=60)
    assert any("UV" in a.title for a in alerts)


def test_strong_wind_alert():
    weather = make_weather(wind=70)
    alerts = engine.evaluate(weather, comfort_score=50)
    assert any("wind" in a.title.lower() for a in alerts)


def test_extreme_heat_alert():
    weather = make_weather(temp=41)
    alerts = engine.evaluate(weather, comfort_score=20)
    assert any("heat" in a.title.lower() for a in alerts)


def test_thunderstorm_critical():
    weather = make_weather(code=95)
    alerts = engine.evaluate(weather, comfort_score=30)
    thunder = [a for a in alerts if a.title == "Thunderstorm"]
    assert thunder and thunder[0].level == "CRITICAL"


def test_poor_visibility_alert():
    weather = make_weather(visibility_m=1500)
    alerts = engine.evaluate(weather, comfort_score=50)
    assert any("visibility" in a.title.lower() for a in alerts)


def test_poor_comfort_alert():
    alerts = engine.evaluate(make_weather(temp=30, humidity=90, rain_prob=90), comfort_score=20)
    assert any("outdoor" in a.title.lower() for a in alerts)


def test_alerts_sorted_by_severity():
    weather = make_weather(code=95, uv=11, wind=70, temp=41)
    alerts = engine.evaluate(weather, comfort_score=10)
    order = {"INFO": 0, "LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}
    levels = [order[a.level] for a in alerts]
    assert levels == sorted(levels, reverse=True)
