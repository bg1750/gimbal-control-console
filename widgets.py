# Instrument widgets drawn with QPainter: an artificial horizon and a pan
# compass. No image files needed.

import math

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QConicalGradient
from PyQt6.QtWidgets import QWidget


_SKY = QColor(110, 134, 156)
_GROUND = QColor(150, 108, 70)
_ACCENT = QColor(190, 120, 170)
_INK = QColor(34, 28, 24)
_LINE = QColor(240, 236, 228)


class AttitudeIndicator(QWidget):
    # Artificial horizon: live pitch and roll.

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pitch = 0.0
        self.roll = 0.0
        self.setMinimumSize(260, 260)

    def set_attitude(self, pitch, roll):
        self.pitch = pitch
        self.roll = roll
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height())
        cx, cy = self.width() / 2.0, self.height() / 2.0
        radius = side / 2.0 - 8

        # Clip to the round bezel.
        p.save()
        path_rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        from PyQt6.QtGui import QRegion
        p.setClipRegion(QRegion(path_rect.toRect(), QRegion.RegionType.Ellipse))

        # Roll the view, then shift by pitch, and paint sky/ground.
        p.translate(cx, cy)
        p.rotate(-self.roll)
        pitch_px = self.pitch * (radius / 45.0)  # 45 deg = rim
        p.translate(0, pitch_px)

        big = radius * 3
        p.fillRect(QRectF(-big, -big, big * 2, big), _SKY)
        p.fillRect(QRectF(-big, 0, big * 2, big), _GROUND)

        # Horizon line.
        pen = QPen(_LINE, 2)
        p.setPen(pen)
        p.drawLine(QPointF(-big, 0), QPointF(big, 0))

        # Pitch ladder every 10 degrees.
        p.setFont(QFont("Consolas", 8))
        for deg in range(-40, 41, 10):
            if deg == 0:
                continue
            y = -deg * (radius / 45.0)
            w = radius * (0.42 if deg % 20 == 0 else 0.24)
            p.drawLine(QPointF(-w, y), QPointF(w, y))
            if deg % 20 == 0:
                p.drawText(QRectF(-w - 34, y - 8, 28, 16),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           str(abs(deg)))
        p.restore()

        # Bezel ring.
        p.setPen(QPen(_INK, 10))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), radius, radius)
        p.setPen(QPen(_ACCENT, 2))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Roll scale ticks around the top arc.
        p.save()
        p.translate(cx, cy)
        p.setPen(QPen(_LINE, 2))
        for deg in (-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60):
            p.save()
            p.rotate(deg)
            length = 12 if deg % 30 == 0 else 7
            p.drawLine(QPointF(0, -radius), QPointF(0, -radius + length))
            p.restore()
        p.restore()

        # Fixed aircraft reference (center wings) + roll pointer.
        p.setPen(QPen(_ACCENT, 3))
        p.drawLine(QPointF(cx - 44, cy), QPointF(cx - 14, cy))
        p.drawLine(QPointF(cx + 14, cy), QPointF(cx + 44, cy))
        p.setBrush(QBrush(_ACCENT))
        p.drawEllipse(QPointF(cx, cy), 3, 3)

        tri = QPolygonF([
            QPointF(cx, cy - radius + 2),
            QPointF(cx - 8, cy - radius + 16),
            QPointF(cx + 8, cy - radius + 16),
        ])
        # Roll pointer.
        p.save()
        p.translate(cx, cy)
        p.rotate(-self.roll)
        p.translate(-cx, -cy)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(tri)
        p.restore()
        p.end()


class HeadingCompass(QWidget):
    # Compass showing the pan heading.

    def __init__(self, parent=None):
        super().__init__(parent)
        self.heading = 0.0
        self.setMinimumSize(220, 220)

    def set_heading(self, heading):
        self.heading = heading % 360.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height())
        cx, cy = self.width() / 2.0, self.height() / 2.0
        radius = side / 2.0 - 8

        # Dial face.
        grad = QConicalGradient(cx, cy, 90)
        grad.setColorAt(0.0, QColor(46, 38, 32))
        grad.setColorAt(0.5, QColor(32, 26, 22))
        grad.setColorAt(1.0, QColor(46, 38, 32))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(_INK, 8))
        p.drawEllipse(QPointF(cx, cy), radius, radius)
        p.setPen(QPen(_ACCENT, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Turn the card so the top mark reads current heading.
        p.save()
        p.translate(cx, cy)
        p.rotate(-self.heading)
        p.setFont(QFont("Space Mono", 10, QFont.Weight.Bold))
        marks = {0: "N", 45: "", 90: "E", 135: "", 180: "S", 225: "", 270: "W", 315: ""}
        for deg in range(0, 360, 15):
            p.save()
            p.rotate(deg)
            major = deg % 45 == 0
            length = 14 if major else 7
            p.setPen(QPen(_LINE, 2 if major else 1))
            p.drawLine(QPointF(0, -radius + 6), QPointF(0, -radius + 6 + length))
            label = marks.get(deg)
            if label:
                p.setPen(QPen(_ACCENT if label == "N" else _LINE, 1))
                p.drawText(QRectF(-12, -radius + 22, 24, 18),
                           Qt.AlignmentFlag.AlignCenter, label)
            p.restore()
        p.restore()

        # Fixed lubber line + center hub.
        p.setPen(QPen(_ACCENT, 3))
        p.drawLine(QPointF(cx, cy - radius + 2), QPointF(cx, cy - radius + 20))
        p.setBrush(QBrush(_INK))
        p.setPen(QPen(_ACCENT, 2))
        p.drawEllipse(QPointF(cx, cy), 28, 28)

        # Digital heading readout in the hub.
        p.setPen(QPen(_LINE))
        p.setFont(QFont("Space Mono", 12, QFont.Weight.Bold))
        p.drawText(QRectF(cx - 30, cy - 12, 60, 24),
                   Qt.AlignmentFlag.AlignCenter, f"{int(self.heading):03d}°")
        p.end()
