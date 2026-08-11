from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent


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


def test_crop_single_click_outside_does_not_confirm() -> None:
    from aimatting.ui.image_view import ImageView

    view = ImageView()
    view.set_pil_image(Image.new("RGB", (100, 60), "red"))
    view.resize(400, 300)
    view.set_crop_mode(True)
    got = []
    view.cropConfirmed.connect(lambda: got.append(True))

    # 图片外单击不再确认
    outside_view = view.mapFromScene(QPointF(150, 80))
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(outside_view),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(press)
    assert not got

    # 图片内双击确认
    center_view = view.mapFromScene(QPointF(50, 30))
    dblclick = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        QPointF(center_view),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseDoubleClickEvent(dblclick)
    assert got
