"""Tests for model parsing (defensive handling of API payloads) and the service."""
import pytest

from app.api.errors import InvalidResponseError, NetworkError
from app.api.geocoding import Geocoder
from app.api.weather_api import WeatherAPI
from app.models.weather_models import WeatherData
from app.services.cache_service import WeatherCache
from app.services.history_service import HistoryService
from app.services.settings_manager import SettingsManager
from app.services.weather_service import WeatherService

from tests.helpers import make_location, sample_air_quality_payload, sample_forecast_payload


# ---------------------------------------------------------------------------
# Model parsing
# ---------------------------------------------------------------------------
def test_parse_valid_payload():
    location = make_location()
    weather = WeatherData.from_api_json(
        sample_forecast_payload(), location, sample_air_quality_payload()
    )
    assert weather.current.temperature == 30.2
    assert weather.current.humidity == 61
    assert weather.current.pressure == 1011.2
    assert weather.current.uv_index == 6.5
    assert weather.current.visibility_m == 12000.0
    assert weather.air_quality is not None and weather.air_quality.aqi == 78.0
    assert len(weather.hourly) == 24
    assert len(weather.daily) == 7
    assert weather.location.display_name == "Lahore, Pakistan"


def test_parse_missing_current_raises():
    with pytest.raises(InvalidResponseError):
        WeatherData.from_api_json({}, make_location())


def test_parse_missing_optional_fields_does_not_crash():
    payload = sample_forecast_payload()
    del payload["current"]["visibility"]
    del payload["current"]["uv_index"]
    weather = WeatherData.from_api_json(payload, make_location())
    assert weather.current.uv_index is None
    assert weather.current.visibility_m == 10000.0  # safe default


def test_parse_air_quality_missing_returns_none():
    weather = WeatherData.from_api_json(sample_forecast_payload(), make_location())
    assert weather.air_quality is None


# ---------------------------------------------------------------------------
# Geocoding helpers
# ---------------------------------------------------------------------------
def test_detect_coordinates():
    geocoder = Geocoder(WeatherAPI())
    assert geocoder.detect_coordinates("33.6, 73.1") == (33.6, 73.1)
    assert geocoder.detect_coordinates("-12.5; 45.2") == (-12.5, 45.2)
    assert geocoder.detect_coordinates("Lahore") is None
    assert geocoder.detect_coordinates("95, 200") is None  # out of range


# ---------------------------------------------------------------------------
# Weather service (mock API, no network)
# ---------------------------------------------------------------------------
class FakeAPI:
    def get_forecast(self, lat, lon, timezone="auto"):
        return sample_forecast_payload()

    def get_air_quality(self, lat, lon):
        return sample_air_quality_payload()

    def search_cities(self, query, limit=8):
        return [{
            "name": query.title(), "country": "Fakeland", "latitude": 10.0,
            "longitude": 20.0, "timezone": "UTC", "country_code": "FK",
        }]


class FailingAPI:
    """Geocoding works, but the forecast endpoint is down (offline scenario)."""

    def get_forecast(self, lat, lon, timezone="auto"):
        raise NetworkError("no connection")

    def get_air_quality(self, lat, lon):
        return None

    def search_cities(self, query, limit=8):
        return [{
            "name": query.title(), "country": "Fakeland", "latitude": 10.0,
            "longitude": 20.0, "timezone": "UTC", "country_code": "FK",
        }]


@pytest.fixture
def service(tmp_path):
    from app.database.database import DatabaseManager
    db = DatabaseManager(tmp_path / "test.db")
    settings = SettingsManager(tmp_path / "settings.json")
    cache = WeatherCache(db)
    history = HistoryService(db)
    yield WeatherService(
        api=FakeAPI(),
        geocoder=Geocoder(FakeAPI()),
        cache=cache,
        history=history,
        settings=settings,
    )
    db.close()


def test_service_fetch_for_query(service):
    location, weather = service.fetch_for_query("lahore")
    assert weather.source == "live"
    assert location.name == "Lahore"
    assert len(service._history.list()) == 1


def test_service_demo_mode(tmp_path):
    from app.database.database import DatabaseManager
    db = DatabaseManager(tmp_path / "demo.db")
    settings = SettingsManager(tmp_path / "settings.json")
    settings.set("demo_mode", True)
    svc = WeatherService(
        api=FakeAPI(),
        geocoder=Geocoder(FakeAPI()),
        cache=WeatherCache(db),
        history=HistoryService(db),
        settings=settings,
    )
    location, weather = svc.fetch_for_query("lahore")
    assert weather.source == "demo"
    assert 0 < weather.current.temperature < 60
    db.close()


def test_service_falls_back_to_cache_on_failure(tmp_path):
    from app.database.database import DatabaseManager
    db = DatabaseManager(tmp_path / "cache.db")
    settings = SettingsManager(tmp_path / "settings.json")
    cache = WeatherCache(db)
    history = HistoryService(db)

    # First: live fetch succeeds and populates the cache.
    live = WeatherService(
        api=FakeAPI(), geocoder=Geocoder(FakeAPI()), cache=cache,
        history=history, settings=settings,
    )
    _, weather = live.fetch_for_query("lahore")
    assert weather.source == "live"

    # Now: API is down -> cache must be served with source="cache".
    offline = WeatherService(
        api=FailingAPI(), geocoder=Geocoder(FailingAPI()), cache=cache,
        history=history, settings=settings,
    )
    _, cached = offline.fetch_for_query("lahore")
    assert cached.source == "cache"
    db.close()


def test_cache_roundtrip_with_json(tmp_path):
    from app.database.database import DatabaseManager
    db = DatabaseManager(tmp_path / "roundtrip.db")
    cache = WeatherCache(db)
    location = make_location()
    weather = WeatherData.from_api_json(
        sample_forecast_payload(), location, sample_air_quality_payload()
    )
    cache.save(location, weather)
    cached = cache.get(location)
    assert cached is not None
    assert cached.weather.current.temperature == 30.2
    assert cached.age_minutes < 1
    db.close()


def test_cache_returns_none_when_missing(tmp_path):
    from app.database.database import DatabaseManager
    db = DatabaseManager(tmp_path / "missing.db")
    cache = WeatherCache(db)
    assert cache.get(make_location()) is None
    db.close()
