"""Central application configuration, environment loading and logging setup.

All paths, API endpoints and tunable constants live here so that the rest of
the application never hard-codes values.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "weathervision.db"
SETTINGS_PATH = DATA_DIR / "settings.json"
LOG_PATH = LOG_DIR / "weathervision.log"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Environment (.env file, never committed)
# ---------------------------------------------------------------------------
load_dotenv(BASE_DIR / ".env")
WEATHER_API_KEY: str = os.getenv("WEATHER_API_KEY", "").strip()
ENV_THEME: str = os.getenv("APP_THEME", "dark").strip().lower()

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
APP_NAME = "WeatherVision"
APP_SUBTITLE = "Real-Time Weather Intelligence"
VERSION = "2.0.0"
ORGANIZATION = "WeatherVision Project"

# ---------------------------------------------------------------------------
# Weather API (Open-Meteo - free, no key required)
# ---------------------------------------------------------------------------
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

API_TIMEOUT = 15          # seconds
API_MAX_RETRIES = 2       # retries for transient HTTP 5xx responses
API_USER_AGENT = f"{APP_NAME}/{VERSION} (educational project)"

# ---------------------------------------------------------------------------
# Limits / defaults
# ---------------------------------------------------------------------------
CACHE_TTL_MINUTES = 30    # fresh period for live data
CACHE_MAX_AGE_MINUTES = 240  # stale cache is still shown, but clearly marked
HISTORY_LIMIT = 20
FORECAST_DAYS = 7
HOURLY_ENTRIES = 24

DEFAULT_SETTINGS: dict = {
    "temp_unit": "C",          # "C" or "F"
    "wind_unit": "kmh",        # "kmh" or "mph"
    "pressure_unit": "hpa",    # "hpa" or "inHg"
    "theme": "dark",           # "dark" or "light"
    "auto_refresh": False,
    "refresh_interval_min": 15,
    "demo_mode": False,
    "notify_on_alerts": True,
    "last_location": None,     # dict or None
    "default_location": None,  # str or None (free-text city)
}

LOGGER_NAME = "weathervision"


def setup_logging() -> logging.Logger:
    """Configure rotating file logging plus a console handler.

    Sensitive values (API keys) are never logged anywhere in the app.
    """
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_configured", False):
        return logger

    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger._configured = True  # type: ignore[attr-defined]
    return logger
