"""Theme management: two curated palettes (dark / light) and the QSS.

Both themes are designed independently (not inverted), with distinct
backgrounds, cards, borders, text and accent colours for charts too.
"""
from __future__ import annotations

from string import Template


class Theme:
    """A colour palette + helper accessors."""

    def __init__(self, colors: dict[str, str]) -> None:
        self.colors = colors

    def __getitem__(self, key: str) -> str:
        return self.colors[key]

    def get(self, key: str, default: str = "") -> str:
        return self.colors.get(key, default)


LIGHT_COLORS: dict[str, str] = {
    "bg": "#EEF2F7",
    "bg_alt": "#E3EAF2",
    "card": "#FFFFFF",
    "card_hover": "#F5F9FE",
    "border": "#D9E2EC",
    "text": "#16233B",
    "text_muted": "#5B6B82",
    "text_soft": "#8494AC",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_soft": "#DBEAFE",
    "success": "#16A34A",
    "warning": "#D97706",
    "danger": "#DC2626",
    "info": "#0891B2",
    "input_bg": "#FFFFFF",
    "header_bg": "#FFFFFF",
    "hero_from": "#1E6FE8",
    "hero_to": "#2AA5E6",
    "hero_text": "#FFFFFF",
    "grid": "#D9E2EC",
    "series_primary": "#2563EB",
    "series_secondary": "#10B981",
    "series_tertiary": "#F59E0B",
    "chart_bg": "#FFFFFF",
}

DARK_COLORS: dict[str, str] = {
    "bg": "#0D1526",
    "bg_alt": "#0A101F",
    "card": "#18213A",
    "card_hover": "#1E2A49",
    "border": "#26324F",
    "text": "#E6EDF7",
    "text_muted": "#9AA8BF",
    "text_soft": "#6C7A94",
    "accent": "#38BDF8",
    "accent_hover": "#0EA5E9",
    "accent_soft": "#15324F",
    "success": "#34D399",
    "warning": "#FBBF24",
    "danger": "#F87171",
    "info": "#22D3EE",
    "input_bg": "#121B30",
    "header_bg": "#0D1526",
    "hero_from": "#0EA5E9",
    "hero_to": "#6D5BD0",
    "hero_text": "#FFFFFF",
    "grid": "#26324F",
    "series_primary": "#38BDF8",
    "series_secondary": "#34D399",
    "series_tertiary": "#FBBF24",
    "chart_bg": "#18213A",
}

_STYLESHEET_TEMPLATE = Template(
    """
* {
    font-family: "Segoe UI", "Segoe UI Variable Text", "Arial";
    font-size: 13px;
    color: $text;
}
QMainWindow, QWidget#Central, QDialog {
    background: $bg;
}
QWidget { background: transparent; }
QWidget#Sidebar { background: $bg_alt; border-right: 1px solid $border; }
QWidget#Header { background: $header_bg; border-bottom: 1px solid $border; }

/* ---------- Cards ---------- */
QFrame#Card, QFrame#CardInset {
    background: $card;
    border: 1px solid $border;
    border-radius: 14px;
}
QFrame#Card[hover="true"] {
    background: $card_hover;
    border: 1px solid $accent;
}
QFrame#HeroCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $hero_from, stop:1 $hero_to);
    border: none;
    border-radius: 16px;
}
QFrame#Banner {
    background: $accent_soft;
    border: 1px solid $accent;
    border-radius: 10px;
}
QFrame#BannerOffline {
    background: rgba(245, 158, 11, 28);
    border: 1px solid $warning;
    border-radius: 10px;
}
QFrame#Skeleton { background: $bg_alt; border-radius: 12px; border: none; }
QFrame#LevelBadge { border-radius: 9px; padding: 2px 8px; }
QFrame#LevelBadge[level="INFO"]    { background: rgba(34, 211, 238, 40); border: 1px solid $info; }
QFrame#LevelBadge[level="LOW"]     { background: rgba(34, 211, 238, 40); border: 1px solid $info; }
QFrame#LevelBadge[level="MODERATE"]{ background: rgba(251, 191, 36, 40); border: 1px solid $warning; }
QFrame#LevelBadge[level="HIGH"]    { background: rgba(249, 115, 22, 40); border: 1px solid #F97316; }
QFrame#LevelBadge[level="CRITICAL"]{ background: rgba(248, 113, 113, 45); border: 1px solid $danger; }

/* ---------- Labels ---------- */
QLabel#AppTitle { font-size: 19px; font-weight: 700; color: $text; }
QLabel#AppSubtitle { font-size: 11px; color: $text_muted; }
QLabel#PageTitle { font-size: 20px; font-weight: 700; }
QLabel#SectionTitle { font-size: 15px; font-weight: 600; }
QLabel#CardTitle { font-size: 13px; font-weight: 600; color: $text_muted; }
QLabel#StatValue { font-size: 20px; font-weight: 700; }
QLabel#StatLabel { font-size: 11px; color: $text_muted; }
QLabel#HeroTemp { font-size: 58px; font-weight: 700; color: $hero_text; }
QLabel#HeroFeels { font-size: 14px; color: rgba(255,255,255,200); }
QLabel#HeroInfo { font-size: 12px; color: rgba(255,255,255,220); }
QLabel#HeroTitle { font-size: 22px; font-weight: 600; color: $hero_text; }
QLabel#Muted { color: $text_muted; }
QLabel#Soft { color: $text_soft; }
QLabel#ErrorTitle { font-size: 18px; font-weight: 700; }
QLabel#EmptyIcon, QLabel#ErrorIcon { font-size: 44px; }
QLabel#ScoreValue { font-size: 34px; font-weight: 700; }
QLabel#ScoreGrade { font-size: 12px; font-weight: 600; color: $text_muted; }
QLabel#InsightTitle { font-size: 13px; font-weight: 600; }
QLabel#InsightText { font-size: 12px; color: $text_muted; }
QLabel#DemoBadge {
    background: $warning; color: #1a1202; border-radius: 9px;
    font-size: 10px; font-weight: 700; padding: 3px 8px;
}

/* ---------- Buttons ---------- */
QPushButton {
    background: $bg_alt;
    border: 1px solid $border;
    border-radius: 9px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover { background: $card_hover; border-color: $accent; color: $accent; }
QPushButton:pressed { background: $accent_soft; }
QPushButton:disabled { color: $text_soft; background: $bg_alt; border-color: $border; }

QPushButton#PrimaryButton {
    background: $accent; color: white; border: none; padding: 8px 16px;
}
QPushButton#PrimaryButton:hover { background: $accent_hover; color: white; }
QPushButton#PrimaryButton:pressed { background: $accent_hover; }

QPushButton#GhostButton { background: transparent; border: 1px solid $border; }
QPushButton#GhostButton:hover { background: $card_hover; border-color: $accent; }

QPushButton#IconButton {
    background: $bg_alt; border: 1px solid $border; border-radius: 9px;
    padding: 6px 10px; font-size: 16px;
}
QPushButton#IconButton:hover { background: $card_hover; border-color: $accent; }

QPushButton#DangerButton { background: transparent; border: 1px solid $danger; color: $danger; }
QPushButton#DangerButton:hover { background: rgba(248,113,113,35); }

QPushButton#NavButton {
    background: transparent; border: none; border-radius: 10px;
    text-align: left; padding: 10px 14px; font-size: 14px; font-weight: 600; color: $text_muted;
}
QPushButton#NavButton:hover { background: $card; color: $text; }
QPushButton#NavButton:checked { background: $accent_soft; color: $accent; }

QPushButton#StarButton { background: transparent; border: none; font-size: 24px; padding: 4px; }
QPushButton#StarButton:hover { background: $card_hover; border-radius: 8px; }

/* ---------- Inputs ---------- */
QLineEdit {
    background: $input_bg; border: 1px solid $border; border-radius: 10px;
    padding: 8px 12px; selection-background-color: $accent; selection-color: white;
}
QLineEdit:focus { border: 1px solid $accent; }
QComboBox, QSpinBox {
    background: $input_bg; border: 1px solid $border; border-radius: 9px; padding: 6px 10px;
}
QComboBox:focus, QSpinBox:focus { border: 1px solid $accent; }
QComboBox QAbstractItemView {
    background: $card; border: 1px solid $border; border-radius: 8px; selection-background-color: $accent_soft;
    selection-color: $accent; outline: none;
}
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border-radius: 5px; border: 1px solid $border; background: $input_bg; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; }

/* ---------- Tabs (charts) ---------- */
QTabWidget::pane { border: 1px solid $border; border-radius: 12px; background: $card; }
QTabBar::tab {
    background: transparent; color: $text_muted; padding: 8px 18px;
    border: none; border-bottom: 2px solid transparent; font-weight: 600;
}
QTabBar::tab:hover { color: $text; }
QTabBar::tab:selected { color: $accent; border-bottom: 2px solid $accent; }

/* ---------- Scroll areas ---------- */
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $text_soft; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: $text_soft; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }

/* ---------- Lists ---------- */
QListWidget {
    background: $card; border: 1px solid $border; border-radius: 12px; padding: 6px;
    outline: none;
}
QListWidget::item { border-radius: 8px; padding: 8px; }
QListWidget::item:hover { background: $card_hover; }
QListWidget::item:selected { background: $accent_soft; color: $accent; }

/* ---------- Progress (activity cards) ---------- */
QProgressBar {
    background: $bg_alt; border: none; border-radius: 4px; height: 8px;
    text-align: center; color: transparent;
}
QProgressBar::chunk { border-radius: 4px; background: $accent; }

/* ---------- Misc ---------- */
QToolTip {
    background: $card; color: $text; border: 1px solid $border;
    border-radius: 6px; padding: 6px 8px;
}
QStatusBar { background: $bg; color: $text_muted; border-top: 1px solid $border; }
QStatusBar::item { border: none; }
QMenu { background: $card; border: 1px solid $border; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 6px; }
QMenu::item:selected { background: $accent_soft; color: $accent; }
"""
)


PALETTES = {
    "dark": Theme(DARK_COLORS),
    "light": Theme(LIGHT_COLORS),
}


class ThemeManager:
    """Applies a theme to the whole application and exposes its palette."""

    def __init__(self, initial: str = "dark") -> None:
        self.current: str = initial if initial in PALETTES else "dark"

    def set_theme(self, name: str, app: "object | None" = None) -> None:
        if name not in PALETTES:
            name = "dark"
        self.current = name
        if app is not None:
            app.setStyleSheet(self.stylesheet())

    def toggle(self, app: "object | None" = None) -> str:
        self.current = "light" if self.current == "dark" else "dark"
        if app is not None:
            app.setStyleSheet(self.stylesheet())
        return self.current

    def palette(self) -> Theme:
        return PALETTES[self.current]

    def stylesheet(self) -> str:
        return _STYLESHEET_TEMPLATE.substitute(self.palette().colors)


# Module-level singleton so widgets, charts and the window share one theme.
theme = ThemeManager()


def current_theme() -> Theme:
    """Return the shared palette (used by painted widgets)."""
    return theme.palette()
