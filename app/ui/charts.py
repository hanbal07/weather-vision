"""Custom QPainter-based charts.

Drawn by hand with Qt's QPainter: no third-party chart library is required.
They are fully theme-aware and interactive (hover a point to see its value).

Three chart types are provided as thin wrappers over the same painter:
temperature (line + gradient fill), precipitation probability (bars) and wind
(line). All automatically rebuild whenever the dashboard refreshes.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QLinearGradient
from PySide6.QtWidgets import QWidget

from app.ui.theme import current_theme

_PAD_L, _PAD_R, _PAD_T, _PAD_B = 52, 18, 26, 40


class ChartWidget(QWidget):
    """A single-series line or bar chart with hover tooltips."""

    def __init__(
        self,
        style: str = "line",
        parent: QWidget | None = None,
        decimals: int = 0,
    ) -> None:
        super().__init__(parent)
        self._style = style
        self._decimals = decimals
        self.setMinimumHeight(270)
        self.setMouseTracking(True)

        self._labels: list[str] = []
        self._values: list[float] = []
        self._unit: str = ""
        self._color: str | None = None
        self._hover_index: int = -1

    # ------------------------------------------------------------------
    def set_data(
        self,
        labels: list[str],
        values: list[float],
        unit: str = "",
        color: str | None = None,
        style: str | None = None,
    ) -> None:
        self._labels = list(labels)
        self._values = [float(v) if v is not None else 0.0 for v in values]
        self._unit = unit
        self._color = color
        if style:
            self._style = style
        self._hover_index = -1
        self.update()

    def clear(self) -> None:
        self._labels, self._values = [], []
        self.update()

    def has_data(self) -> bool:
        return bool(self._values)

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------
    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_index = -1
        self.update()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._values:
            return
        plot = self._plot_rect()
        if plot.width() <= 0:
            return
        n = len(self._values)
        ratio = (event.position().x() - plot.left()) / plot.width()
        index = int(round(ratio * (n - 1)))
        if 0 <= index < n and index != self._hover_index:
            self._hover_index = index
            self.update()
        super().mouseMoveEvent(event)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def _plot_rect(self) -> QRectF:
        return QRectF(
            _PAD_L, _PAD_T,
            self.width() - _PAD_L - _PAD_R,
            self.height() - _PAD_T - _PAD_B,
        )

    def _nice_range(self) -> tuple[float, float]:
        if not self._values:
            return 0.0, 100.0
        if self._style == "bar":
            return 0.0, max(10.0, max(self._values) * 1.1)
        lo = min(self._values)
        hi = max(self._values)
        span = max(1.0, hi - lo)
        return lo - span * 0.15, hi + span * 0.15

    def _x_pos(self, index: int, plot: QRectF) -> float:
        if len(self._values) <= 1:
            return plot.center().x()
        return plot.left() + index * plot.width() / (len(self._values) - 1)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = current_theme()

        if not self._values:
            painter.setPen(QColor(palette.get("text_muted", "#9AA8BF")))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data yet")
            painter.end()
            return

        text_color = QColor(palette.get("text_muted", "#9AA8BF"))
        grid_color = QColor(palette.get("grid", "#26324F"))
        series_color = QColor(self._color or palette.get("accent", "#38BDF8"))
        bg = QColor(palette.get("chart_bg", "#18213A"))

        painter.fillRect(self.rect(), bg)
        plot = self._plot_rect()
        y_lo, y_hi = self._nice_range()

        # Grid + Y labels
        small = QFont(self.font())
        small.setPointSize(9)
        painter.setFont(small)
        for i in range(5):
            y = plot.bottom() - i * plot.height() / 4.0
            value = y_lo + (y_hi - y_lo) * i / 4.0
            painter.setPen(QPen(grid_color, 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(text_color)
            painter.drawText(
                QRectF(0, y - 8, _PAD_L - 8, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{value:.{self._decimals}f}",
            )

        # X labels (max ~7)
        n = len(self._values)
        if n:
            step = max(1, n // 7)
            painter.setPen(text_color)
            for i in range(0, n, step):
                x = self._x_pos(i, plot)
                painter.drawText(
                    QRectF(x - 40, plot.bottom() + 8, 80, 18),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    self._labels[i],
                )

        if self._style == "bar":
            self._paint_bars(painter, plot, y_lo, y_hi, series_color)
        else:
            self._paint_line(painter, plot, y_lo, y_hi, series_color)

        # Hover marker + value box
        if 0 <= self._hover_index < n:
            self._paint_hover(painter, plot, y_lo, y_hi, series_color)

        # Unit label
        if self._unit:
            painter.setPen(QColor(palette.get("text_soft", "#6C7A94")))
            painter.drawText(
                QRectF(plot.left(), 4, plot.width(), 16),
                Qt.AlignmentFlag.AlignRight,
                self._unit,
            )

        painter.end()

    def _paint_line(
        self, painter: QPainter, plot: QRectF, y_lo: float, y_hi: float,
        color: QColor,
    ) -> None:
        points: list[QPointF] = []
        for i, value in enumerate(self._values):
            x = self._x_pos(i, plot)
            y = plot.bottom() - (value - y_lo) / (y_hi - y_lo) * plot.height()
            points.append(QPointF(x, y))

        # Gradient fill under the line
        fill = QLinearGradient(0, plot.top(), 0, plot.bottom())
        c = QColor(color)
        c.setAlpha(70)
        fill.setColorAt(0, c)
        c2 = QColor(color)
        c2.setAlpha(0)
        fill.setColorAt(1, c2)
        painter.setBrush(fill)
        painter.setPen(Qt.PenStyle.NoPen)
        path = points + [QPointF(points[-1].x(), plot.bottom()), QPointF(points[0].x(), plot.bottom())]
        painter.drawPolygon(path)

        # Line
        pen = QPen(color, 2.4)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(points)

        # Min/max markers
        lo_val = min(self._values)
        hi_val = max(self._values)
        lo_i = self._values.index(lo_val)
        hi_i = self._values.index(hi_val)
        painter.setBrush(QColor(color))
        for idx in (lo_i, hi_i):
            painter.drawEllipse(points[idx], 4, 4)
        painter.setPen(QColor("#F87171"))
        painter.drawText(
            QPointF(points[hi_i].x() + 6, points[hi_i].y() - 6),
            f"{hi_val:.{self._decimals}f}",
        )
        painter.setPen(QColor("#34D399"))
        painter.drawText(
            QPointF(points[lo_i].x() + 6, points[lo_i].y() + 14),
            f"{lo_val:.{self._decimals}f}",
        )

    def _paint_bars(
        self, painter: QPainter, plot: QRectF, y_lo: float, y_hi: float,
        color: QColor,
    ) -> None:
        n = len(self._values)
        slot = plot.width() / n
        bar_width = min(26.0, slot * 0.55)
        for i, value in enumerate(self._values):
            x = plot.left() + slot * i + (slot - bar_width) / 2
            y = plot.bottom() - (value - y_lo) / (y_hi - y_lo) * plot.height()
            rect = QRectF(x, y, bar_width, max(2.0, plot.bottom() - y))
            fill = QColor(color)
            fill.setAlpha(170)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 4, 4)

    def _paint_hover(
        self, painter: QPainter, plot: QRectF, y_lo: float, y_hi: float,
        color: QColor,
    ) -> None:
        n = len(self._values)
        if not n:
            return
        idx = self._hover_index
        x = self._x_pos(idx, plot)
        value = self._values[idx]
        y = plot.bottom() - (value - y_lo) / (y_hi - y_lo) * plot.height()

        painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        painter.setBrush(color)
        painter.setPen(QPen(color, 1))
        painter.drawEllipse(QPointF(x, y), 5, 5)

        text = f"{self._labels[idx]}  {value:.{self._decimals}f} {self._unit}".strip()
        metrics = painter.fontMetrics()
        box_w = metrics.horizontalAdvance(text) + 18
        box_h = metrics.height() + 10
        bx = min(max(x - box_w / 2, plot.left()), plot.right() - box_w)
        by = max(plot.top(), y - box_h - 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(current_theme().get("card", "#18213A")))
        painter.drawRoundedRect(QRectF(bx, by, box_w, box_h), 6, 6)
        painter.setPen(QColor(current_theme().get("text", "#E6EDF7")))
        painter.drawText(
            QRectF(bx, by, box_w, box_h), Qt.AlignmentFlag.AlignCenter, text
        )


class TemperatureChart(ChartWidget):
    def __init__(self) -> None:
        super().__init__(style="line", decimals=0)

    def update_data(self, labels: list[str], values: list[float], unit: str) -> None:
        self.set_data(labels, values, unit=unit, style="line")


class PrecipitationChart(ChartWidget):
    def __init__(self) -> None:
        super().__init__(style="bar", decimals=0)

    def update_data(self, labels: list[str], values: list[float]) -> None:
        self.set_data(labels, values, unit="% chance", style="bar")


class WindChart(ChartWidget):
    def __init__(self) -> None:
        super().__init__(style="line", decimals=0)

    def update_data(self, labels: list[str], values: list[float], unit: str) -> None:
        self.set_data(labels, values, unit=unit, style="line")
