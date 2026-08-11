"""颜色选择辅助：保证 qfluentwidgets 颜色对话框完整显示。"""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget
from qfluentwidgets import ColorDialog


_MIN_W = 560
_MIN_H = 800


def run_color_dialog(parent: QWidget, initial, title: str, on_color) -> None:
    """弹出颜色对话框，并临时放大过小的父窗口，避免内容显示不全。

    qfluentwidgets 的 ColorDialog 是跟随父窗口尺寸的遮罩对话框（内容固定
    约 488x696），如果父窗口太窄/太矮会被裁切。这里在打开前临时扩大父窗口，
    关闭后再恢复原尺寸。
    """
    old_min = parent.minimumSize()
    old_size = parent.size()
    target_w = max(old_size.width(), _MIN_W)
    target_h = max(old_size.height(), _MIN_H)
    screen = parent.screen()
    if screen is not None:
        avail = screen.availableGeometry()
        target_w = min(target_w, max(320, avail.width() - 40))
        target_h = min(target_h, max(320, avail.height() - 40))

    parent.setMinimumSize(
        QSize(max(old_min.width(), _MIN_W), max(old_min.height(), _MIN_H))
    )
    if parent.width() < target_w or parent.height() < target_h:
        parent.resize(target_w, target_h)

    try:
        dialog = ColorDialog(initial, title, parent)
        dialog.colorChanged.connect(on_color)
        dialog.exec()
    finally:
        parent.setMinimumSize(old_min)
        parent.resize(old_size)
