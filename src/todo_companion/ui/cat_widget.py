from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget

from todo_companion.ui.theme import INK


class CatState(Enum):
    AWAKE = "awake"
    SLEEPING = "sleeping"
    WAKING = "waking"
    HAPPY = "happy"
    ANGRY = "angry"


SPRITE_FRAME = 64

_SPRITE_FILES = {
    CatState.AWAKE: "AWAKE_IDLE.png",
    CatState.SLEEPING: "SLEEPING.png",
    CatState.WAKING: "WAKE_UP.png",
    CatState.HAPPY: "HAPPY.png",
    CatState.ANGRY: "ANGRY.png",
}


def sprite_directory() -> Path:
    """Locate the sprite-sheet directory in source checkouts and frozen builds."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "asset" / "cat_animation"
    return Path(__file__).resolve().parents[3] / "asset" / "cat_animation"


def load_sprite_sheets() -> dict[CatState, QPixmap]:
    """Load per-state sprite sheets; states without a valid sheet are omitted."""
    sheets: dict[CatState, QPixmap] = {}
    directory = sprite_directory()
    for state, filename in _SPRITE_FILES.items():
        path = directory / filename
        if not path.is_file():
            continue
        pixmap = QPixmap(str(path))
        if (
            pixmap.isNull()
            or pixmap.height() != SPRITE_FRAME
            or pixmap.width() < SPRITE_FRAME
            or pixmap.width() % SPRITE_FRAME
        ):
            continue
        sheets[state] = pixmap
    return sheets


class CatWidget(QWidget):
    """A small procedural cat with interaction-driven animation states."""

    def __init__(self, parent=None, inactivity_ms: int = 20_000):
        super().__init__(parent)
        self.setFixedHeight(SPRITE_FRAME)
        self.setAccessibleName("Orange companion cat")
        self.setToolTip("The companion cat reacts to your quests")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._sheets = load_sprite_sheets()
        self._state = CatState.AWAKE
        self._frame = 0

        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(220)
        self._animation_timer.timeout.connect(self._advance_frame)

        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.setSingleShot(True)
        self._inactivity_timer.setInterval(inactivity_ms)
        self._inactivity_timer.timeout.connect(self.fall_asleep)
        self._inactivity_timer.start()

        self._happy_timer = QTimer(self)
        self._happy_timer.setSingleShot(True)
        self._happy_timer.setInterval(1_800)
        self._happy_timer.timeout.connect(self._finish_happy)

    @property
    def state(self) -> CatState:
        return self._state

    def note_activity(self) -> None:
        if self._state == CatState.SLEEPING:
            # Stretch awake via the one-shot WAKE_UP sheet when it exists.
            if CatState.WAKING in self._sheets:
                self._set_state(CatState.WAKING)
            else:
                self._set_state(CatState.AWAKE)
        if self._state == CatState.AWAKE:
            self._inactivity_timer.start()

    def fall_asleep(self) -> None:
        if self._state == CatState.AWAKE:
            self._set_state(CatState.SLEEPING)

    def celebrate(self) -> None:
        self._happy_timer.start()
        self._inactivity_timer.stop()
        self._set_state(CatState.HAPPY)

    def start_angry(self) -> None:
        self._happy_timer.stop()
        self._inactivity_timer.stop()
        self._set_state(CatState.ANGRY)

    def stop_angry(self) -> None:
        if self._state == CatState.ANGRY:
            self._set_state(CatState.AWAKE)
            self._inactivity_timer.start()

    def _finish_happy(self) -> None:
        if self._state == CatState.HAPPY:
            self._set_state(CatState.AWAKE)
            self._inactivity_timer.start()

    def _set_state(self, state: CatState) -> None:
        self._state = state
        self._frame = 0
        self._animation_timer.setInterval(620 if state == CatState.SLEEPING else 220)
        if self.isVisible() and not self._animation_timer.isActive():
            self._animation_timer.start()
        self.update()

    def _advance_frame(self) -> None:
        next_frame = (self._frame + 1) % self._frame_count()
        if self._state == CatState.WAKING and next_frame == 0:
            self._set_state(CatState.AWAKE)
            self._inactivity_timer.start()
            return
        self._frame = next_frame
        self.update()

    def _frame_count(self) -> int:
        sheet = self._sheets.get(self._state)
        return sheet.width() // SPRITE_FRAME if sheet is not None else 4

    def showEvent(self, event) -> None:
        self._animation_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._animation_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        sheet = self._sheets.get(self._state)
        if sheet is not None:
            # Pixel-art path: nearest-neighbor (no smoothing hint), whole-pixel
            # placement. Motion (jumps, stretches) is baked into the sheets.
            frame = self._frame % (sheet.width() // SPRITE_FRAME)
            target = QRect(
                (self.width() - SPRITE_FRAME) // 2,
                self.height() - SPRITE_FRAME,
                SPRITE_FRAME,
                SPRITE_FRAME,
            )
            source = QRect(frame * SPRITE_FRAME, 0, SPRITE_FRAME, SPRITE_FRAME)
            painter.drawPixmap(target, sheet, source)
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2 - 42, 2)

        bounce = -2 if self._state == CatState.HAPPY and self._frame % 2 else 0
        painter.translate(0, bounce)
        orange = QColor("#E8872E")
        light_orange = QColor("#F6B45E")
        dark_orange = QColor("#B85C1E")
        ink = QColor(INK)

        painter.setPen(QPen(ink, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        tail = QPainterPath(QPointF(66, 43))
        tail_tip_y = 23 + (self._frame % 2) * 7
        if self._state == CatState.ANGRY:
            tail.lineTo(84, 15)
        else:
            tail.cubicTo(88, 46, 88, tail_tip_y, 76, tail_tip_y)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(tail)

        painter.setBrush(orange)
        painter.drawEllipse(QRectF(19, 29, 55, 27))
        painter.setBrush(light_orange)
        painter.drawEllipse(QRectF(31, 39, 31, 14))

        ear_y = 13 if self._state != CatState.ANGRY else 18
        painter.setBrush(orange)
        painter.drawPolygon(
            QPolygonF([QPointF(24, 24), QPointF(27, ear_y), QPointF(38, 22)])
        )
        painter.drawPolygon(
            QPolygonF([QPointF(50, 22), QPointF(61, ear_y), QPointF(64, 25)])
        )
        painter.drawEllipse(QRectF(23, 17, 42, 34))

        painter.setPen(QPen(dark_orange, 2))
        painter.drawLine(QPointF(44, 18), QPointF(44, 31))
        painter.setPen(QPen(ink, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

        if self._state == CatState.SLEEPING:
            painter.drawLine(QPointF(31, 32), QPointF(37, 32))
            painter.drawLine(QPointF(51, 32), QPointF(57, 32))
            painter.drawArc(QRectF(40, 35, 8, 5), 0, -180 * 16)
            painter.setPen(QPen(dark_orange, 1))
            painter.drawText(QPointF(67, 20 - (self._frame % 2) * 3), "z")
            painter.drawText(QPointF(74, 12 - (self._frame % 2) * 3), "Z")
        elif self._state == CatState.HAPPY:
            painter.drawLine(QPointF(30, 33), QPointF(34, 29))
            painter.drawLine(QPointF(34, 29), QPointF(38, 33))
            painter.drawLine(QPointF(50, 33), QPointF(54, 29))
            painter.drawLine(QPointF(54, 29), QPointF(58, 33))
            painter.drawArc(QRectF(39, 34, 10, 8), 180 * 16, 180 * 16)
            self._draw_heart(painter, QPointF(73, 11), dark_orange)
        elif self._state == CatState.ANGRY:
            painter.drawLine(QPointF(30, 27), QPointF(38, 30))
            painter.drawLine(QPointF(50, 30), QPointF(58, 27))
            painter.setBrush(ink)
            painter.drawEllipse(QRectF(33, 31, 3, 4))
            painter.drawEllipse(QRectF(52, 31, 3, 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(40, 41), QPointF(48, 41))
        else:
            blink = self._frame == 3
            if blink:
                painter.drawLine(QPointF(31, 32), QPointF(37, 32))
                painter.drawLine(QPointF(51, 32), QPointF(57, 32))
            else:
                painter.setBrush(ink)
                painter.drawEllipse(QRectF(33, 29, 4, 6))
                painter.drawEllipse(QRectF(51, 29, 4, 6))
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(40, 35, 8, 5), 0, -180 * 16)

        painter.setPen(QPen(ink, 1))
        painter.drawLine(QPointF(25, 38), QPointF(14, 35))
        painter.drawLine(QPointF(25, 41), QPointF(13, 42))
        painter.drawLine(QPointF(63, 38), QPointF(74, 35))
        painter.drawLine(QPointF(63, 41), QPointF(75, 42))

    @staticmethod
    def _draw_heart(painter: QPainter, origin: QPointF, color: QColor) -> None:
        path = QPainterPath(origin + QPointF(0, 3))
        path.cubicTo(origin + QPointF(-7, -3), origin + QPointF(-7, 7), origin)
        path.cubicTo(origin + QPointF(7, -3), origin + QPointF(7, 7), origin + QPointF(0, 3))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)
