"""The main dashboard: a scrollable, sectioned weather intelligence view.

Layout (top to bottom):
    offline banner (when serving cache)  ->  hero current-weather card
    statistics grid                       ->  weather intelligence (score + insights)
    hourly forecast (+ timeline replay)   ->  7-day forecast
    charts (tabs)                         ->  activity planner
    alerts
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.models.weather_models import WeatherData
from app.services.alert_engine import AlertEngine
from app.services.favorites_service import FavoritesService
from app.services.intelligence_engine import IntelligenceEngine
from app.services.settings_manager import SettingsManager
from app.ui.charts import PrecipitationChart, TemperatureChart, WindChart
from app.ui.widgets import (
    ActivityCard,
    AlertCard,
    Card,
    DailyCard,
    EmptyState,
    ErrorState,
    HourlyItem,
    InsightCard,
    LoadingView,
    OfflineBanner,
    ScoreGauge,
    SectionTitle,
    StatCard,
    WhyDialog,
    make_label,
)
from app.utils import units as U
from app.utils.helpers import (
    format_date,
    format_time,
    parse_iso_time,
    time_ago,
)

MINUTE = 60_000


class DashboardWidget(QWidget):
    """Renders weather data and emits user-intent signals to the main window."""

    refresh_requested = Signal()
    favorite_toggled = Signal(object)  # Location
    why_requested = Signal(object)     # WeatherData

    def __init__(
        self,
        intelligence: IntelligenceEngine,
        alerts: AlertEngine,
        favorites: FavoritesService,
        settings: SettingsManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._intelligence = intelligence
        self._alerts = alerts
        self._favorites = favorites
        self._settings = settings
        self._weather: WeatherData | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._banner = OfflineBanner()
        root.addWidget(self._banner)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self._empty_page = EmptyState()
        self._loading_page = LoadingView()
        self._error_page = ErrorState()
        self._error_page.retry_clicked.connect(self.refresh_requested.emit)
        self.stack.addWidget(self._empty_page)
        self.stack.addWidget(self._loading_page)
        self.stack.addWidget(self._error_page)
        self._content_page = self._build_content_page()
        self.stack.addWidget(self._content_page)

        self.stack.setCurrentWidget(self._empty_page)

        # Timeline replay state
        self._replay_index = 0
        self._replay_timer = QTimer(self)
        self._replay_timer.setInterval(900)
        self._replay_timer.timeout.connect(self._replay_step)

    # ------------------------------------------------------------------
    # Content construction
    # ------------------------------------------------------------------
    def _build_content_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(20, 18, 20, 24)
        layout.setSpacing(16)

        # --- Hero card -------------------------------------------------
        self._hero = Card()
        hero_lay = QHBoxLayout(self._hero)
        hero_lay.setContentsMargins(20, 18, 20, 18)
        hero_lay.setSpacing(14)

        left_col = QVBoxLayout()
        left_col.setSpacing(2)
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self.hero_location = make_label("", "HeroTitle")
        self.star_button = QPushButton("☆")
        self.star_button.setObjectName("StarButton")
        self.star_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.star_button.setToolTip("Save / remove from favorites")
        self.star_button.setFixedWidth(38)
        self.star_button.clicked.connect(lambda: self.favorite_toggled.emit(self._weather.location))
        top_row.addWidget(self.hero_location)
        top_row.addWidget(self.star_button)
        top_row.addStretch(1)
        left_col.addLayout(top_row)

        hero_mid = QHBoxLayout()
        hero_mid.setSpacing(18)
        self.hero_temp = make_label("--", "HeroTemp")
        hero_mid.addWidget(self.hero_temp)
        cond_col = QVBoxLayout()
        cond_col.setSpacing(0)
        self.hero_icon = make_label("", "")
        self.hero_icon.setStyleSheet("font-size: 42px;")
        self.hero_condition = make_label("", "HeroFeels")
        self.hero_feels = make_label("", "HeroFeels")
        cond_col.addWidget(self.hero_icon, 0, Qt.AlignmentFlag.AlignLeft)
        cond_col.addWidget(self.hero_condition)
        cond_col.addWidget(self.hero_feels)
        hero_mid.addLayout(cond_col)
        hero_mid.addStretch(1)
        left_col.addLayout(hero_mid)

        self.hero_updated = make_label("", "HeroInfo")
        self.hero_local_time = make_label("", "HeroInfo")
        left_col.addWidget(self.hero_updated)
        left_col.addWidget(self.hero_local_time)
        left_col.addStretch(1)
        hero_lay.addLayout(left_col, 1)

        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        self.hero_sunrise = make_label("", "HeroInfo")
        self.hero_sunset = make_label("", "HeroInfo")
        self.hero_clouds = make_label("", "HeroInfo")
        self.hero_humid = make_label("", "HeroInfo")
        right_col.addStretch(1)
        right_col.addWidget(self.hero_sunrise)
        right_col.addWidget(self.hero_sunset)
        right_col.addWidget(self.hero_clouds)
        right_col.addWidget(self.hero_humid)
        hero_lay.addLayout(right_col)

        self._hero.setObjectName("HeroCard")
        self._hero.setMinimumHeight(210)
        layout.addWidget(self._hero)

        # --- Stats grid -------------------------------------------------
        self._stat_cards: dict[str, StatCard] = {}
        stats_card = Card()
        stats_lay = QVBoxLayout(stats_card)
        stats_lay.setContentsMargins(16, 14, 16, 16)
        stats_lay.addWidget(SectionTitle("Current conditions",
                                          "Key measurements for this location"))
        grid = QGridLayout()
        grid.setSpacing(10)
        stats = [
            ("humidity", "💧", "Humidity"),
            ("wind", "🌬️", "Wind"),
            ("pressure", "📊", "Pressure"),
            ("visibility", "👁️", "Visibility"),
            ("uv", "☀️", "UV Index"),
            ("clouds", "☁️", "Cloud Cover"),
            ("air_quality", "🍃", "Air Quality"),
        ]
        for i, (key, icon, label) in enumerate(stats):
            card = StatCard(icon, label, "—", "")
            self._stat_cards[key] = card
            grid.addWidget(card, i // 4, i % 4)
        stats_lay.addLayout(grid)
        layout.addWidget(stats_card)

        # --- Intelligence section ----------------------------------------
        self._intel_card = Card()
        intel_lay = QHBoxLayout(self._intel_card)
        intel_lay.setContentsMargins(16, 14, 16, 16)
        intel_lay.setSpacing(20)

        gauge_col = QVBoxLayout()
        gauge_col.setSpacing(4)
        gauge_col.addWidget(SectionTitle("Weather Comfort Score",
                                         "0-100 from six weighted weather factors"))
        self._gauge = ScoreGauge()
        gauge_col.addWidget(self._gauge, 0, Qt.AlignmentFlag.AlignHCenter)
        self.score_label = make_label("", "Muted")
        gauge_col.addWidget(self.score_label, 0, Qt.AlignmentFlag.AlignHCenter)
        why_btn = QPushButton("Why this forecast?")
        why_btn.setObjectName("GhostButton")
        why_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        why_btn.setToolTip("Explain how this score was calculated")
        why_btn.clicked.connect(self._on_why_clicked)
        gauge_col.addWidget(why_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        gauge_col.addStretch(1)
        intel_lay.addLayout(gauge_col)

        insights_col = QVBoxLayout()
        insights_col.setSpacing(0)
        insights_col.addWidget(SectionTitle("Weather Intelligence",
                                            "Rule-based insights derived from live data"))
        self._insights_container = QWidget()
        self._insights_lay = QVBoxLayout(self._insights_container)
        self._insights_lay.setContentsMargins(0, 8, 0, 0)
        self._insights_lay.setSpacing(8)
        insights_col.addWidget(self._insights_container)
        intel_lay.addLayout(insights_col, 1)
        layout.addWidget(self._intel_card)

        # --- Hourly --------------------------------------------------------
        hourly_card = Card()
        hourly_lay = QVBoxLayout(hourly_card)
        hourly_lay.setContentsMargins(16, 14, 16, 16)
        head = QHBoxLayout()
        head.addWidget(SectionTitle("Hourly forecast",
                                    "Next 24 hours - the current hour is highlighted"))
        head.addStretch(1)
        self.replay_btn = QPushButton("▶ Timeline replay")
        self.replay_btn.setObjectName("GhostButton")
        self.replay_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.replay_btn.setToolTip("Animate how conditions change through the day")
        self.replay_btn.clicked.connect(self._toggle_replay)
        head.addWidget(self.replay_btn)
        hourly_lay.addLayout(head)

        self._hourly_scroll = QScrollArea()
        self._hourly_scroll.setWidgetResizable(True)
        self._hourly_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._hourly_scroll.setMaximumHeight(170)
        self._hourly_row = QWidget()
        self._hourly_row_lay = QHBoxLayout(self._hourly_row)
        self._hourly_row_lay.setContentsMargins(0, 0, 0, 0)
        self._hourly_row_lay.setSpacing(8)
        self._hourly_scroll.setWidget(self._hourly_row)
        hourly_lay.addWidget(self._hourly_scroll)
        self.replay_status = make_label("", "StatLabel")
        self.replay_status.setVisible(False)
        hourly_lay.addWidget(self.replay_status)
        layout.addWidget(hourly_card)

        # --- Daily -----------------------------------------------------------
        daily_card = Card()
        daily_lay = QVBoxLayout(daily_card)
        daily_lay.setContentsMargins(16, 14, 16, 16)
        daily_lay.addWidget(SectionTitle("7-day forecast",
                                         "Daily high / low and precipitation probability"))
        self._daily_scroll = QScrollArea()
        self._daily_scroll.setWidgetResizable(True)
        self._daily_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._daily_scroll.setMaximumHeight(230)
        self._daily_row = QWidget()
        self._daily_row_lay = QHBoxLayout(self._daily_row)
        self._daily_row_lay.setContentsMargins(0, 0, 0, 0)
        self._daily_row_lay.setSpacing(10)
        self._daily_scroll.setWidget(self._daily_row)
        daily_lay.addWidget(self._daily_scroll)
        layout.addWidget(daily_card)

        # --- Charts ----------------------------------------------------------
        charts_card = Card()
        charts_lay = QVBoxLayout(charts_card)
        charts_lay.setContentsMargins(16, 14, 16, 16)
        charts_lay.addWidget(SectionTitle("Weather charts",
                                          "Hover a point to inspect values"))
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._temp_chart = TemperatureChart()
        self._rain_chart = PrecipitationChart()
        self._wind_chart = WindChart()
        self._tabs.addTab(self._temp_chart, "🌡️ Temperature")
        self._tabs.addTab(self._rain_chart, "🌧️ Precipitation")
        self._tabs.addTab(self._wind_chart, "🌬️ Wind")
        charts_lay.addWidget(self._tabs)
        layout.addWidget(charts_card)

        # --- Activity planner --------------------------------------------------
        activity_card = Card()
        activity_lay = QVBoxLayout(activity_card)
        activity_lay.setContentsMargins(16, 14, 16, 16)
        activity_lay.addWidget(SectionTitle("Activity planner",
                                            "How suitable is today's weather for each activity?"))
        self._activity_grid = QGridLayout()
        self._activity_grid.setSpacing(10)
        self._activity_cards: list[ActivityCard] = []
        for i in range(8):
            ac = ActivityCard("", "")
            self._activity_cards.append(ac)
            self._activity_grid.addWidget(ac, i // 4, i % 4)
        activity_lay.addLayout(self._activity_grid)
        layout.addWidget(activity_card)

        # --- Alerts -------------------------------------------------------------
        self._alerts_card = Card()
        alerts_lay = QVBoxLayout(self._alerts_card)
        alerts_lay.setContentsMargins(16, 14, 16, 16)
        alerts_lay.addWidget(SectionTitle("Weather alerts",
                                          "Warnings generated from live thresholds"))
        self._alerts_container = QWidget()
        self._alerts_lay = QVBoxLayout(self._alerts_container)
        self._alerts_lay.setContentsMargins(0, 6, 0, 0)
        self._alerts_lay.setSpacing(8)
        alerts_lay.addWidget(self._alerts_container)
        layout.addWidget(self._alerts_card)

        layout.addStretch(1)
        scroll.setWidget(body)
        return scroll

    # ------------------------------------------------------------------
    # State switching
    # ------------------------------------------------------------------
    def show_empty(self) -> None:
        self._banner.hide()
        self.stack.setCurrentWidget(self._empty_page)

    def show_loading(self, message: str = "Fetching weather data...") -> None:
        self._loading_page.msg.setText(message)
        self._loading_page.spinner.start()
        self.stack.setCurrentWidget(self._loading_page)

    def stop_loading(self) -> None:
        self._loading_page.spinner.stop()

    def show_error(self, title: str, message: str) -> None:
        self.stop_loading()
        self._banner.hide()
        self._error_page.set_text(title, message)
        self.stack.setCurrentWidget(self._error_page)

    def show_offline_banner(self, weather: WeatherData) -> None:
        minutes = time_ago(weather.fetched_at)
        self._banner.label.setText(
            f"Offline Mode — showing cached weather data from {minutes}."
        )
        self._banner.show()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render_weather(self, weather: WeatherData) -> None:
        """Fully (re)render the dashboard for a weather snapshot."""
        self.stop_loading()
        self._weather = weather
        settings = self._settings
        t_unit, w_unit, p_unit = settings.units
        cur = weather.current
        tz = weather.location.tz_name

        # Hero
        self._hero.setObjectName("HeroCard")
        self._hero.style().unpolish(self._hero)
        self._hero.style().polish(self._hero)
        self.hero_location.setText(weather.location.display_name)
        self.hero_temp.setText(U.format_temp(cur.temperature, t_unit))
        self.hero_icon.setText(cur.icon)
        self.hero_condition.setText(cur.condition_text)
        self.hero_feels.setText(
            f"Feels like {U.format_temp(cur.feels_like, t_unit)}"
        )
        now_local = datetime.now(ZoneInfo(tz)) if tz else datetime.now()
        self.hero_local_time.setText(
            f"Local time: {now_local.strftime('%H:%M')}  ·  "
            f"{now_local.strftime('%a %d %b %Y')}"
        )
        if weather.source == "live":
            self.hero_updated.setText("Live · updated moments ago")
        else:
            self.hero_updated.setText(
                f"{'Demo' if weather.source == 'demo' else 'Cached'} · "
                f"{time_ago(weather.fetched_at)}"
            )
        sunrise = parse_iso_time(cur.sunrise, tz)
        sunset = parse_iso_time(cur.sunset, tz)
        self.hero_sunrise.setText(f"🌅 Sunrise {format_time(sunrise)}")
        self.hero_sunset.setText(f"🌇 Sunset {format_time(sunset)}")
        self.hero_clouds.setText(f"☁️ Cloud cover {cur.cloud_cover}%")
        self.hero_humid.setText(f"💧 Humidity {cur.humidity}%")
        self.set_favorite_state(self._favorites.contains(weather.location))

        # Stats
        self._stat_cards["humidity"].update_value(f"{cur.humidity}%", "Relative humidity")
        self._stat_cards["wind"].update_value(
            U.format_wind(cur.wind_speed, w_unit),
            f"Gusts {U.format_wind(cur.wind_gusts, w_unit)} · {U.wind_direction(cur.wind_direction)}",
        )
        self._stat_cards["pressure"].update_value(
            U.format_pressure(cur.pressure, p_unit), "Atmospheric pressure"
        )
        self._stat_cards["visibility"].update_value(
            U.format_visibility(cur.visibility_m, w_unit), "Visibility"
        )
        uv_text = f"{cur.uv_index:.1f}" if cur.uv_index is not None else "unavailable"
        uv_sub = "UV data unavailable" if cur.uv_index is None else "UV index"
        self._stat_cards["uv"].update_value(uv_text, uv_sub)
        self._stat_cards["clouds"].update_value(f"{cur.cloud_cover}%", "Sky coverage")
        aq = weather.air_quality
        if aq is not None and aq.available:
            self._stat_cards["air_quality"].update_value(
                f"AQI {aq.aqi:.0f}", U.aqi_category(aq.aqi)
            )
        else:
            self._stat_cards["air_quality"].update_value("—", "Air quality unavailable")

        # Intelligence
        score = self._intelligence.comfort_score(weather)
        self._gauge.set_score(score.total, score.grade)
        self.score_label.setText(
            f"{score.grade} · based on six weighted weather factors"
        )
        self._clear_layout(self._insights_lay)
        for insight in self._intelligence.insights(weather):
            self._insights_lay.addWidget(
                InsightCard(insight.icon, insight.title, insight.message, insight.level)
            )

        # Hourly
        self._render_hourly(weather, tz, t_unit)

        # Daily
        self._render_daily(weather, tz, t_unit)

        # Charts
        self._render_charts(weather, tz, t_unit, w_unit)

        # Activities
        activities = self._intelligence.activity_scores(weather)
        for i, act in enumerate(activities):
            if i < len(self._activity_cards):
                card = self._activity_cards[i]
                card.name_label.setText(act.name)
                card.set_score(act.score, act.label, act.reasons)

        # Alerts
        self._clear_layout(self._alerts_lay)
        alert_list = self._alerts.evaluate(weather, score.total)
        if alert_list:
            for alert in alert_list:
                self._alerts_lay.addWidget(
                    AlertCard(alert.icon, alert.title, alert.message, alert.level)
                )
        else:
            self._alerts_lay.addWidget(
                AlertCard("✅", "All clear", "No active weather warnings for this location.", "INFO")
            )

        if weather.source == "cache":
            self.show_offline_banner(weather)
        else:
            self._banner.hide()

        self.stack.setCurrentWidget(self._content_page)

    def re_render(self) -> None:
        """Re-apply current settings (e.g. after unit / theme changes)."""
        if self._weather is not None:
            self.render_weather(self._weather)

    def set_favorite_state(self, is_favorite: bool) -> None:
        self.star_button.setText("★" if is_favorite else "☆")
        self.star_button.setToolTip(
            "Remove from favorites" if is_favorite else "Save to favorites"
        )

    # ------------------------------------------------------------------
    # Sub-renders
    # ------------------------------------------------------------------
    def _render_hourly(self, weather: WeatherData, tz: str, t_unit: str) -> None:
        self._clear_layout(self._hourly_row_lay)
        self._hourly_items: list[HourlyItem] = []
        now_local = datetime.now(ZoneInfo(tz)) if tz else datetime.now()
        current_hour = now_local.strftime("%H:00")
        for h in weather.hourly:
            item = HourlyItem()
            dt = parse_iso_time(h.time, tz)
            time_text = format_time(dt) if dt else "—"
            is_current = (dt.strftime("%H:00") == current_hour) if dt else False
            item.set_data(
                time_text,
                h.icon,
                h.condition_text,
                U.format_temp(h.temperature, t_unit),
                f"💧 {h.precipitation_probability}%",
                is_current,
            )
            self._hourly_items.append(item)
            self._hourly_row_lay.addWidget(item)
        self._hourly_row_lay.addStretch(1)
        self._stop_replay()

    def _render_daily(self, weather: WeatherData, tz: str, t_unit: str) -> None:
        self._clear_layout(self._daily_row_lay)
        for i, d in enumerate(weather.daily):
            card = DailyCard()
            dt = parse_iso_time(d.date, tz)
            day = "Today" if i == 0 else format_date(dt).split(",")[0]
            card.set_data(
                day,
                format_date(dt) if dt else d.date,
                d.icon,
                U.format_temp(d.temp_max, t_unit),
                U.format_temp(d.temp_min, t_unit),
                d.condition_text,
                f"💧 {d.precipitation_probability}% · ☀️ UV {d.uv_index_max:.0f}" if d.uv_index_max else f"💧 {d.precipitation_probability}%",
            )
            self._daily_row_lay.addWidget(card)
        self._daily_row_lay.addStretch(1)

    def _render_charts(self, weather: WeatherData, tz: str, t_unit: str, w_unit: str) -> None:
        labels, temps, rains, winds = [], [], [], []
        for h in weather.hourly:
            dt = parse_iso_time(h.time, tz)
            labels.append(format_time(dt) if dt else "—")
            temps.append(h.temperature)
            rains.append(h.precipitation_probability)
            winds.append(h.wind_speed)

        # Keep x-axis readable for multi-day hourly data.
        if len(labels) > 16:
            step = max(1, len(labels) // 8)
            x_labels = [lbl if i % step == 0 else "" for i, lbl in enumerate(labels)]
        else:
            x_labels = labels

        self._temp_chart.update_data(x_labels, temps, f"°{t_unit}")
        self._rain_chart.update_data(x_labels, rains)
        self._wind_chart.update_data(x_labels, winds, f"{w_unit}/h")

    # ------------------------------------------------------------------
    # "Why this forecast?" dialog
    # ------------------------------------------------------------------
    def _on_why_clicked(self) -> None:
        if self._weather is None:
            return
        lines = self._intelligence.why(self._weather)
        dlg = WhyDialog(
            f"{self._weather.location.short_name} · Comfort score explanation",
            lines,
            self,
        )
        dlg.exec()

    # ------------------------------------------------------------------
    # Timeline replay
    # ------------------------------------------------------------------
    def _toggle_replay(self) -> None:
        if self._replay_timer.isActive():
            self._stop_replay()
            return
        if not getattr(self, "_hourly_items", None):
            return
        self._replay_index = 0
        self.replay_btn.setText("⏹ Stop replay")
        self.replay_status.setVisible(True)
        self._replay_step()
        self._replay_timer.start()

    def _replay_step(self) -> None:
        items = getattr(self, "_hourly_items", [])
        if not items:
            self._stop_replay()
            return
        if self._replay_index >= len(items):
            self._stop_replay()
            return
        item = items[self._replay_index]
        # highlight every item while walking through
        for i, other in enumerate(items):
            other.setProperty("current", i == self._replay_index)
            other.style().unpolish(other)
            other.style().polish(other)
        time_text = item.time_label.text()
        temp_text = item.temp_label.text()
        cond = item.icon_label.toolTip()
        self.replay_status.setText(
            f"▶ {time_text}  ·  {temp_text}  ·  {cond}"
        )
        item.ensure_visible(self._hourly_scroll)
        self._replay_index += 1

    def _stop_replay(self) -> None:
        self._replay_timer.stop()
        self.replay_btn.setText("▶ Timeline replay")
        self.replay_status.setVisible(False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
