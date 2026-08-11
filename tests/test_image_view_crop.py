from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPointF, QRectF


def _view():
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    from aimatting.ui.image_view import ImageView

    return ImageView()


def test_crop_mode_defaults_to_full_image() -> None:
    view = _view()
    view.set_pil_image(Image.new("RGB", (100, 60), "red"))
    view.set_crop_mode(True)
    rect = view.crop_rect()
    assert rect is not None
    assert abs(rect.width() - 100) < 1
    assert abs(rect.height() - 60) < 1


def test_crop_clamp_and_clear() -> None:
    view = _view()
    view.set_pil_image(Image.new("RGB", (100, 60), "red"))
    view.set_crop_mode(True)
    # 模拟创建一个超出边界的选框
    view._crop_rect = QRectF(-50, -30, 300, 200)
    clamped = view._clamp_rect(view._crop_rect)
    assert clamped.left() >= 0
    assert clamped.top() >= 0
    assert clamped.right() <= 100
    assert clamped.bottom() <= 60
    view.set_crop_mode(False)
    assert view.crop_rect() is None


def test_crop_cursor_changes_over_box() -> None:
    from PySide6.QtCore import Qt

    view = _view()
    view.set_pil_image(Image.new("RGB", (100, 60), "red"))
    view.resize(400, 300)
    view.set_crop_mode(True)
    # 取场景坐标并换算为视图坐标
    center_view = view.mapFromScene(view.crop_rect().center())
    corner_view = view.mapFromScene(view.crop_rect().topLeft())
    outside_view = view.mapFromScene(QPointF(120, 80))  # 裁剪框外
    assert view._crop_cursor(center_view) == Qt.CursorShape.SizeAllCursor
    assert view._crop_cursor(corner_view) == Qt.CursorShape.SizeFDiagCursor
    assert view._crop_cursor(outside_view) == Qt.CursorShape.CrossCursor
