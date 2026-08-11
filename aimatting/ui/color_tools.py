"""颜色选择辅助：以独立窗口弹出 qfluentwidgets 取色对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget
from qfluentwidgets import ColorDialog


_CONTENT_W = 488
_CONTENT_H = 696
_MARGIN = 24  # 为卡片阴影留出的边距


def run_color_dialog(parent: QWidget, initial, title: str, on_color) -> None:
    """弹出颜色对话框：独立小窗，居中于主窗口，不改变主窗口尺寸。

    qfluentwidgets 的 ColorDialog 默认是铺满父窗口的遮罩对话框（跟随父窗口
    尺寸），旧实现通过临时放大父窗口来容纳内容，导致主窗口被“憋大”。这里
    在创建后把对话框从父窗口拆出，变成位于主窗口中央的独立小窗。
    """
    dialog = ColorDialog(initial, title, parent)
    host = dialog.window()

    content_w = _CONTENT_W
    content_h = _CONTENT_H + (40 if dialog.enableAlpha else 0)
    w = content_w + _MARGIN * 2
    h = content_h + _MARGIN * 2

    center = parent.mapToGlobal(parent.rect().center())
    x = center.x() - w // 2
    y = center.y() - h // 2
    screen = parent.screen()
    if screen is not None:
        avail = screen.availableGeometry()
        x = max(avail.left(), min(x, avail.right() - w))
        y = max(avail.top(), min(y, avail.bottom() - h))

    # 脱离父窗口，成为独立顶层窗口，不再跟随父窗口尺寸
    dialog.setParent(None)
    if host is not None and host is not dialog:
        host.removeEventFilter(dialog)

    dialog.setWindowFlags(
        Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint
    )
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.ApplicationModal)
    dialog.setFixedSize(w, h)
    dialog.move(x, y)
    layout = dialog.layout()
    if layout is not None:
        layout.setAlignment(dialog.widget, Qt.AlignCenter)
    dialog.setMaskColor(QColor(0, 0, 0, 0))
    dialog.colorChanged.connect(on_color)
    dialog.exec()
