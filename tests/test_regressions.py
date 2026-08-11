from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication

from aimatting.core.history import (
    HistoryManager,
    snapshot_base_image,
    snapshot_to_images,
)
from aimatting.core.image_ops import adjust_image
from aimatting.core.io_utils import build_output_path


def _app():
    return QApplication.instance() or QApplication([])


def test_build_output_path_never_overwrites_source() -> None:
    out = build_output_path("C:/photos/photo.png", None, "", "png")
    assert out != Path("C:/photos/photo.png")
    assert out == Path("C:/photos/photo_out.png")


def test_build_output_path_keeps_suffix() -> None:
    out = build_output_path("C:/photos/photo.png", None, "抠图后", "png")
    assert out == Path("C:/photos/photo抠图后.png")


def test_history_snapshot_keeps_base_image() -> None:
    history = HistoryManager(5)
    source = Image.new("RGB", (4, 4), (10, 10, 10))
    base = Image.new("RGB", (4, 4), (99, 88, 77))
    history.push(source, None, base=base)
    snap = history.undo()
    assert snap is not None
    restored_base = snapshot_base_image(snap)
    assert restored_base is not None
    assert restored_base.getpixel((0, 0)) == (99, 88, 77)
    restored_source, _, _ = snapshot_to_images(snap)
    assert restored_source.getpixel((0, 0)) == (10, 10, 10)


def test_download_task_constructed_with_parent_keyword(monkeypatch) -> None:
    _app()
    from aimatting.ui import dialogs

    captured = {}

    from PySide6.QtCore import QObject, Signal

    class FakeTask(QObject):
        progress = Signal(int, int, int)
        done = Signal(str)
        failed = Signal(str)
        canceled = Signal()

        def __init__(self, *args, **kwargs) -> None:
            super().__init__()
            captured["args"] = args
            captured["kwargs"] = kwargs

        def start(self) -> None:
            pass

    monkeypatch.setattr(dialogs, "ModelDownloadTask", FakeTask)
    dialog = dialogs.ModelManagerDialog("birefnet_hr_matting")
    try:
        dialog._start_download()
        assert len(captured["args"]) == 2  # (url, save_path)
        assert captured["kwargs"].get("parent") is dialog
    finally:
        dialog.deleteLater()


def test_shortcuts_exist() -> None:
    from aimatting.ui.main_window import MainWindow

    _app()
    win = MainWindow()
    try:
        assert win.matte_action.shortcut().toString() == "Ctrl+R"
        assert win.save_action.shortcut().toString() == "Ctrl+S"
    finally:
        win.close()


def test_preprocess_undo_no_double_apply() -> None:
    from aimatting.ui.main_window import MainWindow

    _app()
    win = MainWindow()
    try:
        img = Image.new("RGB", (32, 32), (100, 150, 200))
        win.current_path = "t.png"
        win.original_image = img
        win.prep_source = img
        win._exit_all_tools()
        win._reset_working()

        win.tool_panel.set_preprocess(
            {"brightness": 50, "contrast": 0, "saturation": 0, "temperature": 0}
        )
        win._apply_preprocess_now(push_history=True)
        assert win.history.can_undo()

        win.undo()
        assert win.prep_source is not None
        assert win.prep_source.getpixel((16, 16)) == (100, 150, 200)
        # 撤销后滑块应恢复为旧值（0）
        assert win.tool_panel.prep_sliders["brightness"].value() == 0

        # 再次调整亮度 -20：应基于原图，而不是在 +50 的结果上再叠加
        win.tool_panel.set_preprocess(
            {"brightness": -20, "contrast": 0, "saturation": 0, "temperature": 0}
        )
        win._apply_preprocess_now(push_history=True)
        expected = adjust_image(img, brightness=-20).getpixel((16, 16))
        assert win.working_rgb.getpixel((16, 16)) == expected
    finally:
        win.close()


def test_batch_status_keyed_by_path() -> None:
    _app()
    from aimatting.core.config import Settings
    from aimatting.ui.batch_panel import BatchPanel

    panel = BatchPanel(Settings())
    try:
        panel.add_paths(["a.png", "b.png"])
        panel.set_status(0, "失败：加载失败")
        panel.set_status(1, "完成")
        assert "a.png" in panel.failed_rows()
        # 删除第一行后，b.png 的状态不应错位
        panel.file_list.item(0).setSelected(True)
        panel._remove_selected()
        assert panel.failed_rows() == []
        assert panel.file_list.count() == 1
    finally:
        panel.deleteLater()
