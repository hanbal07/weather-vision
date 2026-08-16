"""Tests for the Flask web layer.

These run fully offline: the app is created in Demo Mode and every location
is resolved through the coordinate path (which never touches the network), or
through a stubbed geocoder. No real API calls are made.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("DEMO_MODE", "1")


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


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def test_index_page_loads(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"WeatherVision" in res.data
    assert b"Search any place on Earth" in res.data


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "healthy"
    assert body["application"] == "WeatherVision"


def test_unknown_api_route_returns_json_404(client):
    res = client.get("/api/nope")
    assert res.status_code == 404
    assert "error" in res.get_json()


def test_unknown_page_returns_html_404(client):
    res = client.get("/definitely-not-a-page")
    assert res.status_code == 404
    assert b"Page not found" in res.data


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
def test_weather_demo_coordinates(client):
    res = client.get("/api/weather?q=31.55, 74.34")
    assert res.status_code == 200
    body = res.get_json()
    assert body["meta"]["source"] == "demo"
    assert body["meta"]["demo"] is True
    assert "temperature_display" in body["current"]
    assert "score" in body and "grade" in body["score"]
    assert "activities" in body and body["activities"]
    assert "insights" in body and body["insights"]
    assert len(body["hourly"]) > 0
    assert len(body["daily"]) > 0


def test_weather_requires_query(client):
    res = client.get("/api/weather")
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_weather_imperial_units(client):
    res = client.get("/api/weather?q=31.55, 74.34&units=imperial")
    assert res.status_code == 200
    body = res.get_json()
    assert body["units"]["temp"] == "F"
    assert body["current"]["temperature_display"].endswith("°F")


def test_weather_records_history(client):
    client.get("/api/weather?q=31.55, 74.34")
    res = client.get("/api/history")
    assert res.status_code == 200
    assert len(res.get_json()["history"]) >= 1


def test_search_route_uses_geocoder(client, monkeypatch):
    from app.models.weather_models import Location

    app_client = client.application
    service = app_client.extensions["service"]

    class FakeGeocoder:
        def search(self, query, limit=8):
            return [Location(
                name="Testville", country="Testland", country_code="TT",
                latitude=10.0, longitude=20.0, timezone="UTC",
            )]

    monkeypatch.setattr(service, "_geocoder", FakeGeocoder())
    res = client.get("/api/search?q=Testville")
    assert res.status_code == 200
    body = res.get_json()
    assert body["locations"][0]["name"] == "Testville"


def test_search_requires_query(client):
    res = client.get("/api/search")
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------
def test_favorites_roundtrip(client):
    payload = {
        "name": "Testville",
        "country": "Testland",
        "country_code": "TT",
        "latitude": 10.0,
        "longitude": 20.0,
        "timezone": "UTC",
    }
    res = client.post("/api/favorites", json=payload)
    assert res.status_code == 200
    assert res.get_json()["added"] is True

    res = client.get("/api/favorites")
    names = [f["name"] for f in res.get_json()["favorites"]]
    assert "Testville" in names

    res = client.delete("/api/favorites", json={"latitude": 10.0, "longitude": 20.0})
    assert res.status_code == 200
    assert res.get_json()["removed"] is True

    res = client.get("/api/favorites")
    names = [f["name"] for f in res.get_json()["favorites"]]
    assert "Testville" not in names


def test_favorites_requires_coordinates(client):
    res = client.post("/api/favorites", json={"name": "Bad"})
    assert res.status_code == 400
    res = client.delete("/api/favorites", json={})
    assert res.status_code == 400
