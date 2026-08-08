from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygon
from PySide6.QtWidgets import QWidget

from todo_buddy.ui.theme import ACCENT, OUTLINE, PAPER


class CardWidget(QWidget):
    """Paints paper behind standard Qt child controls."""

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = self.rect().adjusted(4, 4, -4, -4)
        painter.setPen(QPen(QColor(OUTLINE), 3))
        painter.setBrush(QColor(PAPER))
        painter.drawRoundedRect(card, 8, 8)

class TriangleTrim(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(11)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ACCENT))
        width = 12
        for x in range(0, self.width(), width):
            painter.drawPolygon(
                QPolygon(
                    [
                        QPoint(x, self.height()),
                        QPoint(x + width // 2, 1),
                        QPoint(x + width, self.height()),
                    ]
                )
            )


class FooterWidget(QWidget):
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(QPen(QColor(OUTLINE), 2))
        painter.setBrush(QColor(ACCENT))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
