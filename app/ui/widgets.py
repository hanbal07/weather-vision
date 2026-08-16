"""Reusable UI widgets used by the dashboard, dialogs and pages."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.models.weather_models import Location
from app.ui.theme import current_theme


def make_label(text: str = "", object_name: str = "", tooltip: str = "") -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    if tooltip:
        label.setToolTip(tooltip)
    return label


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------
class Card(QFrame):
    """A rounded card that subtly highlights on hover."""

    def __init__(self, parent: QWidget | None = None, hoverable: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("hover", False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        if hoverable:
            self.setMouseTracking(True)

    def enterEvent(self, event) -> None:  # noqa: N802
        if self.property("hover") is False:
            self.setProperty("hover", True)
            self._refresh()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self.property("hover") is True:
            self.setProperty("hover", False)
            self._refresh()
        super().leaveEvent(event)

    def _refresh(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class SectionTitle(QLabel):
    def __init__(self, text: str, hint: str = "") -> None:
        super().__init__(text)
        self.setObjectName("SectionTitle")
        self.setToolTip(hint)


# ---------------------------------------------------------------------------
# Stat card
# ---------------------------------------------------------------------------
class StatCard(Card):
    def __init__(self, icon: str, label: str, value: str, sub: str = "") -> None:
        super().__init__(hoverable=True)
        self.setMinimumHeight(96)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(make_label(icon, "", label))
        header.addStretch(1)
        layout.addLayout(header)
        self.value_label = make_label(value, "StatValue", label)
        layout.addWidget(self.value_label)
        self.sub_label = make_label(sub, "StatLabel")
        layout.addWidget(self.sub_label)

    def update_value(self, value: str, sub: str = "") -> None:
        self.value_label.setText(value)
        self.sub_label.setText(sub)


# ---------------------------------------------------------------------------
# Spinner
# ---------------------------------------------------------------------------
class Spinner(QWidget):
    """A lightweight rotating arc used as a loading indicator."""

    def __init__(self, size: int = 36, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = 0
        self._size = size
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._running = False

    def start(self) -> None:
        self._running = True
        self._timer.start(16)

    def stop(self) -> None:
        self._running = False
        self._timer.stop()

    def _advance(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._running:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(current_theme().get("accent", "#2563EB"))
        pen = QPen(accent, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = QRectF(3, 3, self._size - 6, self._size - 6)
        painter.drawArc(rect, self._angle * 16, 110 * 16)
        painter.end()


# ---------------------------------------------------------------------------
# Loading / empty / error states
# ---------------------------------------------------------------------------
class LoadingView(QWidget):
    def __init__(self, message: str = "Fetching weather data...") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        self.spinner = Spinner(44)
        layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        self.msg = make_label(message, "Muted")
        layout.addWidget(self.msg, 0, Qt.AlignmentFlag.AlignHCenter)
        # A row of skeleton cards hints at the upcoming layout.
        skeleton_row = QHBoxLayout()
        for _ in range(4):
            box = QFrame()
            box.setObjectName("Skeleton")
            box.setMinimumHeight(84)
            skeleton_row.addWidget(box)
        layout.addLayout(skeleton_row)
        layout.setSpacing(18)
        layout.addStretch(1)
        self.spinner.start()

    def stop(self) -> None:
        self.spinner.stop()


class EmptyState(QWidget):
    def __init__(self, title: str = "No location selected", message: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addStretch(3)
        layout.addWidget(make_label("🌍", "EmptyIcon"), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(make_label(title, "ErrorTitle"), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(
            make_label(message or "Search for a city to begin.", "Muted"),
            0, Qt.AlignmentFlag.AlignHCenter,
        )
        layout.addStretch(3)


class ErrorState(QWidget):
    retry_clicked = Signal()

    def __init__(self, title: str = "Unable to fetch weather", message: str = "") -> None:
        super().__init__()
        self._title_label = make_label(title, "ErrorTitle")
        self._message_label = make_label(
            message or "Please check your internet connection and try again.", "Muted"
        )
        layout = QVBoxLayout(self)
        layout.addStretch(3)
        layout.addWidget(make_label("😕", "ErrorIcon"), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._title_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._message_label, 0, Qt.AlignmentFlag.AlignHCenter)
        retry = QPushButton("Retry")
        retry.setObjectName("PrimaryButton")
        retry.setCursor(Qt.CursorShape.PointingHandCursor)
        retry.clicked.connect(self.retry_clicked.emit)
        layout.addWidget(retry, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(8)
        layout.addStretch(3)

    def set_text(self, title: str, message: str) -> None:
        self._title_label.setText(title)
        self._message_label.setText(message)


# ---------------------------------------------------------------------------
# Offline banner
# ---------------------------------------------------------------------------
class OfflineBanner(Card):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("BannerOffline")
        self.setMinimumHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 10, 8)
        self.icon = make_label("📶", "", "Offline mode")
        layout.addWidget(self.icon)
        self.label = make_label("Offline Mode — showing cached data.", "Muted")
        layout.addWidget(self.label, 1)
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("GhostButton")
        self.close_btn.setFixedWidth(30)
        self.close_btn.setToolTip("Dismiss")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.hide)
        layout.addWidget(self.close_btn)
        self.hide()


# ---------------------------------------------------------------------------
# Score gauge
# ---------------------------------------------------------------------------
class ScoreGauge(QWidget):
    """A 0-100 gauge drawn with QPainter."""

    def __init__(self, size: int = 210, height: int = 140) -> None:
        super().__init__()
        self._score = 0
        self._grade = "—"
        self.setFixedSize(size, height)

    def set_score(self, score: int, grade: str) -> None:
        self._score = max(0, min(100, score))
        self._grade = grade
        self.update()

    @staticmethod
    def _score_color(score: int) -> QColor:
        hue = int(120 * score / 100.0)
        return QColor.fromHsv(hue, 190, 210)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        palette = current_theme()
        track = QColor(palette.get("border", "#26324F"))
        text_color = QColor(palette.get("text", "#E6EDF7"))
        muted = QColor(palette.get("text_muted", "#9AA8BF"))

        margin = 14
        radius = min(w / 2 - margin, h - margin * 1.6)
        center = QPointF(w / 2, h - margin + 2)
        rect = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)

        pen = QPen(track, 12)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 180 * 16, 180 * 16)

        value_pen = QPen(self._score_color(self._score), 12)
        value_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(value_pen)
        painter.drawArc(rect, 180 * 16, int(180 * self._score / 100.0) * 16)

        painter.setPen(text_color)
        font = QFont(self.font())
        font.setPointSize(26)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(0, h - 76, w, 40), Qt.AlignmentFlag.AlignCenter, str(self._score))

        painter.setPen(muted)
        small = QFont(self.font())
        small.setPointSize(10)
        painter.setFont(small)
        painter.drawText(QRectF(0, h - 34, w, 20), Qt.AlignmentFlag.AlignCenter, self._grade)
        painter.end()


# ---------------------------------------------------------------------------
# Insight / activity / alert cards
# ---------------------------------------------------------------------------
class InsightCard(Card):
    def __init__(self, icon: str, title: str, message: str, level: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)
        layout.addWidget(make_label(icon, "", f"Severity: {level}"))
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(make_label(title, "InsightTitle"))
        text.addWidget(make_label(message, "InsightText"))
        text.addWidget(make_label(f"Severity: {level}", "Soft"))
        layout.addLayout(text, 1)


class LevelBadge(QFrame):
    def __init__(self, level: str, text: str) -> None:
        super().__init__()
        self.setObjectName("LevelBadge")
        self.setProperty("level", level.upper() if level.upper() in (
            "INFO", "LOW", "MODERATE", "HIGH", "CRITICAL") else "INFO")
        self.setStyleSheet("")  # QSS handles the look
        self._label = make_label(text, "Soft")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.addWidget(self._label)
        self.style().unpolish(self)
        self.style().polish(self)


class AlertCard(Card):
    def __init__(self, icon: str, title: str, message: str, level: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addWidget(make_label(icon, "", f"Severity: {level}"))
        text = QVBoxLayout()
        text.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(make_label(title, "InsightTitle"))
        row.addWidget(LevelBadge(level, level.capitalize()))
        row.addStretch(1)
        text.addLayout(row)
        text.addWidget(make_label(message, "InsightText"))
        layout.addLayout(text, 1)


class ActivityCard(Card):
    def __init__(self, name: str, icon: str) -> None:
        super().__init__(hoverable=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(make_label(icon, "", name))
        head.addStretch(1)
        self.score_label = make_label("—", "StatValue", name)
        head.addWidget(self.score_label)
        layout.addLayout(head)
        self.name_label = make_label(name, "InsightTitle")
        layout.addWidget(self.name_label)
        from PySide6.QtWidgets import QProgressBar
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        layout.addWidget(self.bar)
        self.status_label = make_label("", "StatLabel")
        layout.addWidget(self.status_label)

    def set_score(self, score: int, label: str, reasons: list[str]) -> None:
        self.score_label.setText(f"{score}/100")
        self.bar.setValue(score)
        self.status_label.setText(label)
        self.setToolTip("\n".join(reasons) if reasons else label)
        from PySide6.QtGui import QColor
        hue = int(120 * score / 100.0)
        color = QColor.fromHsv(hue, 190, 210).name()
        self.bar.setStyleSheet(
            f"QProgressBar::chunk {{ border-radius: 4px; background: {color}; }}"
        )


# ---------------------------------------------------------------------------
# Hourly / daily forecast items
# ---------------------------------------------------------------------------
class HourlyItem(Card):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(96)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(4)
        self.time_label = make_label("", "StatLabel")
        self.icon_label = make_label("", "", "Weather condition")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.temp_label = make_label("", "InsightTitle")
        self.temp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rain_label = make_label("", "StatLabel")
        self.rain_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.time_label, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.temp_label)
        layout.addWidget(self.rain_label)

    def set_data(self, time_label: str, icon: str, condition: str,
                 temp_text: str, rain_text: str, is_current: bool) -> None:
        self.time_label.setText(time_label)
        self.icon_label.setText(icon)
        self.icon_label.setToolTip(condition)
        self.temp_label.setText(temp_text)
        self.rain_label.setText(rain_text)
        self.setProperty("current", is_current)
        if is_current:
            self.setStyleSheet(
                "QFrame#Card { border: 2px solid #38BDF8; border-radius: 14px; }"
            )
        else:
            self.setStyleSheet("")

    def ensure_visible(self, scroll_area: QScrollArea) -> None:
        scroll_area.ensureWidgetVisible(self, 24, 0)


class DailyCard(Card):
    def __init__(self) -> None:
        super().__init__(hoverable=True)
        self.setFixedWidth(150)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)
        self.day_label = make_label("", "CardTitle")
        self.date_label = make_label("", "StatLabel")
        self.icon_label = make_label("", "")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.high_label = make_label("", "StatValue")
        self.high_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.low_label = make_label("", "StatLabel")
        self.low_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cond_label = make_label("", "StatLabel")
        self.cond_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rain_label = make_label("", "StatLabel")
        self.rain_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.day_label)
        layout.addWidget(self.date_label)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.high_label)
        layout.addWidget(self.low_label)
        layout.addWidget(self.cond_label)
        layout.addWidget(self.rain_label)

    def set_data(self, day: str, date: str, icon: str, high: str, low: str,
                 condition: str, rain: str) -> None:
        self.day_label.setText(day)
        self.date_label.setText(date)
        self.icon_label.setText(icon)
        self.icon_label.setToolTip(condition)
        self.high_label.setText(high)
        self.low_label.setText(f"Low {low}")
        self.cond_label.setText(condition)
        self.rain_label.setText(rain)


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------
class LocationPickerDialog(QDialog):
    """Lets the user choose among multiple geocoding matches."""

    def __init__(self, locations: list[Location], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select a location")
        self.setMinimumWidth(420)
        self._selected: Location | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(make_label("Multiple matches found — pick one:", "InsightTitle"))

        self.list_widget = QListWidget()
        for loc in locations:
            item = QListWidgetItem(
                f"📍 {loc.display_name}"
                + (f"   ({int(loc.population):,} people)" if loc.population else "")
            )
            item.setData(Qt.ItemDataRole.UserRole, loc)
            self.list_widget.addItem(item)
        self.list_widget.setCurrentRow(0)
        self.list_widget.itemDoubleClicked.connect(lambda _: self._accept())
        layout.addWidget(self.list_widget, 1)

        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("GhostButton")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Select")
        ok.setObjectName("PrimaryButton")
        ok.clicked.connect(self._accept)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    def _accept(self) -> None:
        item = self.list_widget.currentItem()
        if item:
            self._selected = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def selected_location(self) -> Location | None:
        return self._selected


class WhyDialog(QDialog):
    """Shows the reasoning behind the Weather Comfort Score."""

    def __init__(self, title: str, lines: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Why this forecast?")
        self.setMinimumSize(480, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)

        head = QHBoxLayout()
        head.addWidget(make_label("🧠", "EmptyIcon"))
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.addWidget(make_label(title, "ErrorTitle"))
        text_col.addWidget(make_label("Every conclusion is derived from measured weather values.", "Muted"))
        head.addLayout(text_col)
        head.addStretch(1)
        layout.addLayout(head)

        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        for line in lines:
            label = make_label(line, "InsightText")
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            content_layout.addWidget(label)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        close = QPushButton("Close")
        close.setObjectName("PrimaryButton")
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
