"""Tests for settings persistence and the favorites service."""
import pytest

from app.services.favorites_service import FavoritesService
from app.services.settings_manager import SettingsManager

from tests.helpers import make_location


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def test_settings_defaults(tmp_path):
    settings = SettingsManager(tmp_path / "settings.json")
    assert settings.get("temp_unit") == "C"
    assert settings.get("theme") == "dark"
    assert settings.get("auto_refresh") is False


def test_settings_set_and_reload(tmp_path):
    path = tmp_path / "settings.json"
    settings = SettingsManager(path)
    settings.set("temp_unit", "F")
    settings.set("refresh_interval_min", 30)

    reloaded = SettingsManager(path)
    assert reloaded.get("temp_unit") == "F"
    assert reloaded.get("refresh_interval_min") == 30


def test_settings_reject_invalid_values(tmp_path):
    path = tmp_path / "settings.json"
    settings = SettingsManager(path)
    settings.set("temp_unit", "X")  # not allowed
    settings.set("theme", "neon")

    reloaded = SettingsManager(path)
    assert reloaded.get("temp_unit") == "C"
    assert reloaded.get("theme") == "dark"


def test_settings_reset(tmp_path):
    settings = SettingsManager(tmp_path / "settings.json")
    settings.set("temp_unit", "F")
    settings.set("demo_mode", True)
    settings.reset()
    assert settings.get("temp_unit") == "C"
    assert settings.get("demo_mode") is False


def test_settings_units_property(tmp_path):
    settings = SettingsManager(tmp_path / "settings.json")
    settings.update({"temp_unit": "F", "wind_unit": "mph", "pressure_unit": "inHg"})
    assert settings.units == ("F", "mph", "inHg")


def test_settings_corrupt_file_uses_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ not valid json !!", encoding="utf-8")
    settings = SettingsManager(path)
    assert settings.get("temp_unit") == "C"


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------
@pytest.fixture
def favorites(tmp_path):
    from app.database.database import DatabaseManager

    db = DatabaseManager(tmp_path / "fav.db")
    yield FavoritesService(db)
    db.close()


def test_add_and_contains(favorites):
    loc = make_location()
    assert favorites.add(loc) is True
    assert favorites.contains(loc) is True


def test_add_duplicate_returns_false(favorites):
    loc = make_location()
    favorites.add(loc)
    assert favorites.add(loc) is False


def test_remove(favorites):
    loc = make_location()
    favorites.add(loc)
    assert favorites.remove(loc) is True
    assert favorites.contains(loc) is False
    assert favorites.remove(loc) is False


def test_list_returns_locations(favorites):
    favorites.add(make_location("Lahore", 31.55, 74.34))
    favorites.add(make_location("London", 51.5, -0.12))
    locs = favorites.list()
    assert len(locs) == 2
    names = {l.name for l in locs}
    assert names == {"Lahore", "London"}
