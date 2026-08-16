"""Main application window: header, sidebar, stacked pages and orchestration.

Responsibilities:
* owning the background worker pool so the GUI never blocks on the network;
* wiring the dashboard, favorites, settings and about pages together;
* auto-refresh timer and unit / theme propagation;
* status bar messages, offline banner hand-off and alert notifications.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_NAME, APP_SUBTITLE, VERSION
from app.models.weather_models import Location, WeatherData
from app.services.alert_engine import AlertEngine
from app.services.favorites_service import FavoritesService
from app.services.history_service import HistoryService
from app.services.intelligence_engine import IntelligenceEngine
from app.services.settings_manager import SettingsManager
from app.services.weather_service import WeatherService
from app.ui.dashboard import DashboardWidget
from app.ui.pages import AboutPage, FavoritesPage, SettingsPage
from app.ui.theme import theme
from app.ui.widgets import LocationPickerDialog, make_label
from app.ui.workers import Worker

logger = logging.getLogger("weathervision.main")


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: SettingsManager,
        service: WeatherService,
        favorites: FavoritesService,
        history: HistoryService,
        intelligence: IntelligenceEngine,
        alerts: AlertEngine,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._service = service
        self._favorites = favorites
        self._history = history
        self._intelligence = intelligence
        self._alerts = alerts

        self._last_location: Location | None = None
        self._last_weather: WeatherData | None = None
        self._last_alert_signature: tuple | None = None
        self._fetching = False
        self._pool = QThreadPool.globalInstance()
        self._workers: set[Worker] = set()

        self.setWindowTitle(f"{APP_NAME} — Real-Time Weather Intelligence")
        self.setMinimumSize(1080, 720)
        self.resize(1300, 820)

        self._build_ui()
        self._apply_theme(self._settings.get("theme", "dark"), save=False)
        self._sync_demo_badge()
        self._restart_auto_refresh_timer()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("Central")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Sidebar ----------------------------------------------------
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(14, 18, 14, 18)
        side_layout.setSpacing(6)

        brand = QLabel("🌤️")
        brand.setStyleSheet("font-size: 30px;")
        brand.setToolTip(APP_NAME)
        side_layout.addWidget(brand)
        side_layout.addWidget(make_label(APP_NAME, "AppTitle"))
        side_layout.addWidget(make_label(APP_SUBTITLE, "AppSubtitle"))
        side_layout.addSpacing(18)

        self._nav_buttons: dict[str, QPushButton] = {}
        for key, icon, label in (
            ("dashboard", "🏠", "Dashboard"),
            ("favorites", "⭐", "Favorites"),
            ("settings", "⚙️", "Settings"),
            ("about", "ℹ️", "About"),
        ):
            btn = QPushButton(f"{icon}  {label}")
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._navigate(k))
            side_layout.addWidget(btn)
            self._nav_buttons[key] = btn
        side_layout.addStretch(1)

        version_label = make_label(f"v{VERSION}", "Soft")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side_layout.addWidget(version_label)

        # --- Right column ---------------------------------------------------
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 10, 18, 10)
        header_layout.setSpacing(8)

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search city, region or coordinates…")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.setMinimumWidth(280)
        self.search_field.returnPressed.connect(self._on_search)
        self.search_field.setToolTip(
            "Search by city / country (e.g. 'Lahore', 'Paris, France') or coordinates (e.g. 33.6, 73.0)"
        )
        header_layout.addWidget(self.search_field, 1)

        search_btn = QPushButton("🔍")
        search_btn.setObjectName("PrimaryButton")
        search_btn.setToolTip("Search")
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.clicked.connect(self._on_search)
        header_layout.addWidget(search_btn)

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setObjectName("IconButton")
        self.refresh_btn.setToolTip("Refresh current location")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._on_refresh)
        header_layout.addWidget(self.refresh_btn)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("IconButton")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self._on_toggle_theme)
        header_layout.addWidget(self.theme_btn)

        self.demo_badge = make_label("DEMO DATA", "DemoBadge")
        self.demo_badge.setVisible(False)
        header_layout.addWidget(self.demo_badge)

        right_layout.addWidget(header)

        # Stacked pages
        self.stack = QStackedWidget()
        self.dashboard = DashboardWidget(
            self._intelligence, self._alerts, self._favorites, self._settings
        )
        self.dashboard.refresh_requested.connect(self._on_refresh)
        self.dashboard.favorite_toggled.connect(self._on_favorite_toggled)

        self.favorites_page = FavoritesPage()
        self.favorites_page.location_selected.connect(self._fetch_location)
        self.favorites_page.location_removed.connect(self._on_favorite_removed)

        self.settings_page = SettingsPage(self._settings)
        self.settings_page.setting_changed.connect(self._on_setting_changed)
        self.settings_page.clear_cache_requested.connect(self._on_clear_cache)
        self.settings_page.clear_history_requested.connect(self._on_clear_history)
        self.settings_page.reset_requested.connect(self._on_reset_settings)

        self.about_page = AboutPage()

        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.favorites_page)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.about_page)
        right_layout.addWidget(self.stack, 1)

        root.addWidget(sidebar)
        root.addWidget(right, 1)
        self.setCentralWidget(central)

        status = QStatusBar()
        status.showMessage("Ready — search for a location to begin.")
        self.setStatusBar(status)

        self._navigate("dashboard")

    # ------------------------------------------------------------------
    # Navigation / theme
    # ------------------------------------------------------------------
    def _navigate(self, key: str) -> None:
        order = {"dashboard": 0, "favorites": 1, "settings": 2, "about": 3}
        if key in order:
            self.stack.setCurrentIndex(order[key])
        for name, btn in self._nav_buttons.items():
            btn.setChecked(name == key)
        if key == "favorites":
            self._refresh_favorites_page()
        self._set_theme_button_text()

    def _set_theme_button_text(self) -> None:
        if theme.current == "dark":
            self.theme_btn.setText("☀️")
            self.theme_btn.setToolTip("Switch to light mode")
        else:
            self.theme_btn.setText("🌙")
            self.theme_btn.setToolTip("Switch to dark mode")

    def _apply_theme(self, name: str, save: bool = True) -> None:
        theme.set_theme(name, self._app())
        self._set_theme_button_text()
        self.dashboard.re_render()
        if save:
            self._settings.set("theme", name)

    def _app(self):
        from PySide6.QtWidgets import QApplication
        return QApplication.instance()

    def _on_toggle_theme(self) -> None:
        new_name = "light" if theme.current == "dark" else "dark"
        self._apply_theme(new_name)
        self.statusBar().showMessage(f"Theme switched to {new_name} mode", 3000)

    def _sync_demo_badge(self) -> None:
        self.demo_badge.setVisible(self._service.is_demo_mode())
        self.demo_badge.setText("DEMO DATA — NOT REAL-TIME")

    # ------------------------------------------------------------------
    # Search / refresh flow
    # ------------------------------------------------------------------
    def _start_worker(self, worker: Worker) -> None:
        """Launch a worker, keeping a strong Python reference until it ends.

        QRunnable ownership is otherwise handed to C++ only; holding the wrapper
        prevents its Python-owned signal objects from being garbage-collected
        while the task is still queued or running (e.g. on window close).
        """
        self._workers.add(worker)
        worker.signals.finished.connect(
            lambda _result, _w=worker: self._workers.discard(_w)
        )
        worker.signals.error.connect(
            lambda _msg, _w=worker: self._workers.discard(_w)
        )
        self._pool.start(worker)

    def _on_search(self) -> None:
        text = self.search_field.text().strip()
        if not text:
            self.statusBar().showMessage("Type a city name or coordinates first.", 3000)
            return
        self.dashboard.show_loading("Searching for location…")
        worker = Worker(self._service.search, text)
        worker.signals.finished.connect(self._on_search_results)
        worker.signals.error.connect(
            lambda msg: self._on_any_error("Unable to fetch weather", msg)
        )
        self._start_worker(worker)

    def _on_search_results(self, locations: list[Location]) -> None:
        if not locations:
            self._on_any_error("Unable to fetch weather", "No matching locations.")
            return
        if len(locations) == 1:
            self._fetch_location(locations[0])
            return
        dialog = LocationPickerDialog(locations, self)
        if dialog.exec() and dialog.selected_location():
            self._fetch_location(dialog.selected_location())
        else:
            self.dashboard.show_empty()

    def _on_refresh(self) -> None:
        if self._last_location is None:
            self.statusBar().showMessage("Search for a location first.", 3000)
            self.dashboard.show_empty()
            return
        self._fetch_location(self._last_location)

    def _fetch_location(self, location: Location) -> None:
        if self._fetching:
            return
        self._fetching = True
        self._set_refresh_busy(True)
        self.dashboard.show_loading(
            f"Fetching weather for {location.short_name}…"
        )
        logger.info("Fetching weather for %s", location.display_name)
        worker = Worker(
            lambda loc=location: (loc, self._service.fetch_location(loc))
        )
        worker.signals.finished.connect(self._on_fetch_done)
        worker.signals.error.connect(
            lambda msg: self._on_any_error("Unable to fetch weather", msg)
        )
        self._start_worker(worker)

    def _set_refresh_busy(self, busy: bool) -> None:
        self.refresh_btn.setEnabled(not busy)
        self.refresh_btn.setText("…" if busy else "↻")

    def _on_fetch_done(self, payload: tuple[Location, WeatherData]) -> None:
        location, weather = payload
        self._fetching = False
        self._set_refresh_busy(False)

        self._last_location = location
        self._last_weather = weather
        self._settings.set("last_location", location.to_dict())
        self.setWindowTitle(f"{APP_NAME} — {location.short_name}")

        self.dashboard.render_weather(weather)
        self._refresh_favorites_page()

        source_text = {
            "live": "Live",
            "cache": "Cached (offline)",
            "demo": "Demo data",
        }.get(weather.source, weather.source)
        self.statusBar().showMessage(
            f"{source_text} weather for {location.display_name} — loaded successfully."
        )
        self._maybe_notify(weather)

    def _on_any_error(self, title: str, message: str) -> None:
        self._fetching = False
        self._set_refresh_busy(False)
        self.dashboard.stop_loading()
        if self._last_weather is not None:
            # keep showing the last successful view; just inform the user.
            self.statusBar().showMessage(message, 5000)
        else:
            self.dashboard.show_error(title, message)

    # ------------------------------------------------------------------
    # Favorites
    # ------------------------------------------------------------------
    def _on_favorite_toggled(self, location: Location) -> None:
        if location is None:
            return
        if self._favorites.contains(location):
            self._favorites.remove(location)
            self.statusBar().showMessage(
                f"Removed {location.short_name} from favorites.", 3000
            )
        else:
            self._favorites.add(location)
            self.statusBar().showMessage(
                f"Saved {location.short_name} to favorites.", 3000
            )
        self.dashboard.set_favorite_state(self._favorites.contains(location))
        self._refresh_favorites_page()

    def _on_favorite_removed(self, location: Location) -> None:
        self._favorites.remove(location)
        self.statusBar().showMessage(
            f"Removed {location.short_name} from favorites.", 3000
        )
        self._refresh_favorites_page()
        if (
            self._last_location is not None
            and self._last_location.cache_key() == location.cache_key()
        ):
            self.dashboard.set_favorite_state(False)

    def _refresh_favorites_page(self) -> None:
        self.favorites_page.refresh(self._favorites.list())

    # ------------------------------------------------------------------
    # Settings wiring
    # ------------------------------------------------------------------
    def _on_setting_changed(self, key: str, value: Any) -> None:
        if key == "theme":
            self._apply_theme(value)
        elif key in ("temp_unit", "wind_unit", "pressure_unit"):
            self._settings.set(key, value)
            self.dashboard.re_render()
        elif key in ("auto_refresh", "refresh_interval_min"):
            self._settings.set(key, value)
            self._restart_auto_refresh_timer()
        elif key == "demo_mode":
            self._settings.set(key, value)
            self._sync_demo_badge()
            self._restart_auto_refresh_timer()
            if self._last_location is not None:
                self._fetch_location(self._last_location)
            else:
                self.dashboard.show_empty()
                self.statusBar().showMessage(
                    "Demo mode is on — search a city to see mock data.", 5000
                )
        elif key in ("default_location", "notify_on_alerts"):
            self._settings.set(key, value)

    def _on_clear_cache(self) -> None:
        self._service.clear_cache()
        self.statusBar().showMessage("Offline cache cleared.", 3000)

    def _on_clear_history(self) -> None:
        self._history.clear()
        self.statusBar().showMessage("Search history cleared.", 3000)

    def _on_reset_settings(self) -> None:
        self._settings.reset()
        self.settings_page.reload()
        self._apply_theme(self._settings.get("theme", "dark"))
        self._sync_demo_badge()
        self._restart_auto_refresh_timer()
        self.statusBar().showMessage("Settings restored to defaults.", 3000)

    # ------------------------------------------------------------------
    # Auto refresh
    # ------------------------------------------------------------------
    def _restart_auto_refresh_timer(self) -> None:
        if not hasattr(self, "_timer"):
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._on_auto_refresh)
        self._timer.stop()
        if self._settings.get("auto_refresh") and not self._service.is_demo_mode():
            interval = int(self._settings.get("refresh_interval_min", 15)) * 60_000
            self._timer.start(interval)
            logger.info("Auto refresh every %d min", interval // 60_000)
        else:
            self._timer.stop()

    def _on_auto_refresh(self) -> None:
        if self._last_location is not None and not self._fetching:
            logger.info("Auto refresh triggered")
            self._fetch_location(self._last_location)

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    def _maybe_notify(self, weather: WeatherData) -> None:
        if not self._settings.get("notify_on_alerts"):
            return
        score = self._intelligence.comfort_score(weather).total
        alerts = self._alerts.evaluate(weather, score)
        important = [a for a in alerts if a.level in ("HIGH", "CRITICAL")]
        if not important:
            return
        signature = tuple((a.level, a.title) for a in important)
        if signature == self._last_alert_signature:
            return
        self._last_alert_signature = signature
        lines = "\n".join(f"{a.icon} {a.title}: {a.message}" for a in important)
        QMessageBox.warning(
            self,
            "Weather alert",
            f"Weather alerts for {weather.location.short_name}:\n\n{lines}",
        )

    def startup_load(self) -> None:
        """Load the last / default location after the window is shown."""
        if self._settings.get("demo_mode"):
            self.statusBar().showMessage(
                "Demo mode active — data is simulated, not real-time.", 5000
            )
        last = self._settings.get("last_location")
        if isinstance(last, dict):
            location = Location.from_dict(last)
            self.search_field.setText(location.short_name)
            self._fetch_location(location)
            return
        default_loc = self._settings.get("default_location")
        if isinstance(default_loc, str) and default_loc.strip():
            self.search_field.setText(default_loc.strip())
            self._on_search()
            return
        self.dashboard.show_empty()

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        logger.info("WeatherVision shutting down")
        self._timer.stop()
        super().closeEvent(event)
