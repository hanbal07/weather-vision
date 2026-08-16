"""WeatherVision — Real-Time Weather Intelligence System.

Entry point. Wires configuration, database, services and the GUI together,
then starts the Qt event loop. Run with::

    python main.py

To launch in Demo Mode (mock data, no internet) either enable it in
Settings inside the app, or set ``DEMO_MODE=1`` before starting::

    set DEMO_MODE=1
    python main.py
"""
from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from app.config import (
    APP_NAME,
    APP_SUBTITLE,
    DB_PATH,
    SETTINGS_PATH,
    VERSION,
    setup_logging,
)
from app.database.database import DatabaseManager
from app.services.alert_engine import AlertEngine
from app.services.cache_service import WeatherCache
from app.services.favorites_service import FavoritesService
from app.services.history_service import HistoryService
from app.services.intelligence_engine import IntelligenceEngine
from app.services.settings_manager import SettingsManager
from app.services.weather_service import WeatherService
from app.ui.theme import theme


def build_application() -> tuple[QApplication, object]:
    """Construct the Qt application, services and main window.

    Split out so an automated smoke test can import it without side effects.
    """
    logger = setup_logging()
    logger.info("Starting %s v%s (%s)", APP_NAME, VERSION, APP_SUBTITLE)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(f"{APP_NAME} — {APP_SUBTITLE}")
    app.setApplicationVersion(VERSION)

    if os.getenv("DEMO_MODE") == "1":
        os.environ.setdefault("WEATHERVISION_DEMO", "1")

    settings = SettingsManager(SETTINGS_PATH)
    if os.getenv("WEATHERVISION_DEMO") == "1" or os.getenv("DEMO_MODE") == "1":
        settings.set("demo_mode", True)

    db = DatabaseManager(DB_PATH)

    # API + services --------------------------------------------------------
    from app.api.geocoding import Geocoder
    from app.api.weather_api import WeatherAPI

    api = WeatherAPI()
    geocoder = Geocoder(api)
    cache = WeatherCache(db)
    favorites = FavoritesService(db)
    history = HistoryService(db)
    intelligence = IntelligenceEngine()
    alerts = AlertEngine()
    service = WeatherService(
        api=api,
        geocoder=geocoder,
        cache=cache,
        history=history,
        settings=settings,
    )

    # Theme ------------------------------------------------------------------
    theme.set_theme(settings.get("theme", "dark"), app)

    from app.ui.main_window import MainWindow

    window = MainWindow(
        settings=settings,
        service=service,
        favorites=favorites,
        history=history,
        intelligence=intelligence,
        alerts=alerts,
    )
    return app, window


def main() -> int:
    app, window = build_application()
    window.show()
    window.startup_load()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
