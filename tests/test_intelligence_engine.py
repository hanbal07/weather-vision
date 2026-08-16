"""Tests for the Weather Intelligence Engine (scores, activities, insights)."""
from app.services.intelligence_engine import IntelligenceEngine

from tests.helpers import make_weather

engine = IntelligenceEngine()


def test_comfort_score_perfect_weather_is_high():
    result = engine.comfort_score(make_weather(temp=22, humidity=50, wind=10,
                                               rain_prob=0, visibility_m=20000, uv=2))
    assert result.total >= 85
    assert result.grade in ("Excellent", "Good")


def test_comfort_score_extreme_weather_is_low():
    result = engine.comfort_score(make_weather(temp=42, humidity=92, wind=80,
                                               rain_prob=95, visibility_m=500, uv=11))
    assert result.total <= 20
    assert result.grade == "Very Poor"


def test_score_is_bounded_0_100():
    for kwargs in (dict(temp=-20), dict(temp=60), dict(rain_prob=100)):
        result = engine.comfort_score(make_weather(**kwargs))
        assert 0 <= result.total <= 100


def test_score_components_explainable():
    result = engine.comfort_score(make_weather(temp=35, humidity=80))
    labels = {c.label for c in result.components}
    assert labels == {"Temperature", "Humidity", "Wind", "Rain probability",
                      "Visibility", "UV index"}
    assert all(c.note for c in result.components)


def test_why_returns_reasoning_lines():
    weather = make_weather(temp=34, humidity=72, rain_prob=65)
    lines = engine.why(weather)
    assert len(lines) >= 3
    assert any("Comfort Score" in line for line in lines)
    assert any("Temperature" in line for line in lines)


def test_activity_scores_within_bounds_and_sorted():
    weather = make_weather(temp=20, humidity=50, wind=10, rain_prob=0)
    results = engine.activity_scores(weather)
    assert len(results) == 8
    scores = [r.score for r in results]
    assert all(0 <= s <= 100 for s in scores)
    assert scores == sorted(scores, reverse=True)
    assert all(r.reasons for r in results)


def test_activity_picnic_penalized_in_rain():
    sunny = next(r for r in engine.activity_scores(make_weather(temp=24, rain_prob=5))
                 if r.name == "Picnic")
    rainy = next(r for r in engine.activity_scores(make_weather(temp=24, rain_prob=95))
                 if r.name == "Picnic")
    assert rainy.score < sunny.score


def test_insights_generate_rain_alert():
    weather = make_weather(rain_prob=85, code=61, precipitation=3.0)
    titles = [i.title for i in engine.insights(weather)]
    assert any("Rain" in t for t in titles)


def test_insights_include_clothing_advice():
    weather = make_weather(temp=12)
    titles = [i.title for i in engine.insights(weather)]
    assert "Clothing" in titles


def test_insights_thunderstorm_critical():
    weather = make_weather(code=95)
    levels = [i.level for i in engine.insights(weather)]
    assert "CRITICAL" in levels
