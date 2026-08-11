from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QWheelEvent


def _view():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from aimatting.ui.image_view import ImageView

    view = ImageView()
    view.set_pil_image(Image.new("RGB", (100, 60), "red"))
    view.set_brush_active(True)
    view.set_brush_cursor(60, 0.8)
    return view


def _wheel(delta_y: int, ctrl: bool = False) -> QWheelEvent:
    mods = (
        Qt.KeyboardModifier.ControlModifier
        if ctrl
        else Qt.KeyboardModifier.NoModifier
    )
    return QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, delta_y),
        Qt.MouseButton.NoButton,
        mods,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )


def test_wheel_resizes_brush_and_ctrl_zooms() -> None:
    view = _view()
    size = view._brush_size
    got = []
    view.brushSizeChanged.connect(got.append)
    view.wheelEvent(_wheel(120))
    assert got and got[-1] == size + 5
    before = view._zoom
    view.wheelEvent(_wheel(120, ctrl=True))
    assert abs(view._zoom - before * 1.15) < 1e-6


def test_enter_emits_tool_action() -> None:
    view = _view()
    got = []
    view.toolActionRequested.connect(lambda: got.append(True))
    ev = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
    )
    view.keyPressEvent(ev)
    assert got


def test_crop_blank_click_confirms() -> None:
    from aimatting.ui.image_view import ImageView

    view = ImageView()
    view.set_pil_image(Image.new("RGB", (100, 60), "red"))
    view.set_crop_mode(True)
    assert view._crop_click_outside_image(QPointF(150, 80)) is True
    assert view._crop_click_outside_image(QPointF(50, 30)) is False
