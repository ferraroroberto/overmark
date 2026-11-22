"""The recording chip: a red dot and the elapsed time, hidden from every capture."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen, QScreen

from overmark import theme
from overmark.recording.monitors import Monitor
from overmark.toolbar import TOP_MARGIN, CaptureHidden

PADDING_X = 14
DOT = 10
HEIGHT = 36


def format_elapsed(seconds: float) -> str:
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def screen_for(monitor: Monitor | None) -> QScreen:
    """The Qt screen showing ``monitor``; Qt keeps each screen's top-left at its native
    position, so the corners match even on mixed-DPI desktops."""
    if monitor is not None:
        for screen in QGuiApplication.screens():
            top_left = screen.geometry().topLeft()
            if (top_left.x(), top_left.y()) == (monitor.x, monitor.y):
                return screen
    return QGuiApplication.primaryScreen()


class RecordingIndicator(CaptureHidden):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Overmark recording")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._paused = False
        self._text = "REC 00:00"
        self._font = QFont("Segoe UI", 11)
        self._font.setWeight(QFont.Weight.DemiBold)
        self._screen: QScreen | None = None

    def show_on(self, monitor: Monitor | None) -> None:
        self._screen = screen_for(monitor)
        self.update_time(0.0, paused=False)
        self.show()

    def update_time(self, seconds: float, *, paused: bool) -> None:
        self._paused = paused
        self._text = f"{'Paused' if paused else 'REC'} {format_elapsed(seconds)}"
        width = QFontMetrics(self._font).horizontalAdvance(self._text) + DOT + 3 * PADDING_X // 2
        self.setFixedSize(width + PADDING_X, HEIGHT)
        if self._screen is not None:
            area = self._screen.availableGeometry()
            self.move(QPoint(area.right() - self.width() - TOP_MARGIN, area.top() + TOP_MARGIN))
        self.raise_above_overlays()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        t = theme.tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(t["border"]), 1))
        painter.setBrush(QColor(t["card"]))
        painter.drawRoundedRect(rect, HEIGHT / 2, HEIGHT / 2)
        mark = QRectF(PADDING_X, (HEIGHT - DOT) / 2, DOT, DOT)
        painter.setPen(Qt.PenStyle.NoPen)
        if self._paused:
            painter.setBrush(QColor(t["fg_muted"]))
            bar = DOT / 3
            painter.drawRect(QRectF(mark.left(), mark.top(), bar, DOT))
            painter.drawRect(QRectF(mark.right() - bar, mark.top(), bar, DOT))
        else:
            painter.setBrush(QColor(t["danger"]))
            painter.drawEllipse(mark)
        painter.setPen(QColor(t["fg"]))
        painter.setFont(self._font)
        text_rect = QRectF(mark.right() + PADDING_X / 2, 0, self.width(), HEIGHT)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, self._text)
        painter.end()
