"""Floating indicator: a small fixed-size pill. At rest it shows a few dots; while dictating,
the microphone level; notices appear in a separate caption next to it.
It never steals focus from the app being typed into.

On the left and right edges it stands vertically. Hovering it reveals two buttons:
collapse (it becomes a thin line against the edge that comes back out when the mouse
gets near) and close (it stops being always visible).
It is moved by dragging: the screen dims and the four possible slots appear."""
from __future__ import annotations

import logging
import math
import time

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..i18n import tr
from .theme import DARK

log = logging.getLogger("susurros.pill")
N_BARS = 9
SIZE = (84, 28)          # the indicator is always the same size, at rest and in use
SLIVER = 6               # thickness when collapsed against the edge
SLIVER_LOCKED = 9        # slightly thicker in hands-free, to fit the border that marks it
LOCK_ORANGE = "#ffd84a"  # yellow: stands apart from the orange of the voice and says "locked, recording"
MARGIN = 14
ATTACK_S, RELEASE_S = 0.028, 0.16   # the voice rises almost instantly and falls gently
DRAG_THRESHOLD = 8       # pixels the mouse must move before a drag starts
HOVER_PAD = 16           # slack around the indicator within which the mouse counts as "over" it
POSITIONS = ("top", "bottom", "left", "right")
_NO_FOCUS = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
_FILL = QColor(20, 19, 18, 242)


def is_vertical(position: str) -> bool:
    return position in ("left", "right")


def anchor(area: QRect, width: int, height: int, position: str, margin: int = MARGIN) -> QPoint:
    """Top left corner of a rectangle placed against the `position` edge of `area`."""
    cx = area.center().x() - width // 2
    cy = area.center().y() - height // 2
    return {
        "top": QPoint(cx, area.top() + margin),
        "left": QPoint(area.left() + margin, cy),
        "right": QPoint(area.right() + 1 - width - margin, cy),
    }.get(position, QPoint(cx, area.bottom() + 1 - height - margin))


class DropOverlay(QWidget):
    """Dims the screen and draws the four slots while the indicator is being dragged."""

    def __init__(self):
        super().__init__(None, _NO_FOCUS | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.active = "bottom"
        self._area = QRect()

    def open(self, screen) -> None:
        self.setGeometry(screen.geometry())
        self._area = screen.availableGeometry().translated(-screen.geometry().topLeft())
        self.show()

    def slot_rect(self, position: str) -> QRectF:
        w, h = SIZE[0] + 20, SIZE[1] + 14
        if is_vertical(position):
            w, h = h, w
        corner = anchor(self._area, w, h, position)
        return QRectF(corner.x(), corner.y(), w, h)

    def nearest(self, global_pos: QPoint) -> str:
        local = global_pos - self.geometry().topLeft()
        return min(POSITIONS, key=lambda pos: (self.slot_rect(pos).center().toPoint() - local).manhattanLength())

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 150))
        for position in POSITIONS:
            rect = self.slot_rect(position)
            radius = min(rect.width(), rect.height()) / 2
            if position == self.active:
                p.setPen(QPen(QColor(DARK["ACCENT"]), 2))
                fill = QColor(DARK["ACCENT"])
                fill.setAlpha(60)
                p.setBrush(fill)
            else:
                p.setPen(QPen(QColor(255, 255, 255, 130), 1.5, Qt.DashLine))
                p.setBrush(QColor(255, 255, 255, 18))
            p.drawRoundedRect(rect, radius, radius)
        p.end()


class Caption(QWidget):
    """Short caption next to the indicator (notices and the hands-free hint)."""

    def __init__(self):
        super().__init__(None, _NO_FOCUS | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.text = ""
        self._font = QFont()
        self._font.setPixelSize(12)

    def show_text(self, text: str, pill: QRect, position: str) -> None:
        self.text = text
        width = QFontMetrics(self._font).horizontalAdvance(text) + 26
        height, gap = 28, 8
        self.resize(width, height)
        cx = pill.center().x() - width // 2
        cy = pill.center().y() - height // 2
        self.move({
            "top": QPoint(cx, pill.bottom() + gap),
            "left": QPoint(pill.right() + gap, cy),
            "right": QPoint(pill.left() - gap - width, cy),
        }.get(position, QPoint(cx, pill.top() - gap - height)))
        self.show()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 34), 1))
        p.setBrush(_FILL)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 9, 9)
        p.setPen(QColor(DARK["TEXT"]))
        p.setFont(self._font)
        p.drawText(self.rect(), Qt.AlignCenter, self.text)
        p.end()


class Controls(QWidget):
    """Two buttons that appear next to the indicator on hover: collapse and close."""
    collapseClicked = Signal()
    closeClicked = Signal()
    BUTTON, GAP = 22, 4

    def __init__(self):
        super().__init__(None, _NO_FOCUS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.position = "bottom"
        self.collapsed = False
        self._hot = -1

    def place(self, pill: QRect, position: str, collapsed: bool) -> None:
        self.position, self.collapsed = position, collapsed
        long, short = self.BUTTON * 2 + self.GAP, self.BUTTON
        if is_vertical(position):   # below the indicator
            self.setFixedSize(short, long)
            self.move(pill.center().x() - short // 2, pill.bottom() + 7)
        else:                       # to its right
            self.setFixedSize(long, short)
            self.move(pill.right() + 7, pill.center().y() - short // 2)
        self.show()
        self.update()

    def _button_at(self, pos) -> int:
        along = pos.y() if is_vertical(self.position) else pos.x()
        return 0 if along < self.BUTTON + self.GAP / 2 else 1

    def _button_rect(self, index: int) -> QRectF:
        offset = index * (self.BUTTON + self.GAP)
        if is_vertical(self.position):
            return QRectF(0, offset, self.BUTTON, self.BUTTON)
        return QRectF(offset, 0, self.BUTTON, self.BUTTON)

    def mouseMoveEvent(self, event) -> None:
        hot = self._button_at(event.position())
        if hot != self._hot:
            self._hot = hot
            self.setToolTip((tr("Expand") if self.collapsed else tr("Collapse against the edge")) if hot == 0
                            else tr("Hide the indicator"))
            self.update()

    def leaveEvent(self, _event) -> None:
        self._hot = -1
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            (self.collapseClicked if self._button_at(event.position()) == 0 else self.closeClicked).emit()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for index in (0, 1):
            rect = self._button_rect(index).adjusted(0.5, 0.5, -0.5, -0.5)
            p.setPen(QPen(QColor(255, 255, 255, 70 if index == self._hot else 40), 1))
            p.setBrush(QColor(52, 49, 45, 250) if index == self._hot else _FILL)
            p.drawEllipse(rect)
            p.setPen(QPen(QColor(DARK["TEXT"]), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            c = rect.center()
            if index == 1:    # close: a cross
                p.drawLine(c + QPointF(-3.5, -3.5), c + QPointF(3.5, 3.5))
                p.drawLine(c + QPointF(-3.5, 3.5), c + QPointF(3.5, -3.5))
                continue
            # Collapse: an arrow towards the edge it hides against (inwards if already collapsed).
            angle = {"bottom": 0, "left": 90, "top": 180, "right": 270}[self.position]
            p.save()
            p.translate(c)
            p.rotate(angle + (180 if self.collapsed else 0))
            p.drawPolyline([QPointF(-4, -2), QPointF(0, 2.5), QPointF(4, -2)])
            p.restore()
        p.end()


class Pill(QWidget):
    positionChosen = Signal(str)
    collapsedChanged = Signal(bool)
    closeRequested = Signal()

    def __init__(self):
        super().__init__(None, _NO_FOCUS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.state = "hidden"   # hidden | idle | recording | locked | processing
        self.position = "bottom"
        self.always = True
        self.collapsed = False
        self.mic_ok = True
        self.hotkey_name = "Caps Lock"   # the controller sets it in the interface language
        self._level = 0.0               # smoothed voice level (what gets drawn)
        self._bars = [0.0] * N_BARS     # smoothed height of each bar
        self._last_frame = 0.0
        self._target = 0.0
        # One frame per screen refresh (144 Hz included); motion is computed from elapsed
        # time, so it is just as smooth at 60 as at 240 Hz.
        self._tick = QTimer(self, timeout=self._animate)
        self._tick.setTimerType(Qt.PreciseTimer)
        self._caption = Caption()
        self._caption_timer = QTimer(self, singleShot=True, timeout=self._caption_done)
        self._controls = Controls()
        self._controls.collapseClicked.connect(self._toggle_collapsed)
        self._controls.closeClicked.connect(self._close)
        self._hover = False
        self._hover_blocked = False   # after collapsing: the mouse must leave before it peeks out again
        self._press_pos: QPoint | None = None
        self._misses = 0
        self._hover_timer = QTimer(self, interval=33, timeout=self._poll_hover)
        self._overlay = DropOverlay()
        self._dragging = False
        self._screen = None
        app = QGuiApplication.instance()
        app.screenRemoved.connect(self._on_screens_changed)
        app.primaryScreenChanged.connect(self._on_screens_changed)
        self._layout()

    # -- API -------------------------------------------------------------
    def configure(self, position: str, always: bool, collapsed: bool | None = None) -> None:
        self.position = position if position in POSITIONS else "bottom"
        self.always = always
        if collapsed is not None:
            self.collapsed = collapsed
        if self.state in ("hidden", "idle"):
            self.hide_pill()
        else:
            self._layout()

    def show_recording(self) -> None:
        self._level, self._bars = 0.0, [0.0] * N_BARS
        self._set("recording")

    def show_locked(self) -> None:
        self._set("locked")
        self._say(tr("Hands-free · double {key} to finish", key=self.hotkey_name), 2400)

    def show_processing(self) -> None:
        self._set("processing")

    def show_message(self, text: str, ms: int = 1500, rest: bool = True) -> None:
        """Short notice in the caption. With `rest` the indicator goes back to its resting look
        right away; without it the state is kept (the caller knows whether a dictation is still
        in progress)."""
        if rest:
            self._set("idle")
        self._say(text, ms)

    def hide_pill(self) -> None:
        """Back to rest: visible if it is always on screen, hidden otherwise."""
        self._tick.stop()
        if self.always or self._caption.isVisible():
            self._set("idle", keep_caption=True)
        else:
            self._really_hide()

    def _close(self) -> None:
        """× button: it stops being always visible. It hides now, even if the setting was already off."""
        self.always = False
        self._caption_timer.stop()
        self._caption.hide()
        self._really_hide()
        self.closeRequested.emit()

    def set_level(self, level: float) -> None:
        self._target = level

    # -- internal --------------------------------------------------------
    @property
    def _sliver(self) -> bool:
        """Collapsed against the edge (except while the mouse makes it peek out)."""
        return self.collapsed and not (self._hover and self.state == "idle")

    def _really_hide(self) -> None:
        self.state = "hidden"
        self._hover = False
        self._hover_timer.stop()
        self._controls.hide()
        self.hide()

    def _say(self, text: str, ms: int) -> None:
        self._caption.show_text(text, self.geometry(), self.position)
        self._caption_timer.start(ms)

    def _caption_done(self) -> None:
        self._caption.hide()
        if self.state == "idle" and not self.always:
            self._really_hide()

    def _set(self, state: str, keep_caption: bool = False) -> None:
        self._end_drag(apply=False)
        if not keep_caption:
            self._caption_timer.stop()
            self._caption.hide()
        was_resting, was_hidden = self.state in ("hidden", "idle"), self.state == "hidden"
        self.state = state
        if was_hidden or (state != "idle" and was_resting):
            # When it appears or becomes active, it does so on the screen where the cursor is.
            self._screen = QGuiApplication.screenAt(QCursor.pos())
        self._layout()
        if state == "idle":
            self._tick.stop()
        elif not self._tick.isActive():
            rate = min(240.0, max(60.0, self._current_screen().refreshRate() or 60.0))
            self._last_frame = time.monotonic()
            self._tick.start(max(4, round(1000 / rate)))
            log.info("Indicator animation at %.0f Hz", rate)
        if not self._hover_timer.isActive():
            self._hover_timer.start()
        self.show()
        self.update()

    def _current_screen(self):
        if self._screen is not None and self._screen not in QGuiApplication.screens():
            self._screen = None   # the monitor is no longer connected
        return self._screen or QGuiApplication.primaryScreen()

    def _on_screens_changed(self, *_args) -> None:
        self._screen = None
        if self.state != "hidden":
            self._layout()

    def _layout(self) -> None:
        """Size and place according to the edge, whether it is collapsed and whether the mouse is over it."""
        vertical = is_vertical(self.position)
        if self._sliver:
            thick = SLIVER_LOCKED if self.state == "locked" else SLIVER
            size, margin = ((thick, SIZE[0]) if vertical else (SIZE[0], thick)), 0
        else:
            size, margin = ((SIZE[1], SIZE[0]) if vertical else SIZE), MARGIN
        self.setFixedSize(*size)
        if not self._dragging:
            self.move(anchor(self._current_screen().availableGeometry(), *size, self.position, margin))
        self.setCursor(Qt.OpenHandCursor if self.state == "idle" and not self._sliver else Qt.ArrowCursor)
        if self._hover and self.state == "idle" and not self._dragging:
            self._controls.place(self.geometry(), self.position, self.collapsed)
        else:
            self._controls.hide()
        if self._caption.isVisible():   # the caption follows the indicator when it moves or changes size
            self._caption.show_text(self._caption.text, self.geometry(), self.position)
        self.update()

    def _poll_hover(self) -> None:
        if self._dragging:
            # If the release was missed (session lock, UAC prompt), do not leave the screen dimmed.
            if not QGuiApplication.mouseButtons() & Qt.LeftButton:
                self._end_drag(apply=False)
            return
        zone = self.geometry()
        if self._controls.isVisible():
            zone = zone.united(self._controls.geometry())
        if self._sliver:   # collapsed: getting near the edge is enough
            zone = zone.united(QRect(anchor(self._current_screen().availableGeometry(),
                                            *self._expanded_size(), self.position),
                                     QSize(*self._expanded_size())))
        over = self.state == "idle" and zone.adjusted(-HOVER_PAD, -HOVER_PAD, HOVER_PAD, HOVER_PAD) \
            .contains(QCursor.pos())
        if self._hover_blocked:
            self._hover_blocked = over
            return
        self._misses = 0 if over else self._misses + 1
        if over != self._hover and (over or self._misses >= 8):   # it leaves after a short delay (~¼ s)
            self._hover = over
            self._layout()

    def _expanded_size(self) -> tuple[int, int]:
        return (SIZE[1], SIZE[0]) if is_vertical(self.position) else SIZE

    def _toggle_collapsed(self) -> None:
        self.collapsed = not self.collapsed
        self._hover = False   # it collapses (or stays out) now, without waiting for the mouse to leave
        self._hover_blocked = self.collapsed   # and does not peek out again until the mouse moves away
        self._misses = 0
        self._layout()
        self.collapsedChanged.emit(self.collapsed)

    def _animate(self) -> None:
        now = time.monotonic()
        dt = min(0.05, now - self._last_frame)   # capped: no jump after a stall
        self._last_frame = now
        if self.state in ("recording", "locked"):
            self._level = self._approach(self._level, self._target, dt)
            for i in range(N_BARS):
                # The middle bars weigh more and each one breathes at its own pace: it looks like
                # a living wave rather than nine identical bars.
                weight = 0.5 + 0.5 * math.sin(math.pi * (i + 0.5) / N_BARS)
                breath = 0.66 + 0.34 * math.sin(now * (6.0 + 0.9 * i) + i * 1.9)
                self._bars[i] = self._approach(self._bars[i], self._target * weight * breath, dt)
        self.update()

    @staticmethod
    def _approach(value: float, target: float, dt: float) -> float:
        """Time-based exponential smoothing: the same motion at any refresh rate."""
        tau = ATTACK_S if target > value else RELEASE_S
        return value + (target - value) * (1 - math.exp(-dt / tau))

    # -- drag to reposition -----------------------------------------------
    def mousePressEvent(self, event) -> None:
        if self.state == "idle" and not self._sliver and event.button() == Qt.LeftButton:
            self._press_pos = event.globalPosition().toPoint()

    def _begin_drag(self, pos: QPoint) -> None:
        self._dragging = True
        self._controls.hide()
        self._screen = QGuiApplication.screenAt(pos) or self._current_screen()
        self._overlay.active = self.position
        self._overlay.open(self._screen)
        self.raise_()
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        pos = event.globalPosition().toPoint()
        if not self._dragging:
            # A click without moving the mouse is not a drag: it does not dim the screen.
            if self._press_pos is None or (pos - self._press_pos).manhattanLength() < DRAG_THRESHOLD:
                return
            self._begin_drag(pos)
        self.move(pos - QPoint(self.width() // 2, self.height() // 2))
        nearest = self._overlay.nearest(pos)
        if nearest != self._overlay.active:
            self._overlay.active = nearest
            self._overlay.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press_pos = None
            if self._dragging:
                self._end_drag(apply=True)

    def _end_drag(self, apply: bool) -> None:
        self._press_pos = None
        if not self._dragging:
            return
        self._dragging = False
        self._overlay.hide()
        if apply and self._overlay.active != self.position:
            self.position = self._overlay.active
            self.positionChosen.emit(self.position)
        self._layout()

    # -- painting --------------------------------------------------------
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        active = self.state in ("recording", "locked", "processing")
        if self._sliver:
            self._paint_sliver(p, active)
            p.end()
            return

        if is_vertical(self.position):   # same drawing, rotated: the bars end up stacked
            p.translate(self.width(), 0)
            p.rotate(90)
        width, height = SIZE
        rect = QRectF(0.75, 0.75, width - 1.5, height - 1.5)
        if self.state == "locked":   # hands-free: orange border for as long as it lasts
            p.setPen(QPen(QColor(DARK["ACCENT"]), 1.5))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 44), 1))
        p.setBrush(_FILL)
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.setPen(Qt.NoPen)
        cx, cy = width / 2, height / 2

        if self.state in ("recording", "locked"):
            p.setBrush(QColor(DARK["ACCENT"]))
            x = cx - (N_BARS * 3 + (N_BARS - 1) * 3) / 2
            for i, level in enumerate(self._bars):
                h = 3 + 14 * min(1.0, level)
                p.drawRoundedRect(QRectF(x + i * 6, cy - h / 2, 3, h), 1.5, 1.5)
        elif self.state == "processing":
            now = time.monotonic()
            for i in range(3):
                phase = (math.sin(now * 5.5 - i * 0.9) + 1) / 2
                color = QColor(DARK["ACCENT"])
                color.setAlphaF(0.3 + 0.7 * phase)
                p.setBrush(color)
                radius = 2.4 + 0.7 * phase
                p.drawEllipse(QRectF(cx + (i - 1) * 11 - radius, cy - radius, radius * 2, radius * 2))
        else:
            # At rest: faint orange dots, red if there is no microphone.
            color = QColor(DARK["ACCENT"] if self.mic_ok else DARK["DANGER"])
            color.setAlphaF(0.55 if self.mic_ok else 1.0)
            p.setBrush(color)
            for i in range(5):
                p.drawEllipse(QRectF(cx + (i - 2) * 8 - 1.75, cy - 1.75, 3.5, 3.5))
        p.end()

    def _paint_sliver(self, p: QPainter, active: bool) -> None:
        """Collapsed: a thin line. While dictating it is a meter: a bright orange stretch that grows
        from the centre with the voice over a faint orange track, to show that it is listening."""
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        radius = min(rect.width(), rect.height()) / 2
        if self.state == "locked":
            # Hands-free: an intense border surrounds the line for as long as it stays locked;
            # the voice meter is drawn inside.
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(LOCK_ORANGE))
            p.drawRoundedRect(rect, radius, radius)
            rect = rect.adjusted(2, 2, -2, -2)
            radius = min(rect.width(), rect.height()) / 2
        if not active:
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.setBrush(QColor(DARK["DANGER"]) if not self.mic_ok else QColor(70, 66, 61, 245))
            p.drawRoundedRect(rect, radius, radius)
            return
        p.setPen(Qt.NoPen)
        track = QColor(DARK["ACCENT"])
        if self.state == "processing":   # transcribing: the whole line pulses
            track.setAlphaF(0.45 + 0.55 * (math.sin(time.monotonic() * 5.5) + 1) / 2)
            p.setBrush(track)
            p.drawRoundedRect(rect, radius, radius)
            return
        p.setBrush(QColor(58, 44, 30, 245))                 # track: dull orange
        p.drawRoundedRect(rect, radius, radius)
        level = min(1.0, self._level)
        share = 0.12 + 0.88 * level                          # in silence a central dot remains
        p.setBrush(track)
        if is_vertical(self.position):
            length = rect.height() * share
            p.drawRoundedRect(QRectF(rect.x(), rect.center().y() - length / 2, rect.width(), length),
                              radius, radius)
        else:
            length = rect.width() * share
            p.drawRoundedRect(QRectF(rect.center().x() - length / 2, rect.y(), length, rect.height()),
                              radius, radius)
