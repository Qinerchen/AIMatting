from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from aimatting.core.config import Settings  # noqa: E402
from aimatting.ui.batch_panel import BatchPanel  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def test_batch_settings_button_text_switches() -> None:
    _app()
    panel = BatchPanel(Settings())
    try:
        panel.add_paths(["a.png", "b.png", "c.png"])
        assert panel.item_settings_button.text() == "单独设置"

        for i in range(panel.file_list.count()):
            panel.file_list.item(i).setSelected(True)
        assert panel.item_settings_button.text() == "批量设置"

        panel.file_list.item(0).setSelected(False)
        assert panel.item_settings_button.text() == "批量设置"

        panel.file_list.item(1).setSelected(False)
        assert panel.item_settings_button.text() == "单独设置"
    finally:
        panel.deleteLater()


def test_eyedropper_constructs() -> None:
    _app()
    from aimatting.ui.eyedropper import Eyedropper

    picker = Eyedropper()
    try:
        assert picker.color().isValid()
    finally:
        picker.deleteLater()
