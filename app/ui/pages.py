"""Sidebar pages: Favorites, Settings and About."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_NAME, APP_SUBTITLE, VERSION
from app.models.weather_models import Location
from app.services.settings_manager import SettingsManager
from app.ui.widgets import Card, SectionTitle, make_label


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------
class FavoritesPage(QWidget):
    location_selected = Signal(object)  # Location
    location_removed = Signal(object)   # Location

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(make_label("⭐ Favorites", "PageTitle"))
        layout.addWidget(
            make_label("Saved locations - click Load to view its weather.", "Muted")
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._body = QWidget()
        self._list_layout = QVBoxLayout(self._body)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(10)
        self._list_layout.addStretch(1)
        scroll.setWidget(self._body)
        layout.addWidget(scroll, 1)

        self._empty_label = make_label(
            "No favorites yet.\nOpen the Dashboard, search a city and tap ☆ to save it.",
            "Muted",
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_layout.insertWidget(0, self._empty_label)

    def refresh(self, locations: list[Location]) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._empty_label.setVisible(not locations)
        self._empty_label = make_label(
            "No favorites yet.\nOpen the Dashboard, search a city and tap ☆ to save it.",
            "Muted",
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_layout.addWidget(self._empty_label)
        self._empty_label.setVisible(not locations)

        for loc in locations:
            card = Card(hoverable=True)
            row = QHBoxLayout(card)
            row.setContentsMargins(14, 10, 10, 10)
            row.setSpacing(12)
            row.addWidget(make_label("📍", "", loc.display_name))
            info = QVBoxLayout()
            info.setSpacing(0)
            info.addWidget(make_label(loc.display_name, "InsightTitle"))
            info.addWidget(make_label(
                f"{loc.latitude:.3f}, {loc.longitude:.3f} · {loc.tz_name}", "StatLabel"
            ))
            row.addLayout(info, 1)

            load_btn = QPushButton("Load")
            load_btn.setObjectName("PrimaryButton")
            load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            load_btn.clicked.connect(
                lambda _=False, loc=loc: self.location_selected.emit(loc)
            )
            row.addWidget(load_btn)

            remove_btn = QPushButton("Remove")
            remove_btn.setObjectName("DangerButton")
            remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            remove_btn.clicked.connect(
                lambda _=False, loc=loc: self.location_removed.emit(loc)
            )
            row.addWidget(remove_btn)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)

        self._list_layout.addStretch(1)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
class SettingsPage(QWidget):
    setting_changed = Signal(str, object)      # key, value
    clear_cache_requested = Signal()
    clear_history_requested = Signal()
    reset_requested = Signal()

    def __init__(self, settings: SettingsManager) -> None:
        super().__init__()
        self._settings = settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(make_label("⚙️ Settings", "PageTitle"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 8, 0)
        body_layout.setSpacing(12)

        # --- Units --------------------------------------------------------
        units_card = Card()
        u = QVBoxLayout(units_card)
        u.setContentsMargins(16, 14, 16, 16)
        u.addWidget(SectionTitle("Units", "Applied to the entire interface"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)

        self.temp_combo = self._combo(
            [("Celsius (°C)", "C"), ("Fahrenheit (°F)", "F")],
            settings.get("temp_unit", "C"),
        )
        self.wind_combo = self._combo(
            [("Kilometres per hour", "kmh"), ("Miles per hour", "mph")],
            settings.get("wind_unit", "kmh"),
        )
        self.pressure_combo = self._combo(
            [("Hectopascal (hPa)", "hpa"), ("Inches of mercury (inHg)", "inHg")],
            settings.get("pressure_unit", "hpa"),
        )

        grid.addWidget(make_label("Temperature", "CardTitle"), 0, 0)
        grid.addWidget(self.temp_combo, 0, 1)
        grid.addWidget(make_label("Wind speed", "CardTitle"), 1, 0)
        grid.addWidget(self.wind_combo, 1, 1)
        grid.addWidget(make_label("Pressure", "CardTitle"), 2, 0)
        grid.addWidget(self.pressure_combo, 2, 1)
        grid.setColumnStretch(1, 1)
        u.addLayout(grid)

        self.temp_combo.currentIndexChanged.connect(
            lambda _: self._emit("temp_unit", self.temp_combo.currentData())
        )
        self.wind_combo.currentIndexChanged.connect(
            lambda _: self._emit("wind_unit", self.wind_combo.currentData())
        )
        self.pressure_combo.currentIndexChanged.connect(
            lambda _: self._emit("pressure_unit", self.pressure_combo.currentData())
        )

        body_layout.addWidget(units_card)

        # --- Appearance -----------------------------------------------------
        appear_card = Card()
        a = QVBoxLayout(appear_card)
        a.setContentsMargins(16, 14, 16, 16)
        a.addWidget(SectionTitle("Appearance", "Dark and light are designed independently"))
        row = QHBoxLayout()
        row.addWidget(make_label("Theme", "CardTitle"))
        self.theme_combo = self._combo(
            [("Dark mode", "dark"), ("Light mode", "light")],
            settings.get("theme", "dark"),
        )
        self.theme_combo.setMinimumWidth(220)
        row.addWidget(self.theme_combo, 1)
        a.addLayout(row)
        self.theme_combo.currentIndexChanged.connect(
            lambda _: self._emit("theme", self.theme_combo.currentData())
        )
        body_layout.addWidget(appear_card)

        # --- Data & refresh ---------------------------------------------------
        data_card = Card()
        d = QVBoxLayout(data_card)
        d.setContentsMargins(16, 14, 16, 16)
        d.addWidget(SectionTitle("Data & refresh", "Keep requests within API limits"))
        d.addSpacing(4)

        self.auto_refresh_box = QCheckBox("Automatically refresh the current location")
        self.auto_refresh_box.setChecked(bool(settings.get("auto_refresh")))
        self.auto_refresh_box.toggled.connect(
            lambda checked: self._emit("auto_refresh", checked)
        )
        d.addWidget(self.auto_refresh_box)

        interval_row = QHBoxLayout()
        interval_row.addWidget(make_label("Refresh interval (minutes)", "Muted"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(5, 120)
        self.interval_spin.setValue(int(settings.get("refresh_interval_min", 15)))
        self.interval_spin.setSuffix(" min")
        self.interval_spin.setEnabled(bool(settings.get("auto_refresh")))
        self.interval_spin.valueChanged.connect(
            lambda v: self._emit("refresh_interval_min", v)
        )
        self.auto_refresh_box.toggled.connect(self.interval_spin.setEnabled)
        interval_row.addWidget(self.interval_spin, 1)
        d.addLayout(interval_row)

        demo_row = QHBoxLayout()
        self.demo_box = QCheckBox("Demo mode (realistic mock data, no internet)")
        self.demo_box.setChecked(bool(settings.get("demo_mode")))
        self.demo_box.toggled.connect(lambda checked: self._emit("demo_mode", checked))
        demo_row.addWidget(self.demo_box)
        demo_row.addStretch(1)
        d.addLayout(demo_row)

        notify_row = QHBoxLayout()
        self.notify_box = QCheckBox("Show alert popups for HIGH / CRITICAL warnings")
        self.notify_box.setChecked(bool(settings.get("notify_on_alerts")))
        self.notify_box.toggled.connect(
            lambda checked: self._emit("notify_on_alerts", checked)
        )
        notify_row.addWidget(self.notify_box)
        notify_row.addStretch(1)
        d.addLayout(notify_row)

        default_row = QHBoxLayout()
        default_row.addWidget(make_label("Default location (optional)", "CardTitle"))
        self.default_edit = QLineEdit()
        self.default_edit.setPlaceholderText("e.g. Lahore")
        current = settings.get("default_location")
        if isinstance(current, str):
            self.default_edit.setText(current)
        self.default_edit.editingFinished.connect(self._save_default_location)
        default_row.addWidget(self.default_edit, 1)
        d.addLayout(default_row)

        body_layout.addWidget(data_card)

        # --- Maintenance --------------------------------------------------------
        maint_card = Card()
        m = QVBoxLayout(maint_card)
        m.setContentsMargins(16, 14, 16, 16)
        m.addWidget(SectionTitle("Maintenance", "Local data controls"))
        actions = QHBoxLayout()
        clear_cache_btn = QPushButton("Clear cache")
        clear_cache_btn.setObjectName("GhostButton")
        clear_cache_btn.clicked.connect(self.clear_cache_requested.emit)
        clear_history_btn = QPushButton("Clear search history")
        clear_history_btn.setObjectName("GhostButton")
        clear_history_btn.clicked.connect(self.clear_history_requested.emit)
        reset_btn = QPushButton("Reset all settings")
        reset_btn.setObjectName("DangerButton")
        reset_btn.clicked.connect(self._confirm_reset)
        actions.addWidget(clear_cache_btn)
        actions.addWidget(clear_history_btn)
        actions.addWidget(reset_btn)
        actions.addStretch(1)
        m.addLayout(actions)
        body_layout.addWidget(maint_card)

        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

    # ------------------------------------------------------------------
    def _combo(self, items: list[tuple[str, str]], current: str) -> QComboBox:
        combo = QComboBox()
        for label, value in items:
            combo.addItem(label, value)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        return combo

    def _emit(self, key: str, value: object) -> None:
        self.setting_changed.emit(key, value)

    def _save_default_location(self) -> None:
        text = self.default_edit.text().strip()
        self._emit("default_location", text or None)

    def _confirm_reset(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        answer = QMessageBox.question(
            self,
            "Reset settings",
            "Reset all settings to defaults? Your favorites and history are kept.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.reset_requested.emit()

    def reload(self) -> None:
        """Re-sync controls after an external change (e.g. reset)."""
        self.temp_combo.setCurrentIndex(self.temp_combo.findData(self._settings.get("temp_unit")))
        self.wind_combo.setCurrentIndex(self.wind_combo.findData(self._settings.get("wind_unit")))
        self.pressure_combo.setCurrentIndex(
            self.pressure_combo.findData(self._settings.get("pressure_unit"))
        )
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self._settings.get("theme")))
        self.auto_refresh_box.setChecked(bool(self._settings.get("auto_refresh")))
        self.demo_box.setChecked(bool(self._settings.get("demo_mode")))
        self.notify_box.setChecked(bool(self._settings.get("notify_on_alerts")))


# ---------------------------------------------------------------------------
# About
# ---------------------------------------------------------------------------
class AboutPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        card = Card()
        c = QVBoxLayout(card)
        c.setContentsMargins(24, 22, 24, 22)
        c.setSpacing(8)

        logo = QLabel("🌤️")
        logo.setStyleSheet("font-size: 56px;")
        c.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        c.addWidget(make_label(APP_NAME, "PageTitle"), 0, Qt.AlignmentFlag.AlignHCenter)
        c.addWidget(
            make_label(APP_SUBTITLE, "Muted"), 0, Qt.AlignmentFlag.AlignHCenter
        )
        c.addSpacing(12)

        info = [
            ("Version", VERSION),
            ("Weather provider", "Open-Meteo (free, keyless)"),
            ("GUI framework", "PySide6 (Qt for Python)"),
            ("Charts", "Custom QPainter visualizations"),
            ("Storage", "SQLite (favorites, history, cache)"),
            ("Developer", "Your Name — University Project"),
        ]
        for label, value in info:
            row = QHBoxLayout()
            row.addWidget(make_label(label, "CardTitle"))
            row.addStretch(1)
            row.addWidget(make_label(value, "Muted"))
            c.addLayout(row)

        c.addSpacing(8)
        purpose = QLabel(
            "WeatherVision converts raw weather data into explainable intelligence: "
            "forecasts, a comfort score, alerts, activity suitability and insights "
            "that answer 'what does this weather mean for me?' and 'why?'."
        )
        purpose.setWordWrap(True)
        purpose.setObjectName("Muted")
        purpose.setAlignment(Qt.AlignmentFlag.AlignJustify)
        c.addWidget(purpose)
        c.addSpacing(8)
        c.addWidget(
            make_label("© 2026 WeatherVision Project. For academic use.", "Soft"),
            0, Qt.AlignmentFlag.AlignHCenter,
        )

        layout.addWidget(card)
        layout.addStretch(1)
