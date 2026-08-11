from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication

_QAPP = QApplication.instance() or QApplication([])


def _app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_main_window_constructs() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        assert win.windowTitle()
        assert win.tool_panel is not None
        assert win.view is not None
        assert win.panel.matte_button.isEnabled() is False  # 未导入图片
        # 导入与工具同列：工具面板位于「单张」页左侧栏内
        assert win.tool_panel.parent() is win.single_left
        assert win.stackedWidget.count() == 2
        assert win.batch_page is not None
        # 单张页与批量页各有一条状态栏
        assert len(win._status_labels) == 2
    finally:
        win.close()


def test_import_and_tool_layout() -> None:
    from aimatting.ui.main_window import MainWindow

    app = _app()
    win = MainWindow()
    try:
        img = Image.new("RGB", (64, 48), (120, 60, 30))
        # 直接设置状态，模拟导入
        win.current_path = "test.png"
        win.original_image = img
        win.prep_source = img
        win._exit_all_tools()
        win._reset_working()
        assert win.working_rgb is not None
        assert win.working_rgb.size == (64, 48)
        assert win.panel.matte_button.isEnabled() is True
        # 工具列四个按钮
        assert set(win.tool_panel._tool_buttons) == {
            "mask",
            "crop",
            "preprocess",
            "bg",
            "retouch",
        }
    finally:
        win.close()


def test_top_bar_has_no_import_button() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        assert "import" not in win._tb_buttons
        assert "undo" in win._tb_buttons and "redo" in win._tb_buttons
    finally:
        win.close()


def test_mask_apply_keeps_region() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        img = Image.new("RGB", (32, 32), (10, 200, 10))
        win.current_path = "test.png"
        win.original_image = img
        win.prep_source = img
        win._exit_all_tools()
        win._reset_working()
        mask = np.zeros((32, 32), dtype=np.uint8)
        mask[8:24, 8:24] = 255
        win.mask_prior = mask
        win._apply_mask_to_image()
        out = win.working_rgb
        assert out.mode == "RGBA"
        assert np.asarray(out)[20, 20, 3] == 255
        assert np.asarray(out)[2, 2, 3] == 0
        # 遮罩保留：抠图时作为约束，模型在画笔区域内精细抠图
        assert win.mask_prior is not None and win.mask_prior.max() > 0
    finally:
        win.close()


def test_retouch_stroke_edits_alpha() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        img = Image.new("RGB", (200, 200), (80, 90, 100))
        win.current_path = "t.png"
        win.original_image = img
        win.prep_source = img
        win._exit_all_tools()
        win._reset_working()
        win.alpha = np.full((200, 200), 255, dtype=np.uint8)
        win._on_tool_selected("retouch")
        assert win._active_tool == "retouch"
        # 擦除
        win.tool_panel.set_retouch_mode("erase")
        win.tool_panel.retouch_size.setValue(40)
        win.tool_panel.retouch_hardness.setValue(100)
        win._on_retouch_stroke(100, 100)
        assert win.alpha[100, 100] == 0
        win._on_retouch_finished()
        # 恢复
        win.tool_panel.set_retouch_mode("add")
        win._on_retouch_stroke(100, 100)
        assert win.alpha[100, 100] == 255
        win._on_retouch_finished()
    finally:
        win.close()


def test_retouch_requires_matte(monkeypatch) -> None:
    from aimatting.ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_info", lambda *a, **k: None)
    win = MainWindow()
    try:
        img = Image.new("RGB", (64, 48), (120, 60, 30))
        win.current_path = "t.png"
        win.original_image = img
        win.prep_source = img
        win._exit_all_tools()
        win._reset_working()
        win._on_tool_selected("retouch")
        assert win._active_tool == ""  # 未抠图时不进入橡皮擦
    finally:
        win.close()


def test_mask_stroke_can_be_undone() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        img = Image.new("RGB", (100, 100), (80, 90, 100))
        win.current_path = "t.png"
        win.original_image = img
        win.prep_source = img
        win._exit_all_tools()
        win._reset_working()
        win._on_tool_selected("mask")
        win.tool_panel.set_brush_mode("add")
        win.tool_panel.brush_size.setValue(40)
        win.tool_panel.brush_hardness.setValue(100)
        win._on_brush_stroke(50, 50)
        win._on_brush_finished()
        assert win.mask_prior[50, 50] > 0
        assert win.history.can_undo()
        win.undo()
        assert win.mask_prior is None or win.mask_prior[50, 50] == 0
    finally:
        win.close()


def test_zoom_label_updates() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        win._on_zoom_changed(1.25)
        assert win.zoom_label.text() == "125%"
        win._on_zoom_changed(0.5)
        assert win.zoom_label.text() == "50%"
    finally:
        win.close()


def test_maximize_toggle_uses_native_state() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        win._toggle_maximize()
        assert win._is_maximized is True
        assert win.isMaximized() is True
        win._toggle_maximize()
        assert win._is_maximized is False
        assert win.isMaximized() is False
    finally:
        win.close()


def _stop_exit_anim(win) -> None:
    group = win._exit_anim_group
    if group is not None:
        try:
            group.finished.disconnect()
        except RuntimeError:
            pass
        group.stop()
        group.deleteLater()
    win._exit_anim_group = None
    win._exit_anim_running = False


def test_minimize_animation_starts() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        win.show()
        win._animate_minimize()
        assert win.isMinimized() is True
    finally:
        _stop_exit_anim(win)
        win.close()


def test_close_animation_starts() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        win.show()
        win._animate_close()
        assert win.isVisible() is False
    finally:
        _stop_exit_anim(win)
        win.close()


def test_crop_after_matte_preserves_alpha() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        img = Image.new("RGB", (100, 80), (10, 200, 10))
        win.current_path = "t.png"
        win.original_image = img
        win.prep_source = img
        win._exit_all_tools()
        win._reset_working()
        alpha = np.zeros((80, 100), dtype=np.uint8)
        alpha[10:70, 10:90] = 255
        win.alpha = alpha
        win._apply_crop((10, 10, 60, 50))
        assert win.working_rgb.size == (50, 40)
        assert win.alpha is not None
        assert win.alpha.shape == (40, 50)
        assert win.alpha.max() == 255
    finally:
        win.close()


def test_crop_can_be_undone_before_matte() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        img = Image.new("RGB", (100, 80), (10, 200, 10))
        win.current_path = "t.png"
        win.original_image = img
        win.prep_source = img
        win._exit_all_tools()
        win._reset_working()

        win._apply_crop((10, 10, 60, 50))
        assert win.working_rgb.size == (50, 40)
        assert win.history.can_undo()

        win.undo()
        assert win.working_rgb.size == (100, 80)
        assert win.original_image.size == (100, 80)

        win.redo()
        assert win.working_rgb.size == (50, 40)
    finally:
        win.close()


def test_import_new_image_resets_preprocess(tmp_path) -> None:
    from aimatting.ui.main_window import MainWindow

    path = tmp_path / "reset.png"
    Image.new("RGB", (32, 32), (100, 100, 100)).save(path)
    win = MainWindow()
    try:
        win.tool_panel.prep_sliders["brightness"].setValue(40)
        win.tool_panel.prep_sliders["contrast"].setValue(-30)
        win.import_image(str(path))
        assert win.tool_panel.prep_sliders["brightness"].value() == 0
        assert win.tool_panel.prep_sliders["contrast"].value() == 0
    finally:
        win.close()


def test_preview_render_paths_do_not_crash() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        img = Image.new("RGB", (64, 48), (120, 60, 30))
        win.current_path = "t.png"
        win.original_image = img
        win.prep_source = img
        win._exit_all_tools()
        win._reset_working()
        win.alpha = np.full((48, 64), 255, dtype=np.uint8)
        win._active_tool = "bg"
        win._render(fit=False, preview=True)
        win._render_preprocess_preview()
    finally:
        win.close()


def test_entering_tool_disables_compare() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        img = Image.new("RGB", (64, 48), (120, 60, 30))
        win.current_path = "t.png"
        win.original_image = img
        win.prep_source = img
        win._exit_all_tools()
        win._reset_working()
        win.alpha = np.full((48, 64), 255, dtype=np.uint8)
        win.compare_button.setChecked(True)
        assert win.compare_enabled is True
        win._on_tool_selected("crop")
        assert win.compare_enabled is False
        assert win._active_tool == "crop"
    finally:
        win.close()


def test_brush_coverage_matches_cursor_size() -> None:
    from aimatting.ui.main_window import MainWindow

    win = MainWindow()
    try:
        img = Image.new("RGB", (200, 200), (80, 90, 100))
        win.current_path = "t.png"
        win.original_image = img
        win.prep_source = img
        win._exit_all_tools()
        win._reset_working()
        win._on_tool_selected("mask")
        win.tool_panel.set_brush_mode("add")  # 与真实点击「画前景」一致
        win.tool_panel.brush_size.setValue(60)  # 直径 60
        win.tool_panel.brush_hardness.setValue(100)
        win._on_brush_stroke(100, 100)
        m = win.mask_prior
        assert m is not None
        ys, xs = np.where(m > 127)
        radius = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2.0
        assert 28 <= radius <= 33, f"覆盖半径 {radius} 应与光标(30)一致"
        # 顶部边缘连续覆盖：从(100,0)画到(100,30)应覆盖到第0行
        win._on_brush_stroke(100, 0)
        win._on_brush_stroke(100, 30)
        assert m[0:10, 95:105].max() > 127
    finally:
        win.close()
