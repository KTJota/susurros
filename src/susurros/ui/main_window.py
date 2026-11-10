"""Main window: history, insights, dictionary and settings."""
from __future__ import annotations

import sys
from datetime import datetime

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .. import audio, autostart, config, sounds
from ..db import Store
from ..i18n import day_label, fmt_decimal, fmt_int, tr
from . import theme

IS_MAC = sys.platform == "darwin"
CAN_CAPTURE = sys.platform in ("win32", "darwin")   # systems with a keyboard listener
HISTORY_LIMIT = 100   # rows shown at once: beyond this, every refresh and theme change is noticeable


def _label(text: str, name: str, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def _engine_label(engine: str) -> str:
    """How a dictation was cleaned, for the row's meta line; empty for the plain local rules."""
    if engine == "claude":
        return tr("polished with Claude")
    if engine == "live":
        return tr("typed while speaking")
    return ""


def _fmt_saved(minutes: float) -> str:
    if minutes < 60:
        return f"{round(minutes)} min"
    return f"{fmt_decimal(minutes / 60)} h"


def _scroll(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(inner)
    area.viewport().setObjectName("scrollHost")
    inner.setObjectName("scrollHost")
    return area


class Toggle(QCheckBox):
    """Sliding switch; behaves like a regular checkbox."""

    def __init__(self, checked: bool = False):
        super().__init__()
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 22)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        on = self.isChecked()
        p.setBrush(QColor(theme.ACCENT if on else theme.BORDER))
        p.drawRoundedRect(QRectF(0, 0, 40, 22), 11, 11)
        p.setBrush(QColor(theme.BG if on else theme.MUTED))
        p.drawEllipse(QRectF(21 if on else 3, 3, 16, 16))
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QColor(theme.TEXT))
            p.drawRoundedRect(QRectF(0.5, 0.5, 39, 21), 10.5, 10.5)
        p.end()


class ThemeButton(QToolButton):
    """Theme switcher button; paints its own icon in the colours of the active theme."""

    def __init__(self, mode: str, tooltip: str):
        super().__init__()
        self.mode = mode
        self.setCheckable(True)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(34, 28)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.isChecked() or self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.SURFACE_2))
            p.drawRoundedRect(QRectF(self.rect()), 6, 6)
        color = QColor(theme.TEXT if self.isChecked() else theme.MUTED)
        p.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.translate(self.width() / 2, self.height() / 2)
        if self.mode == "light":       # sun
            p.drawEllipse(QRectF(-3.5, -3.5, 7, 7))
            for _ in range(8):
                p.drawLine(0, -6, 0, -8)
                p.rotate(45)
        elif self.mode == "dark":      # moon
            moon = QPainterPath()
            moon.addEllipse(QRectF(-7, -7, 14, 14))
            bite = QPainterPath()
            bite.addEllipse(QRectF(-2, -10, 14, 14))
            p.drawPath(moon.subtracted(bite))
        else:                          # screen: follow the system
            p.drawRoundedRect(QRectF(-8, -7, 16, 11), 2, 2)
            p.drawLine(0, 4, 0, 7)
            p.drawLine(-4, 7, 4, 7)
        if self.hasFocus() and self.focusReason() in (Qt.TabFocusReason, Qt.BacktabFocusReason):
            p.resetTransform()
            p.setPen(QPen(QColor(theme.ACCENT), 1.5))
            p.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), 6, 6)
        p.end()

    def focusReason(self):
        return getattr(self, "_focus_reason", None)

    def focusInEvent(self, event) -> None:
        self._focus_reason = event.reason()
        super().focusInEvent(event)


class ClickRow(QFrame):
    """History row: a click anywhere (or Enter/Space when focused) copies the dictation."""
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()


class Combo(QComboBox):
    """Drop-down that does not change value with the wheel while the page is scrolled."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class MainWindow(QMainWindow):
    apiKeyChanged = Signal()
    hudChanged = Signal()
    hotkeyCaptureRequested = Signal()
    hotkeyCaptureAbandoned = Signal()   # the window was hidden or lost focus while waiting for the key
    languageChanged = Signal()          # the interface language setting has a new value
    quitting = False                    # set when the whole app is closing: the window then lets itself be closed

    def __init__(self, store: Store, hotkey_name: str):
        """`hotkey_name` is the shortcut as shown to the user, already in the interface language."""
        super().__init__()
        self.store = store
        self.hotkey_name = hotkey_name
        self.setWindowTitle("Susurros")
        self.setWindowIcon(theme.make_icon())
        self.resize(980, 680)
        self.setMinimumSize(780, 520)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.stack = QStackedWidget()
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.stack.addWidget(self._build_history())
        self.stack.addWidget(self._build_insights())
        self.stack.addWidget(self._build_dictionary())
        self.stack.addWidget(self._build_settings())
        self.refresh_dictionary()

        # Theme switcher, floating in the top right corner above every page.
        self._theme_switch = QFrame(root)
        self._theme_switch.setObjectName("themeSwitch")
        switch = QHBoxLayout(self._theme_switch)
        switch.setContentsMargins(3, 3, 3, 3)
        switch.setSpacing(2)
        self._theme_buttons = QButtonGroup(self)
        for mode, tooltip in (("light", tr("Light theme")), ("dark", tr("Dark theme")),
                              ("system", tr("Same as system"))):
            button = ThemeButton(mode, tooltip)
            self._theme_buttons.addButton(button)
            switch.addWidget(button)
            button.clicked.connect(lambda _c=False, m=mode: self.set_theme(m))
        self._theme_switch.adjustSize()
        self.set_theme(self.store.get("theme"))
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_scheme)

    def set_theme(self, mode: str) -> None:
        mode = mode if mode in theme.MODES else "system"
        self._theme_mode = mode
        if self.store.get("theme") != mode:
            self.store.set("theme", mode)
        for button in self._theme_buttons.buttons():
            button.setChecked(button.mode == mode)
        self._applied_scheme = theme.apply(mode)
        self.set_status(*self._status)  # the status dot carries its colour inline

    def _on_system_scheme(self, _scheme) -> None:
        # With "same as system", Windows has switched between light and dark.
        if self._theme_mode == "system":
            now = "light" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light else "dark"
            if now != self._applied_scheme:
                self.set_theme("system")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._theme_switch.move(self.centralWidget().width() - self._theme_switch.width() - 40, 32)
        self._theme_switch.raise_()

    # -- sidebar ---------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(208)
        box = QVBoxLayout(side)
        box.setContentsMargins(14, 22, 14, 16)
        box.setSpacing(4)

        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 18)
        brand.setSpacing(10)
        logo = QLabel()
        pixmap = theme.make_pixmap(56)
        pixmap.setDevicePixelRatio(2)
        logo.setPixmap(pixmap)
        brand.addWidget(logo)
        brand.addWidget(_label("susurros", "wordmark"))
        brand.addStretch()
        box.addLayout(brand)

        self._nav = QButtonGroup(self)
        for index, name in enumerate((tr("History"), "Insights", tr("Dictionary"), tr("Settings"))):
            button = QPushButton(name)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self._nav.addButton(button, index)
            box.addWidget(button)
        self._nav.button(0).setChecked(True)
        self._nav.idClicked.connect(self.stack.setCurrentIndex)
        self._nav.idClicked.connect(lambda _index: self.hotkeyCaptureAbandoned.emit())
        box.addStretch()

        status = QHBoxLayout()
        status.setContentsMargins(8, 0, 0, 0)
        status.setSpacing(8)
        self._status_dot = QLabel()
        self._status_dot.setFixedSize(8, 8)
        self._status_text = _label("", "status", wrap=True)
        status.addWidget(self._status_dot, 0, Qt.AlignTop)
        status.addWidget(self._status_text, 1)
        box.addLayout(status)
        self.set_status(tr("Loading the speech model…"), "busy")
        return side

    def set_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self._nav.button(index).setChecked(True)

    def set_status(self, text: str, kind: str = "ok") -> None:
        self._status = (text, kind)
        self._status_text.setToolTip(text if len(text) > 60 else "")   # long errors do not fit
        color = {"ok": theme.OK, "busy": theme.ACCENT, "error": theme.DANGER, "off": theme.FAINT}[kind]
        self._status_dot.setStyleSheet(f"background: {color}; border-radius: 4px; margin-top: 4px;")
        self._status_dot.setFixedSize(8, 12)
        self._status_text.setText(text)

    def _page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("page")
        box = QVBoxLayout(page)
        box.setContentsMargins(40, 34, 40, 0)
        box.setSpacing(0)
        box.addWidget(_label(title, "title"))
        box.addSpacing(4)
        box.addWidget(_label(subtitle, "subtitle", wrap=True))
        box.addSpacing(22)
        return page, box

    # -- history ---------------------------------------------------------
    def _build_history(self) -> QWidget:
        page, box = self._page(tr("History"), "")
        self._history_subtitle = page.findChild(QLabel, "subtitle")

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self._search = QLineEdit()
        self._search.setPlaceholderText(tr("Search your dictations"))
        self._search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self, singleShot=True, interval=180, timeout=self.refresh_history)
        self._search.textChanged.connect(lambda _t: self._search_timer.start())
        search_row.addWidget(self._search, 1)
        clear = QPushButton(tr("Clear history"))
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self._confirm_clear)
        self._clear_button = clear
        search_row.addWidget(clear)
        box.addLayout(search_row)
        box.addSpacing(8)

        self._history_host = QWidget()
        self._history_box = QVBoxLayout(self._history_host)
        self._history_box.setContentsMargins(0, 0, 12, 24)
        self._history_box.setSpacing(0)
        box.addWidget(_scroll(self._history_host), 1)
        return page

    def refresh_history(self, force: bool = False) -> None:
        stats = self.refresh_insights()
        self._clear_button.setVisible(stats["count"] > 0)
        if not (self.isVisible() or force):
            # Hidden in the tray, the list is not rebuilt after every dictation: that happens when it is shown.
            self._history_dirty = True
            return
        self._history_dirty = False

        while self._history_box.count():
            item = self._history_box.takeAt(0)
            if item.widget():
                item.widget().hide()   # deleteLater waits for the event loop: keep it out of sight meanwhile
                item.widget().deleteLater()

        query = self._search.text()
        rows = self.store.list_transcriptions(query, HISTORY_LIMIT)
        self._history_empty = not rows
        if not rows:
            text = (tr('No dictation contains "{query}".', query=query.strip()) if query.strip() else
                    tr("No dictations yet. Hold {key}, speak and release: the text appears where "
                       "your cursor is and is saved here.", key=self.hotkey_name))
            empty = _label(text, "empty", wrap=True)
            empty.setContentsMargins(0, 26, 0, 0)
            self._history_box.addWidget(empty)
            self._history_box.addStretch()
            return

        current_day = None
        for row in rows:
            created = datetime.fromisoformat(row["created_at"])
            if created.date() != current_day:
                current_day = created.date()
                header = _label(day_label(current_day), "section")
                header.setContentsMargins(0, 20, 0, 6)
                self._history_box.addWidget(header)
            self._history_box.addWidget(self._history_row(row, created))
        if len(rows) == HISTORY_LIMIT and (query.strip() or stats["count"] > HISTORY_LIMIT):
            more = _label(
                tr("Showing the {n} most recent. Use search to find older ones.", n=HISTORY_LIMIT)
                if not query.strip() else tr("Showing the {n} most recent matches.", n=HISTORY_LIMIT),
                "hint", wrap=True)
            more.setContentsMargins(12, 16, 0, 0)
            self._history_box.addWidget(more)
        self._history_box.addStretch()

    def _history_row(self, row, created: datetime) -> QWidget:
        frame = ClickRow()
        frame.setObjectName("row")
        frame.setCursor(Qt.PointingHandCursor)
        box = QVBoxLayout(frame)
        box.setContentsMargins(12, 12, 8, 10)
        box.setSpacing(5)
        text = _label(row["text"], "rowText", wrap=True)
        text.setTextFormat(Qt.PlainText)
        # A very long word (a URL) is clipped instead of widening the whole list.
        text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        box.addWidget(text)

        meta_parts = [created.strftime("%H:%M")]
        if row["app"]:
            meta_parts.append(row["app"])
        meta_parts.append(tr("{n} words", n=row["words"]) if row["words"] != 1 else tr("1 word"))
        if _engine_label(row["engine"] or ""):
            meta_parts.append(_engine_label(row["engine"]))
        footer = QHBoxLayout()
        footer.setSpacing(2)
        meta = _label("  ·  ".join(meta_parts), "rowMeta")
        meta.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        footer.addWidget(meta, 1)
        copy = _label(tr("Click to copy"), "rowHint")
        copy.setContentsMargins(0, 0, 8, 0)

        def do_copy(value=row["text"], hint=copy):
            QGuiApplication.clipboard().setText(value)
            hint.setText(tr("Copied"))
            hint.setProperty("done", True)
            hint.style().polish(hint)

            def reset():
                hint.setText(tr("Click to copy"))
                hint.setProperty("done", False)
                hint.style().polish(hint)
            QTimer.singleShot(1400, hint, reset)  # does not run if the row is gone by then

        frame.clicked.connect(do_copy)
        delete = QPushButton(tr("Delete"))
        delete.setObjectName("linkDanger")
        delete.setCursor(Qt.PointingHandCursor)
        delete.clicked.connect(lambda _c=False, rid=row["id"]: self._delete(rid))
        footer.addWidget(copy)
        footer.addWidget(delete)
        box.addLayout(footer)
        return frame

    def _delete(self, row_id: int) -> None:
        self.store.delete_transcription(row_id)
        self.refresh_history()

    def _confirm_clear(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(tr("Clear history"))
        box.setText(tr("Delete all saved dictations?"))
        box.setInformativeText(tr("This can't be undone."))
        confirm = box.addButton(tr("Delete all"), QMessageBox.DestructiveRole)
        box.addButton(tr("Cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is confirm:
            self.store.clear_history()
            self.refresh_history()

    # -- insights --------------------------------------------------------
    def _tile_row(self, box: QVBoxLayout, items: tuple[tuple[str, str], ...]) -> None:
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        for key, caption in items:
            tile = QFrame()
            tile.setObjectName("tile")
            inner = QVBoxLayout(tile)
            inner.setContentsMargins(16, 13, 16, 13)
            inner.setSpacing(1)
            value = _label("0", "tileValue")
            self._tiles[key] = value
            inner.addWidget(value)
            inner.addWidget(_label(caption, "tileLabel", wrap=True))
            tiles.addWidget(tile, 1)
        box.addLayout(tiles)

    def _build_insights(self) -> QWidget:
        page, box = self._page("Insights", tr("How much you dictate, how fast, and how much cleanup changes."))
        self._tiles: dict[str, QLabel] = {}
        box.addWidget(_label(tr("PACE AND VOLUME"), "section"))
        box.addSpacing(10)
        self._tile_row(box, (("wpm", tr("words per minute")), ("words", tr("words dictated in total")),
                             ("count", tr("dictations")), ("saved", tr("saved compared with typing"))))
        box.addSpacing(26)
        box.addWidget(_label(tr("CLEANUP"), "section"))
        box.addSpacing(10)
        self._tile_row(box, (("fixes_per", tr("edits per dictation")), ("fixes", tr("words edited")),
                             ("fillers", tr("filler words removed")),
                             ("fixes_pct", tr("of what you say gets edited"))))
        box.addSpacing(14)
        self._insights_note = _label("", "hint", wrap=True)
        box.addWidget(self._insights_note)
        box.addStretch()
        return page

    def refresh_insights(self) -> dict:
        stats = self.store.stats()
        measured = stats["measured"] > 0
        self._tiles["wpm"].setText(str(stats["wpm"]) if stats["wpm"] else "–")
        self._tiles["words"].setText(fmt_int(stats["words"]))
        self._tiles["count"].setText(fmt_int(stats["count"]))
        self._tiles["saved"].setText(_fmt_saved(stats["saved_min"]))
        self._tiles["fixes_per"].setText(fmt_decimal(stats["fixes_per"]) if measured else "–")
        self._tiles["fixes"].setText(fmt_int(stats["fixes"]) if measured else "–")
        self._tiles["fillers"].setText(fmt_int(stats["fillers"]) if measured else "–")
        self._tiles["fixes_pct"].setText(tr("{value}%", value=fmt_decimal(stats["fixes_pct"])) if measured else "–")
        notes = [tr("An edit is a word that cleanup removed or changed from what was transcribed: "
                    "filler words (uh, um), repetitions and self-corrections. "
                    "Changes to punctuation and capitalization don't count.")]
        if stats["count"] > stats["measured"]:
            notes.append(tr("Cleanup figures come from {measured} of your {count} dictations: "
                            "earlier ones didn't record edits.",
                            measured=stats["measured"], count=stats["count"]))
        self._insights_note.setText(" ".join(notes))
        return stats

    # -- dictionary ------------------------------------------------------
    def _build_dictionary(self) -> QWidget:
        page, box = self._page(
            tr("Dictionary"),
            tr("Names, acronyms and technical terms you want spelled the same way every time."))
        add_row = QHBoxLayout()
        add_row.setSpacing(10)
        self._word_input = QLineEdit()
        self._word_input.setPlaceholderText(tr("For example: PySide, kubectl, Zaragoza"))
        self._word_input.setMaxLength(60)
        self._word_input.returnPressed.connect(self._add_word)
        add = QPushButton(tr("Add"))
        add.setObjectName("primary")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self._add_word)
        add_row.addWidget(self._word_input, 1)
        add_row.addWidget(add)
        box.addLayout(add_row)
        box.addSpacing(14)

        self._words_host = QWidget()
        self._words_box = QVBoxLayout(self._words_host)
        self._words_box.setContentsMargins(0, 0, 12, 24)
        self._words_box.setSpacing(6)
        box.addWidget(_scroll(self._words_host), 1)
        return page

    def _add_word(self) -> None:
        if self.store.add_word(self._word_input.text()):
            self.refresh_dictionary()
        self._word_input.clear()

    def refresh_dictionary(self) -> None:
        while self._words_box.count():
            item = self._words_box.takeAt(0)
            if item.widget():
                item.widget().hide()   # deleteLater waits for the event loop: keep it out of sight meanwhile
                item.widget().deleteLater()
        words = self.store.words()
        if not words:
            self._words_box.addWidget(_label(
                tr("The dictionary is empty. Add the words dictation tends to get wrong."),
                "empty", wrap=True))
        for word in words:
            chip = QFrame()
            chip.setObjectName("chip")
            row = QHBoxLayout(chip)
            row.setContentsMargins(14, 7, 8, 7)
            label = QLabel(word)
            label.setTextFormat(Qt.PlainText)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            row.addWidget(label, 1)
            remove = QPushButton(tr("Remove"))
            remove.setObjectName("linkDanger")
            remove.setCursor(Qt.PointingHandCursor)
            remove.clicked.connect(lambda _c=False, w=word: self._remove_word(w))
            row.addWidget(remove)
            self._words_box.addWidget(chip)
        self._words_box.addStretch()

    def _remove_word(self, word: str) -> None:
        self.store.remove_word(word)
        self.refresh_dictionary()

    # -- settings --------------------------------------------------------
    def _build_settings(self) -> QWidget:
        page, box = self._page(tr("Settings"), tr("Changes are saved right away."))
        host = QWidget()
        inner = QVBoxLayout(host)
        inner.setContentsMargins(0, 0, 12, 28)
        inner.setSpacing(10)

        inner.addWidget(_label(tr("DICTATION"), "section"))
        card = self._card(inner)
        self._hotkey_button = QPushButton(self.hotkey_name)
        self._hotkey_button.setCursor(Qt.PointingHandCursor)
        self._hotkey_button.setMinimumWidth(150)
        self._hotkey_button.setEnabled(CAN_CAPTURE)
        self._hotkey_button.clicked.connect(self._capture_hotkey)
        self._setting(card, tr("Dictation shortcut"),
                      tr("A single key or a combination, such as Option + 1 or Control + Command. "
                         "The key keeps doing its normal job too.") if IS_MAC else
                      tr("A single key or a combination, such as Alt + 1 or Ctrl + Win. "
                         "The key keeps doing its normal job too."),
                      self._hotkey_button)
        mic = Combo()
        mic.addItem(tr("System default"), "")
        for name in audio.input_devices():
            mic.addItem(name, name)
        mic.setCurrentIndex(max(0, mic.findData(self.store.get("mic_device"))))
        mic.currentIndexChanged.connect(lambda _i: self.store.set("mic_device", mic.currentData()))
        self._setting(card, tr("Microphone"), "", mic)
        lang = Combo()
        for code, name in config.LANGUAGES:
            lang.addItem(tr(name), code)
        lang.setCurrentIndex(max(0, lang.findData(self.store.get("language"))))
        lang.currentIndexChanged.connect(lambda _i: self.store.set("language", lang.currentData()))
        self._setting(card, tr("Dictation language"),
                      tr("Setting the language avoids mistakes in very short dictations."), lang)
        self._toggle(card, "auto_paste", tr("Type where the cursor is"),
                     tr("If you turn this off, dictations are only saved to the history."))
        self._toggle(card, "live_typing", tr("Type as I speak"),
                     tr("Text appears while you speak, a second or two behind. In exchange, only filler "
                        "words are removed: no polishing with Claude and no self-corrections applied."))
        self._toggle(card, "trailing_space", tr("Add a trailing space"),
                     tr("So consecutive dictations don't run together."))
        self._toggle(card, "sounds", tr("Sounds"), tr("A short cue when dictation starts and ends."))
        sound_set = Combo()
        for code, name in sounds.SETS:
            sound_set.addItem(tr(name), code)
        sound_set.setCurrentIndex(max(0, sound_set.findData(self.store.get("sound_set"))))

        def choose_sound(_index: int) -> None:
            # Choosing one plays its start/stop pair, to compare by ear.
            code = sound_set.currentData()
            self.store.set("sound_set", code)
            sounds.play("start", code)
            QTimer.singleShot(750, self, lambda: sounds.play("stop", code))

        sound_set.currentIndexChanged.connect(choose_sound)
        self._setting(card, tr("Sound style"), tr("Choosing one plays its start and end sounds."),
                      sound_set, last=True)

        inner.addSpacing(12)
        inner.addWidget(_label(tr("ON-SCREEN INDICATOR"), "section"))
        card = self._card(inner)
        self._hud_always = self._toggle(
            card, "hud_always", tr("Always show it"),
            tr("If you turn this off, it only appears while you dictate. Its × button also closes it."),
            signal=self.hudChanged)
        position = self._position_combo = Combo()
        for code, name in config.HUD_POSITIONS:
            position.addItem(tr(name), code)
        position.setCurrentIndex(max(0, position.findData(self.store.get("hud_position"))))
        position.currentIndexChanged.connect(
            lambda _i: (self.store.set("hud_position", position.currentData()), self.hudChanged.emit()))
        self._setting(card, tr("Position"), tr("You can also drag the indicator with the mouse and drop "
                                               "it in one of the four slots."), position, last=True)

        inner.addSpacing(12)
        inner.addWidget(_label(tr("TEXT CLEANUP"), "section"))
        card = self._card(inner)
        self._toggle(card, "llm_enabled", tr("Polish with Claude"),
                     tr("Removes rambling and self-corrections and improves punctuation. Only the text "
                        "is sent, never the audio. Without a key, the local rules are used."))
        key_box = QVBoxLayout()
        key_box.setContentsMargins(18, 14, 18, 16)
        key_box.setSpacing(8)
        key_box.addWidget(_label(tr("Anthropic API key"), "settingLabel"))
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.Password)
        self._key_input.setPlaceholderText("sk-ant-…")
        self._key_input.returnPressed.connect(self._save_key)
        save = QPushButton(tr("Save"))
        save.setObjectName("primary")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save_key)
        self._key_remove = QPushButton(tr("Remove"))
        self._key_remove.setCursor(Qt.PointingHandCursor)
        self._key_remove.clicked.connect(self._remove_key)
        key_row.addWidget(self._key_input, 1)
        key_row.addWidget(save)
        key_row.addWidget(self._key_remove)
        key_box.addLayout(key_row)
        self._key_status = _label("", "settingHelp", wrap=True)
        key_box.addWidget(self._key_status)
        card.addLayout(key_box)
        self._refresh_key_status()

        inner.addSpacing(12)
        inner.addWidget(_label(tr("PRIVACY AND SYSTEM"), "section"))
        card = self._card(inner)
        ui_lang = self._ui_language_combo = Combo()
        for code, name in config.UI_LANGUAGES:
            # Each language is listed under its own name; only "Same as Windows" is translated.
            ui_lang.addItem(name if code else tr(name), code)
        ui_lang.setCurrentIndex(max(0, ui_lang.findData(self.store.get("ui_language"))))
        ui_lang.currentIndexChanged.connect(
            lambda _i: (self.store.set("ui_language", ui_lang.currentData()), self.languageChanged.emit()))
        self._setting(card, tr("Interface language"), "", ui_lang)
        self._toggle(card, "keep_raw", tr("Also keep the original transcription"),
                     tr("By default only the cleaned text is saved."),
                     last=not CAN_CAPTURE)
        if CAN_CAPTURE:
            start = Toggle(autostart.is_enabled())
            start.toggled.connect(autostart.set_enabled)
            if IS_MAC:
                self._setting(card, tr("Open at login"), tr("Starts hidden in the menu bar."), start, last=True)
            else:
                self._setting(card, tr("Open when Windows starts"), tr("Starts hidden in the system tray."),
                              start, last=True)

        inner.addSpacing(8)
        self._settings_hint = _label("", "hint", wrap=True)
        inner.addWidget(self._settings_hint)
        self.set_hotkey_name(self.hotkey_name)
        inner.addStretch()
        self._settings_scroll = _scroll(host)
        box.addWidget(self._settings_scroll, 1)
        return page

    def _card(self, parent: QVBoxLayout) -> QVBoxLayout:
        card = QFrame()
        card.setObjectName("card")
        box = QVBoxLayout(card)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        parent.addWidget(card)
        return box

    def _setting(self, card: QVBoxLayout, title: str, help_text: str, control: QWidget,
                 last: bool = False) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(18, 13, 18, 13)
        row.setSpacing(18)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(_label(title, "settingLabel"))
        if help_text:
            texts.addWidget(_label(help_text, "settingHelp", wrap=True))
        row.addLayout(texts, 1)
        control.setAccessibleName(title)
        row.addWidget(control, 0, Qt.AlignVCenter)
        card.addLayout(row)
        if not last:
            line = QFrame()
            line.setFixedHeight(1)
            line.setObjectName("separator")
            card.addWidget(line)

    def _toggle(self, card: QVBoxLayout, key: str, title: str, help_text: str,
                last: bool = False, signal=None) -> Toggle:
        box = Toggle(self.store.get_bool(key))
        box.toggled.connect(lambda checked, k=key: self.store.set(k, checked))
        if signal is not None:
            box.toggled.connect(lambda _checked: signal.emit())
        self._setting(card, title, help_text, box, last)
        return box

    def settings_scroll(self) -> int:
        return self._settings_scroll.verticalScrollBar().value()

    def set_settings_scroll(self, value: int) -> None:
        self._settings_scroll.verticalScrollBar().setValue(value)

    def set_hud_always(self, value: bool) -> None:
        self._hud_always.setChecked(value)

    def sync_hud_position(self, code: str) -> None:
        """The indicator was moved by dragging it: reflect that without notifying again."""
        self._position_combo.blockSignals(True)
        self._position_combo.setCurrentIndex(max(0, self._position_combo.findData(code)))
        self._position_combo.blockSignals(False)

    def _capture_hotkey(self) -> None:
        self._hotkey_button.setText(tr("Press the shortcut…"))
        self._hotkey_button.setEnabled(False)
        self.hotkeyCaptureRequested.emit()

    def set_hotkey_name(self, name: str) -> None:
        """Updates every text that names the shortcut (also when the capture is cancelled)."""
        self.hotkey_name = name
        self._hotkey_button.setText(name)
        self._hotkey_button.setEnabled(CAN_CAPTURE)
        self._history_subtitle.setText(
            tr("Hold {key} to dictate. Press it twice in a row to dictate hands-free.", key=name))
        self._settings_hint.setText(tr("Esc cancels a dictation in progress."))
        if getattr(self, "_history_empty", True):   # only the empty-list text names the shortcut
            self.refresh_history()

    def _refresh_key_status(self) -> None:
        has_key = bool(config.get_api_key())
        self._key_remove.setVisible(has_key)
        self._key_status.setText(
            (tr("A key is saved in the macOS Keychain.") if IS_MAC
             else tr("A key is saved in Windows Credential Manager."))
            if has_key else
            tr("No key. Create one at console.anthropic.com and paste it here."))

    def _save_key(self) -> None:
        key = self._key_input.text().strip()
        if not key:
            return
        try:
            config.set_api_key(key)
        except Exception as exc:
            self._key_status.setText(tr("Couldn't save the key: {error}", error=exc))
            return
        self._key_input.clear()
        self._refresh_key_status()
        self.apiKeyChanged.emit()

    def _remove_key(self) -> None:
        config.set_api_key("")
        self._refresh_key_status()
        self.apiKeyChanged.emit()

    # -- window ----------------------------------------------------------
    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self.hotkeyCaptureAbandoned.emit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if getattr(self, "_history_dirty", False):
            self.refresh_history()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.hotkeyCaptureAbandoned.emit()

    def closeEvent(self, event) -> None:
        # Closing the window does not quit the app: it stays in the tray so dictation keeps working.
        if self.quitting:   # the app itself is closing (Cmd+Q on macOS): do not stand in the way
            event.accept()
            return
        event.ignore()
        self.hide()

    def bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
