"""Application settings backed by a JSON file.

Persisted in ``data/settings.json``. Values are type-validated on load so a
hand-edited or corrupted file cannot crash the application.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import DEFAULT_SETTINGS

logger = logging.getLogger("weathervision.settings")

_ALLOWED_TEMP_UNITS = {"C", "F"}
_ALLOWED_WIND_UNITS = {"kmh", "mph"}
_ALLOWED_PRESSURE_UNITS = {"hpa", "inHg"}
_ALLOWED_THEMES = {"dark", "light"}


class SettingsManager:
    """Loads, validates and persists user preferences."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read settings file: %s", exc)
            return
        if isinstance(raw, dict):
            self._data.update(self._sanitize(raw))

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.error("Could not save settings: %s", exc)

    def _sanitize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Keep only known keys with valid values."""
        cleaned: dict[str, Any] = {}
        for key, default in DEFAULT_SETTINGS.items():
            if key not in raw:
                continue
            value = raw[key]
            if key == "temp_unit" and value in _ALLOWED_TEMP_UNITS:
                cleaned[key] = value
            elif key == "wind_unit" and value in _ALLOWED_WIND_UNITS:
                cleaned[key] = value
            elif key == "pressure_unit" and value in _ALLOWED_PRESSURE_UNITS:
                cleaned[key] = value
            elif key == "theme" and value in _ALLOWED_THEMES:
                cleaned[key] = value
            elif key == "auto_refresh" and isinstance(value, bool):
                cleaned[key] = value
            elif key == "demo_mode" and isinstance(value, bool):
                cleaned[key] = value
            elif key == "notify_on_alerts" and isinstance(value, bool):
                cleaned[key] = value
            elif key == "refresh_interval_min" and isinstance(value, (int, float)):
                cleaned[key] = max(5, min(int(value), 120))
            elif key in ("last_location", "default_location"):
                cleaned[key] = value if value is None or isinstance(value, (str, dict)) else None
        return cleaned

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULT_SETTINGS:
            return
        self._data[key] = value
        self._save()

    def update(self, mapping: dict[str, Any]) -> None:
        for key, value in mapping.items():
            if key in DEFAULT_SETTINGS:
                self._data[key] = value
        self._save()

    def reset(self) -> None:
        self._data = dict(DEFAULT_SETTINGS)
        self._save()

    @property
    def units(self) -> tuple[str, str, str]:
        return (
            self.get("temp_unit", "C"),
            self.get("wind_unit", "kmh"),
            self.get("pressure_unit", "hpa"),
        )
