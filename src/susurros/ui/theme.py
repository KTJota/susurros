"""Light and dark themes, style sheet and application icon.

The colours of the active theme are variables of this module (`theme.BG`, `theme.ACCENT`…):
`apply()` changes them and generates the style sheet again. The floating indicator and the
icon always use the dark palette (`DARK`), because they are drawn over any background.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap

DARK = {
    "BG": "#141312", "SURFACE": "#1c1b19", "SURFACE_2": "#262421", "BORDER": "#322f2b",
    "TEXT": "#ece7df", "MUTED": "#9b958b", "FAINT": "#8a857c",
    "ACCENT": "#f0a868", "ACCENT_HOVER": "#f5b67d", "ACCENT_DIM": "#3a2c1e", "ON_ACCENT": "#141312",
    "DANGER": "#e5735f", "OK": "#8fbf7f",
}
LIGHT = {
    "BG": "#f6f3ed", "SURFACE": "#fffdf9", "SURFACE_2": "#ebe6dc", "BORDER": "#dcd5c8",
    "TEXT": "#1f1c18", "MUTED": "#645e55", "FAINT": "#6f685e",
    "ACCENT": "#a85c18", "ACCENT_HOVER": "#8f4d12", "ACCENT_DIM": "#f3e2d0", "ON_ACCENT": "#ffffff",
    "DANGER": "#b83a27", "OK": "#3f7a2e",
}
MODES = ("light", "dark", "system")

# Initial values (dark theme); `apply()` replaces them.
BG, SURFACE, SURFACE_2, BORDER = DARK["BG"], DARK["SURFACE"], DARK["SURFACE_2"], DARK["BORDER"]
TEXT, MUTED, FAINT = DARK["TEXT"], DARK["MUTED"], DARK["FAINT"]
ACCENT, ACCENT_HOVER, ACCENT_DIM, ON_ACCENT = (DARK["ACCENT"], DARK["ACCENT_HOVER"],
                                               DARK["ACCENT_DIM"], DARK["ON_ACCENT"])
DANGER, OK = DARK["DANGER"], DARK["OK"]

FONT = '"Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif'
FONT_DISPLAY = '"Segoe UI Variable Display", "Segoe UI", "Inter", sans-serif'


def apply(mode: str) -> str:
    """Activates "light", "dark" or "system" and returns the theme that ends up in use."""
    app = QGuiApplication.instance()
    hints = app.styleHints()
    # Setting the scheme in Qt makes the Windows title bar follow the theme;
    # Unknown hands control back to the system.
    hints.setColorScheme({"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}
                         .get(mode, Qt.ColorScheme.Unknown))
    effective = mode if mode in ("light", "dark") else (
        "light" if hints.colorScheme() == Qt.ColorScheme.Light else "dark")
    globals().update(LIGHT if effective == "light" else DARK)
    app.setStyleSheet(stylesheet())
    return effective


def stylesheet() -> str:
    return f"""
* {{ font-family: {FONT}; font-size: 14px; color: {TEXT}; outline: none; }}
QMainWindow, #page {{ background: {BG}; }}
#sidebar {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
#wordmark {{ font-family: {FONT_DISPLAY}; font-size: 21px; font-weight: 600; letter-spacing: -0.3px; }}
#nav {{ text-align: left; padding: 8px 11px; border: 1px solid transparent; border-radius: 7px;
        color: {MUTED}; background: transparent; }}
#nav:focus {{ border-color: {ACCENT}; }}
#nav:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
#nav:checked {{ background: {SURFACE_2}; color: {TEXT}; font-weight: 600; }}
#status {{ color: {MUTED}; font-size: 12px; }}
#title {{ font-family: {FONT_DISPLAY}; font-size: 26px; font-weight: 600; letter-spacing: -0.4px; }}
#subtitle {{ color: {MUTED}; }}
#section {{ color: {FAINT}; font-size: 11px; font-weight: 600; letter-spacing: 1.2px; }}
#tile {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
#tileValue {{ font-family: {FONT_DISPLAY}; font-size: 24px; font-weight: 600; }}
#tileLabel {{ color: {MUTED}; font-size: 12px; }}
#row {{ background: transparent; border: none; border-bottom: 1px solid {BORDER}; }}
#row:hover {{ background: {SURFACE}; border-radius: 8px; }}
#row:focus {{ background: {SURFACE}; border: 1px solid {ACCENT}; border-radius: 8px; }}
#rowText {{ font-size: 14px; }}
#rowMeta {{ color: {FAINT}; font-size: 12px; }}
#rowHint {{ color: {FAINT}; font-size: 12px; }}
#rowHint[done="true"] {{ color: {OK}; }}
#hint, #empty {{ color: {MUTED}; }}
#notice {{ color: {DANGER}; font-size: 12px; }}
#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
#separator {{ background: {BORDER}; }}
#settingLabel {{ font-weight: 600; }}
#settingHelp {{ color: {MUTED}; font-size: 12px; }}
#chip {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; }}
#themeSwitch {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 9px; }}

QLineEdit {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
             padding: 8px 11px; selection-background-color: {ACCENT}; selection-color: {ON_ACCENT}; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QPushButton {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 14px; }}
QPushButton:hover {{ border-color: {FAINT}; }}
QPushButton:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QPushButton#link:focus, QPushButton#linkDanger:focus {{ color: {TEXT}; text-decoration: underline; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: {ON_ACCENT}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#link {{ background: transparent; border: none; padding: 2px 6px; color: {FAINT}; font-size: 12px; }}
QPushButton#link:hover {{ color: {TEXT}; }}
QPushButton#linkDanger {{ background: transparent; border: none; padding: 2px 6px; color: {FAINT}; font-size: 12px; }}
QPushButton#linkDanger:hover {{ color: {DANGER}; }}
QComboBox {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 11px; min-width: 210px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {BORDER};
                              selection-background-color: {ACCENT_DIM}; selection-color: {TEXT}; padding: 4px; }}
#scrollHost {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; height: 0; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; padding: 5px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMessageBox {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 7px; }}
"""


_BARS = (0.34, 0.62, 1.0, 0.5, 0.78)  # wave outline of the icon


def make_pixmap(size: int = 64) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(DARK["BG"]))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)
    p.setBrush(QColor(DARK["ACCENT"]))
    bar_w = size * 0.085
    gap = size * 0.065
    total = len(_BARS) * bar_w + (len(_BARS) - 1) * gap
    x = (size - total) / 2
    for h in _BARS:
        bar_h = size * 0.56 * h
        p.drawRoundedRect(QRectF(x, (size - bar_h) / 2, bar_w, bar_h), bar_w / 2, bar_w / 2)
        x += bar_w + gap
    p.end()
    return pixmap


def make_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(make_pixmap(size))
    return icon
