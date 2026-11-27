"""Dragging the toolbar, driven offscreen with synthetic mouse events."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from overmark import config  # noqa: E402
from overmark.config import Settings  # noqa: E402
from overmark.controller import Controller  # noqa: E402
from overmark.strokes import Tool  # noqa: E402
from overmark.toolbar import Toolbar  # noqa: E402

LEFT = Qt.MouseButton.LeftButton


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def send(widget: QWidget, kind: QEvent.Type, at: QPoint) -> None:
    button = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else LEFT
    held = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else LEFT
    local = QPointF(widget.mapFromGlobal(at))
    QApplication.sendEvent(
        widget,
        QMouseEvent(kind, local, QPointF(at), button, held, Qt.KeyboardModifier.NoModifier),
    )


def drag(widget: QWidget, by: QPoint) -> None:
    start = widget.mapToGlobal(widget.rect().center())
    send(widget, QEvent.Type.MouseButtonPress, start)
    if not by.isNull():
        send(widget, QEvent.Type.MouseMove, start + by)
    send(widget, QEvent.Type.MouseButtonRelease, start + by)


def toolbar(path: Path) -> Toolbar:
    bar = Toolbar(Controller(config.load(path, path.with_name("no-sample.json")), path))
    bar.expand()
    return bar


def test_dragging_a_button_moves_and_saves_without_clicking_or_drawing(app, tmp_path) -> None:
    path = tmp_path / "config.json"
    bar = toolbar(path)
    bar.controller.set_drawing(True)
    start = bar.pos()

    drag(bar.tool_buttons[Tool.ARROW], QPoint(0, 200))

    assert bar.pos().y() == start.y() + 200
    assert bar.controller.tool is Tool.PEN  # the arrow button was not clicked
    assert not bar.controller.board.strokes
    assert not bar.dragging
    saved = config.load(path, tmp_path / "no-sample.json").toolbar_positions
    assert [point[1] for point in saved.values()] == [bar.y()]
    # Collapsed, expanded and after a restart it stays at the new spot.
    bar.collapse()
    assert bar.y() == start.y() + 200
    bar.expand()
    assert toolbar(path).pos() == bar.pos()


def test_a_press_without_a_drag_still_clicks(app, tmp_path) -> None:
    bar = toolbar(tmp_path / "config.json")
    start = bar.pos()
    drag(bar.tool_buttons[Tool.ARROW], QPoint())
    assert bar.controller.tool is Tool.ARROW
    assert bar.pos() == start
    assert bar.controller.settings.toolbar_positions == {}


def test_an_empty_part_of_the_pill_drags_and_collapse_waits(app, tmp_path) -> None:
    bar = toolbar(tmp_path / "config.json")
    start = bar.pos()
    corner = bar.mapToGlobal(QPoint(2, 2))
    send(bar, QEvent.Type.MouseButtonPress, corner)
    send(bar, QEvent.Type.MouseMove, corner + QPoint(0, 150))
    bar.collapse()  # the hover timer firing mid-drag must not resize or move the pill
    assert bar.expanded and bar.pos() == start + QPoint(0, 150)
    send(bar, QEvent.Type.MouseButtonRelease, corner + QPoint(0, 150))
    assert bar.y() == start.y() + 150


def test_saving_settings_keeps_a_later_drag(app, tmp_path) -> None:
    controller = Controller(Settings(), tmp_path / "config.json")
    draft = Settings()  # what a dialog opened before the drag holds
    controller.set_toolbar_position("layout", (40, 50))
    controller.apply_settings(draft)
    assert controller.settings.toolbar_positions == {"layout": (40, 50)}
