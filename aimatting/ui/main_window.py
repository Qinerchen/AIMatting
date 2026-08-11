"""主窗口：负责导入、抠图、编辑、批量与导出的整体流程。"""
from __future__ import annotations

import gc
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import (
    QEvent,
    QSize,
    QTimer,
    QUrl,
    Qt,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    FluentWindow,
    FluentIcon,
    MessageBox,
    NavigationItemPosition,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    ToolButton,
)

from aimatting.core.batch import BatchOptions, BatchTask
from aimatting.core.config import (
    MODEL_REGISTRY,
    Settings,
    app_root,
    model_file_path,
)
from aimatting.core.history import (
    HistoryManager,
    snapshot_original_image,
    snapshot_to_images,
)
from aimatting.core.image_ops import (
    adjust_image,
    alpha_to_cutout,
    combine_with_target_mask,
    composite_background,
    defringe,
    flatten_to_rgb,
    keep_masked_region,
    load_image,
    mask_bbox,
    opaque_over_white,
    paint_mask,
    soften_alpha,
)
from aimatting.core.io_utils import (
    FILE_DIALOG_FILTER,
    build_output_path,
    ensure_supported_suffix,
    is_supported,
    save_image,
)
from aimatting.core.worker_process import RemoteMattingEngine
from aimatting.ui.batch_panel import BatchPanel
from aimatting.ui.dialogs import AboutDialog, ModelManagerDialog, TutorialDialog
from aimatting.ui.image_view import ImageView
from aimatting.ui.panels import ParamPanel, ToolPanel, _circular_arrow_icon
from aimatting.workers.tasks import MattingTask, ModelPreloadTask


def _pil_to_pixmap(image: Image.Image) -> QPixmap:
    image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    qimg = QImage(
        data,
        image.width,
        image.height,
        image.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    return QPixmap.fromImage(qimg)


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AIMatting - BiRefNet 高精度抠图工具")
        self.resize(1280, 800)
        self.setWindowIcon(
            QIcon(str(app_root() / "assets" / "aimatting_icon.png"))
        )

        self.settings = Settings()
        self.engine = RemoteMattingEngine()
        self.history = HistoryManager(max_steps=20)
        self._set_engine_model_path()
        self._status_labels: list[BodyLabel] = []
        self._model_labels: list[CaptionLabel] = []

        self.original_image: Image.Image | None = None
        self.prep_source: Image.Image | None = None   # 预处理基准图（含裁剪/画笔改动）
        self.working_rgb: Image.Image | None = None
        self.fg_rgb: Image.Image | None = None        # 去色边后的前景色版本
        self.alpha: np.ndarray | None = None
        self.current_path: str | None = None
        self._busy = False
        self._paint_changed = False
        self._render_pending = False
        self._brush_mode = "none"
        self._retouch_mode = "none"
        self._last_stroke_xy: tuple[float, float] | None = None
        self._retouch_before: np.ndarray | None = None
        self._mask_before: np.ndarray | None = None
        self.mask_prior: np.ndarray | None = None     # 笔刷遮罩（抠图前）
        self._matte_use_mask = False
        self._matte_crop_box: tuple[int, int, int, int] | None = None
        self._overlay_pending = False
        self._matte_task: MattingTask | None = None
        self._preload_task: ModelPreloadTask | None = None
        self._batch_task: BatchTask | None = None
        self.compare_enabled = False
        self._crop_mode = False
        self._active_tool = ""                        # "" / mask / crop / preprocess / bg
        self._resize_edge = ""
        self._resize_start_global = None
        self._resize_start_rect = None
        self._is_maximized = False
        self._was_minimized = False
        self._normal_geometry = None
        self._restore_geometry = None
        self._geo_anim = None
        self._exit_anim_group = None
        self._exit_anim_running = False

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(30)
        self._render_timer.timeout.connect(self._render_now)

        self._preprocess_timer = QTimer(self)
        self._preprocess_timer.setSingleShot(True)
        self._preprocess_timer.setInterval(150)
        self._preprocess_timer.timeout.connect(self._apply_preprocess_now)

        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.setInterval(40)
        self._overlay_timer.timeout.connect(self._build_overlay)

        self._build_ui()
        self._connect_signals()
        self._update_ui_state()
        self.status("就绪")
        self._startup_model_check()
        self._preload_default_model()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self._build_actions()

        self.single_interface = self._build_single_interface()
        self.single_interface.setObjectName("singleInterface")
        self.batch_panel = BatchPanel(self.settings)
        self.batch_panel.setObjectName("batchInterface")

        self.addSubInterface(
            self.single_interface,
            FluentIcon.PHOTO,
            "单张",
            NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.batch_panel,
            FluentIcon.LIBRARY,
            "批量",
            NavigationItemPosition.TOP,
        )
        self.setAcceptDrops(True)

    def _build_single_interface(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(8)

        root.addWidget(self._build_top_bar())

        splitter = QSplitter(Qt.Orientation.Horizontal, page)
        self.single_left = self._build_left_panel()
        splitter.addWidget(self.single_left)
        splitter.addWidget(self._build_center_panel())
        self.panel = ParamPanel(self.settings)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setHandleWidth(1)
        splitter.setSizes([300, 700, 340])
        root.addWidget(splitter, 1)

        root.addWidget(self._make_status_bar(True))
        return page

    def _build_left_panel(self) -> QWidget:
        """单张页左侧：导入区 + 工具列。"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.drop_label = BodyLabel("拖拽图片到此处\n或点击下方按钮导入")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setMinimumHeight(140)
        self.drop_label.setObjectName("DropZone")
        self.drop_label.setAcceptDrops(True)
        self.drop_label.setStyleSheet(
            "BodyLabel { border: 2px dashed rgba(255,255,255,0.35);"
            " border-radius: 10px; background: rgba(255,255,255,0.04);"
            " padding: 12px; }"
        )
        layout.addWidget(self.drop_label)

        self.import_button = PrimaryPushButton("选择图片…")
        layout.addWidget(self.import_button)

        self.file_info = CaptionLabel("未导入图片")
        self.file_info.setWordWrap(True)
        layout.addWidget(self.file_info)

        self.single_status = CaptionLabel("")
        self.single_status.setWordWrap(True)
        layout.addWidget(self.single_status)

        self.cancel_button = PushButton("取消任务")
        self.cancel_button.setObjectName("CancelButton")
        self.cancel_button.setStyleSheet(
            "PushButton { color: #FF8A8E; background: rgba(240, 74, 80, 0.15); }"
            "PushButton:hover { color: white; background: #F04A50; }"
        )
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button)

        self.tool_panel = ToolPanel(self.settings)
        layout.addWidget(self.tool_panel, 1)
        return panel

    def _build_center_panel(self) -> QWidget:
        """中间：预览画布 + 缩放工具条。"""
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)

        self.view = ImageView()
        center_layout.addWidget(self.view, 1)

        zoom_row = QHBoxLayout()
        self.zoom_out_button = ToolButton(FluentIcon.ZOOM_OUT, center)
        self.fit_button = PushButton("适合窗口")
        self.actual_button = PushButton("100%")
        self.zoom_in_button = ToolButton(FluentIcon.ZOOM_IN, center)
        self.zoom_label = BodyLabel("100%")
        self.zoom_label.setFixedWidth(52)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setToolTip("当前预览缩放比例（滚轮缩放）")
        self.compare_button = PushButton("对比")
        self.compare_button.setCheckable(True)
        for btn in (
            self.zoom_out_button,
            self.fit_button,
            self.actual_button,
            self.zoom_in_button,
            self.compare_button,
        ):
            btn.setFixedWidth(88)
            zoom_row.addWidget(btn)
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addStretch(1)
        center_layout.addLayout(zoom_row)
        return center

    def _make_status_bar(self, with_progress: bool = True) -> QWidget:
        bar = QWidget()
        bar.setObjectName("StatusBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        status_label = CaptionLabel("就绪")
        status_label.setObjectName("StatusText")
        layout.addWidget(status_label, 1)
        self._status_labels.append(status_label)

        if with_progress:
            self.single_progress = ProgressBar()
            self.single_progress.setFixedWidth(180)
            self.single_progress.hide()
            layout.addWidget(self.single_progress)

        model_label = CaptionLabel("")
        model_label.setObjectName("ModelLabel")
        layout.addWidget(model_label)
        self._model_labels.append(model_label)
        return bar

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and not self.isMinimized():
            self._is_maximized = self.isMaximized()

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._tb_buttons: dict[str, QWidget] = {}
        for key, text, icon, shortcut, slot in (
            ("undo", "撤销", _circular_arrow_icon("undo"), "Ctrl+Z", self.undo),
            ("redo", "重做", _circular_arrow_icon("redo"), "Ctrl+Y", self.redo),
        ):
            btn = ToolButton(icon, bar)
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(34, 30)
            btn.setToolTip(f"{text}（{shortcut}）")
            btn.clicked.connect(slot)
            layout.addWidget(btn)
            self._tb_buttons[key] = btn

        layout.addSpacing(8)
        layout.addWidget(CaptionLabel("模型"))
        self.model_combo = ComboBox()
        self.model_combo.setObjectName("ModelCombo")
        self.model_combo.setMinimumWidth(200)
        for mid, info in MODEL_REGISTRY.items():
            self.model_combo.addItem(
                info["name"].split("（")[0], userData=mid
            )
        self.model_combo.setCurrentIndex(
            max(
                0,
                self.model_combo.findData(self.settings.get("model_id", "")),
            )
        )
        self.model_combo.currentIndexChanged.connect(
            lambda _i: self._on_model_combo_changed(
                str(self.model_combo.currentData())
            )
        )
        layout.addWidget(self.model_combo)
        layout.addStretch(1)

        for key, text, slot in (
            ("models", "模型管理", self.open_model_manager),
            ("tutorial", "使用教程", self.open_tutorial),
            ("about", "关于", self.open_about),
        ):
            btn = PushButton(text)
            btn.setObjectName("TopBarButton")
            btn.clicked.connect(slot)
            layout.addWidget(btn)
            self._tb_buttons[key] = btn

        return bar

    def _on_model_combo_changed(self, model_id: str) -> None:
        if model_id == self.settings.get("model_id", ""):
            return
        self.settings.set("model_id", model_id)
        self.settings.save()
        self.engine.unload()
        self._set_engine_model_path()
        self._update_model_label()
        self._preload_default_model()
        if self._current_model_path():
            self.status(f"已切换到 {MODEL_REGISTRY[model_id]['name'].split('（')[0]}")
        else:
            self.status("该模型尚未下载，请在「模型管理」中下载")

    def _sync_action_buttons(self) -> None:
        if not hasattr(self, "_tb_buttons"):
            return
        states = {
            "undo": self.undo_action.isEnabled(),
            "redo": self.redo_action.isEnabled(),
            "models": not self._busy,
            "tutorial": True,
            "about": True,
        }
        for key, enabled in states.items():
            if key in self._tb_buttons:
                self._tb_buttons[key].setEnabled(enabled)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _animate_minimize(self) -> None:
        self.showMinimized()

    def _animate_close(self) -> None:
        self.close()

    def _build_actions(self) -> None:
        self.import_action = QAction("导入图片", self)
        self.import_action.setShortcut(QKeySequence("Ctrl+O"))
        self.undo_action = QAction("撤销", self)
        self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.redo_action = QAction("重做", self)
        self.redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        self.model_action = QAction("模型管理", self)
        self.tutorial_action = QAction("使用教程", self)
        self.tutorial_action.setShortcut(QKeySequence("F1"))
        self.about_action = QAction("关于", self)
        for action in (
            self.import_action,
            self.undo_action,
            self.redo_action,
            self.model_action,
            self.tutorial_action,
            self.about_action,
        ):
            self.addAction(action)

    def _connect_signals(self) -> None:
        self.import_button.clicked.connect(self.import_image)
        self.import_action.triggered.connect(self.import_image)
        self.undo_action.triggered.connect(self.undo)
        self.redo_action.triggered.connect(self.redo)
        self.model_action.triggered.connect(self.open_model_manager)
        self.tutorial_action.triggered.connect(self.open_tutorial)
        self.about_action.triggered.connect(self.open_about)

        self.zoom_out_button.clicked.connect(self.view.zoom_out)
        self.zoom_in_button.clicked.connect(self.view.zoom_in)
        self.fit_button.clicked.connect(self.view.fit)
        self.actual_button.clicked.connect(self.view.actual_size)
        self.compare_button.toggled.connect(self._on_compare_toggled)
        self.view.zoomChanged.connect(self._on_zoom_changed)
        self.cancel_button.clicked.connect(self._cancel_current_task)

        self.tool_panel.tool_selected.connect(self._on_tool_selected)
        self.tool_panel.bg_changed.connect(lambda: self._render(fit=False))
        self.tool_panel.preprocess_changed.connect(self._preprocess_timer.start)
        self.tool_panel.preprocess_commit.connect(self._apply_preprocess_now)
        self.tool_panel.mask_mode_changed.connect(self._on_brush_mode_changed)
        self.tool_panel.mask_clear_requested.connect(self._clear_mask_state)
        self.tool_panel.brush_params_changed.connect(self._sync_brush_cursor)
        self.tool_panel.mask_apply_requested.connect(self._apply_mask_to_image)
        self.tool_panel.retouch_mode_changed.connect(self._on_retouch_mode_changed)
        self.tool_panel.retouch_params_changed.connect(self._sync_brush_cursor)
        self.tool_panel.crop_confirm_requested.connect(self._confirm_crop)
        self.tool_panel.crop_cancel_requested.connect(self._cancel_crop)
        self.panel.feather_requested.connect(self._apply_feather)
        self.panel.defringe_requested.connect(self._apply_defringe)
        self.panel.matte_requested.connect(self.start_matte)
        self.panel.save_requested.connect(self.save_current)

        self.view.brushStroke.connect(self._on_brush_stroke)
        self.view.brushStrokeFinished.connect(self._on_brush_finished)
        self.view.brushSizeChanged.connect(self._on_brush_size_wheel)
        self.view.toolActionRequested.connect(self._on_tool_action)
        self.view.cropRectChanged.connect(self._on_crop_rect_changed)
        self.view.cropConfirmed.connect(self._confirm_crop)
        self.view.cropCanceled.connect(self._cancel_crop)

        self.batch_panel.start_requested.connect(self._start_batch)
        self.batch_panel.stop_requested.connect(self._stop_batch)
        self.batch_panel.edit_requested.connect(self._open_batch_edit)
        self.batch_panel.retry_requested.connect(self._retry_failed_batch)

        self.drop_label.dragEnterEvent = self._drop_enter
        self.drop_label.dropEvent = self._drop

    # ------------------------------------------------------------------
    # 导入
    # ------------------------------------------------------------------
    def import_image(self, path: str | None = None) -> None:
        if self._busy:
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择图片", "", FILE_DIALOG_FILTER
            )
        if not path:
            return
        try:
            image = load_image(path)
        except Exception as exc:  # noqa: BLE001
            self._critical("导入失败", f"无法打开图片：\n{exc}")
            return
        self.current_path = str(Path(path))
        self.original_image = image
        self.prep_source = image
        self._exit_all_tools()
        self._reset_working()

    def _reset_working(self) -> None:
        prep = self.tool_panel.get_preprocess()
        base = self.prep_source or self.original_image
        self.working_rgb = adjust_image(base, **prep)
        self.fg_rgb = None
        self.alpha = None
        self.history.clear()
        self.prep_source = base
        self._paint_changed = False
        self._clear_mask_state()
        self._reset_view_modes()
        self._render(fit=True)
        name = Path(self.current_path).name
        self.file_info.setText(
            f"文件名：{name}\n尺寸：{self.working_rgb.width} × "
            f"{self.working_rgb.height}\n格式：{Path(self.current_path).suffix.upper()}"
        )
        self._update_drop_preview()
        self.single_status.setText("已导入，可先预处理 / 笔刷遮罩，然后点「开始抠图」")
        self.status(f"已导入 {name}")
        self._update_ui_state()

    def _update_drop_preview(self) -> None:
        if self.original_image is None:
            self.drop_label.setText("拖拽图片到此处\n或点击下方按钮导入")
            self.drop_label.setPixmap(QPixmap())
            self.drop_label.setToolTip("")
            return
        pixmap = _pil_to_pixmap(self.original_image.convert("RGB"))
        scaled = pixmap.scaled(
            max(60, self.drop_label.width() - 16),
            max(60, self.drop_label.height() - 16),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.drop_label.setText("")
        self.drop_label.setPixmap(scaled)
        if self.current_path:
            self.drop_label.setToolTip(self.current_path)

    # ------------------------------------------------------------------
    # 预处理
    # ------------------------------------------------------------------
    def _apply_preprocess_now(self) -> None:
        if self.original_image is None:
            return
        self._preprocess_timer.stop()
        if self.alpha is not None:
            # 保留历史：把当前状态入栈，预处理变化可撤销
            self.history.push(
                self.working_rgb,
                Image.fromarray(self.alpha),
                self.tool_panel.get_preprocess(),
            )
        base = self.prep_source or self.original_image
        self.working_rgb = adjust_image(base, **self.tool_panel.get_preprocess())
        self.fg_rgb = None
        self._paint_changed = False
        self._clear_mask_state()
        self._reset_view_modes()
        self._render(fit=False)
        self.single_status.setText("预处理已更新（保留当前抠图结果）")
        self.status("预处理已更新（保留当前抠图结果）")
        self._update_ui_state()

    def _reset_view_modes(self) -> None:
        self.compare_enabled = False
        self.compare_button.setChecked(False)
        self.view.set_compare_enabled(False)
        self._crop_mode = False
        self.view.set_crop_mode(False)
        self._brush_mode = "none"
        self._retouch_mode = "none"
        self.view.set_brush_active(False)
        self._schedule_overlay()

    # ------------------------------------------------------------------
    # 抠图
    # ------------------------------------------------------------------
    def start_matte(self) -> None:
        if self._busy or self.original_image is None:
            self._info("提示", "请先导入图片。")
            return
        model_path = self._current_model_path()
        if not model_path:
            self._warn(
                "缺少模型", "尚未下载抠图模型，请先在「模型管理」中下载。"
            )
            self.open_model_manager()
            return
        self.engine.set_model_path(model_path)
        max_side = self.panel.get_output_settings()[4]
        # 有笔刷遮罩时：裁剪到遮罩区域精细抠图，并用遮罩约束只抠主体
        self._matte_use_mask = False
        self._matte_crop_box = None
        self._matte_mask_ratio = 0.0
        w, h = self.working_rgb.size
        if self.mask_prior is not None and self.mask_prior.max() > 0:
            self._matte_use_mask = True
            self._matte_mask_ratio = float(
                (self.mask_prior > 15).mean()
            )
            box = mask_bbox(
                self.mask_prior, margin_ratio=0.3, min_margin=48
            )
            if box:
                area_ratio = (
                    (box[2] - box[0]) * (box[3] - box[1]) / max(1, w * h)
                )
                if area_ratio < 0.85:
                    # 主体周围保留足够背景上下文，模型才能识别
                    self._matte_crop_box = box
                    task_image = self.working_rgb.crop(box)
                else:
                    task_image = self.working_rgb
            else:
                task_image = self.working_rgb
        else:
            task_image = self.working_rgb
        self._set_busy(True)
        self.single_progress.setRange(0, 100)
        self.single_progress.setValue(0)
        self.single_progress.show()
        self.single_status.setText(
            "正在抠图…"
            if not self._matte_use_mask
            else "画笔保留区域 + 模型精细抠图中…"
        )
        self.status(
            "正在抠图…"
            if not self._matte_use_mask
            else "画笔保留区域 + 模型精细抠图中…"
        )
        self._matte_task = MattingTask(
            self.engine, task_image, max_side=max_side, parent=self
        )
        self._matte_task.progress.connect(self._on_matte_progress_pct)
        self._matte_task.done.connect(self._on_matte_done)
        self._matte_task.failed.connect(self._on_matte_failed)
        self._matte_task.canceled.connect(self._on_matte_canceled)
        self._matte_task.finished.connect(self._matte_task.deleteLater)
        self._matte_task.start()

    def _on_matte_progress(self, text: str) -> None:
        self._on_matte_progress_pct(0, text)

    def _on_matte_progress_pct(self, percent: int, text: str) -> None:
        self.single_progress.setRange(0, 100)
        self.single_progress.setValue(int(percent))
        self.single_status.setText(text)
        self.status(text)

    def _on_matte_canceled(self) -> None:
        self._set_busy(False)
        self.single_progress.hide()
        self.single_status.setText("已取消")
        self.status("任务已取消")
        self._finish_matte_cleanup()
        self._update_ui_state()

    def _on_matte_done(self, alpha_img: Image.Image, elapsed: float) -> None:
        self._set_busy(False)
        self.single_progress.hide()
        h, w = self.working_rgb.height, self.working_rgb.width
        alpha_arr = np.asarray(alpha_img.convert("L"), dtype=np.uint8)
        if self._matte_use_mask:
            if self._matte_crop_box:
                x0, y0, x1, y1 = self._matte_crop_box
                full = np.zeros((h, w), dtype=np.uint8)
                full[y0:y1, x0:x1] = alpha_arr
            else:
                full = alpha_arr
            combined = combine_with_target_mask(full, self.mask_prior)
            if combined.getextrema()[0] == 0 and combined.getextrema()[1] == 0:
                # 模型未能识别主体（主体几乎占满画面）：回退为笔刷遮罩
                self.alpha = np.where(
                    self.mask_prior > 127, 255, 0
                ).astype(np.uint8)
                self.status(
                    "模型未识别到主体，已按笔刷遮罩出图；建议缩小遮罩范围后重试"
                )
                self.single_status.setText("已使用笔刷遮罩作为结果")
            else:
                self.alpha = np.asarray(combined, dtype=np.uint8).copy()
        else:
            self.alpha = alpha_arr.copy()
        self.history.push(
            self.working_rgb,
            Image.fromarray(self.alpha),
            self.tool_panel.get_preprocess(),
            Image.fromarray(self.mask_prior)
            if self.mask_prior is not None
            else None,
        )
        self._paint_changed = False
        provider = self.engine.provider
        self._render(fit=True)
        self.single_status.setText(
            f"{'画笔区域+精细抠图完成' if self._matte_use_mask else '抠图完成'}，"
            f"耗时 {elapsed:.2f} 秒（{provider}）"
        )
        self.status(
            f"{'画笔区域+精细抠图完成' if self._matte_use_mask else '抠图完成'}，"
            f"耗时 {elapsed:.2f} 秒"
        )
        self._finish_matte_cleanup()
        self._update_ui_state()

    def _on_matte_failed(self, message: str) -> None:
        self._set_busy(False)
        self.single_progress.hide()
        self.single_status.setText("抠图失败")
        self.status("抠图失败")
        self._critical("抠图失败", message)
        self._finish_matte_cleanup()
        self._update_ui_state()

    def _finish_matte_cleanup(self) -> None:
        """抠图结束后清理：退出工具预览、回收线程与临时内存。"""
        self._exit_tool_previews()
        if self._active_tool == "mask":
            self._active_tool = ""
            self.tool_panel.set_active_tool("")
        self._release_engine_memory()

    def _release_engine_memory(self) -> None:
        """按设置释放模型内存（默认常驻，避免每次抠图重新加载模型）。"""
        if self.panel.get_release_model():
            self.engine.unload()

    # ------------------------------------------------------------------
    # 预览渲染
    # ------------------------------------------------------------------
    def _render(self, fit: bool = True) -> None:
        if self.working_rgb is None:
            return
        source = self._display_source()
        if self.alpha is None:
            self.view.set_pil_image(source, fit=fit)
            return
        alpha_img = Image.fromarray(self.alpha)
        enabled, hex_color, opacity = self.tool_panel.get_bg_state()
        if enabled and self._active_tool == "bg":
            color = QColor(hex_color).getRgb()[:3]
            display = composite_background(
                source, alpha_img, color, opacity / 100.0
            )
        else:
            display = alpha_to_cutout(source, alpha_img)
        self.view.set_pil_image(display, fit=fit)
        self._refresh_compare(source, display)

    def _display_source(self) -> Image.Image:
        """当前用于显示/导出的前景图（去色边后优先）。"""
        return self.fg_rgb or self.working_rgb

    def _refresh_compare(self, original: Image.Image, result: Image.Image) -> None:
        if self.compare_enabled:
            base = (
                flatten_to_rgb(self.original_image)
                if self.original_image is not None
                else original
            )
            self.view.set_compare_images(
                _pil_to_pixmap(base),
                _pil_to_pixmap(result),
            )

    def _schedule_render(self) -> None:
        if not self._render_pending:
            self._render_pending = True
            self._render_timer.start()

    def _render_now(self) -> None:
        self._render_pending = False
        self._render(fit=False)

    # ------------------------------------------------------------------
    # 手动微调
    # ------------------------------------------------------------------
    def _on_tool_selected(self, tool: str) -> None:
        """左侧工具列切换：先退出上一个工具的全部预览，再激活新工具。"""
        if tool == self._active_tool and tool != "":
            tool = ""  # 再次点击当前工具 = 退出
        if tool:
            self._disable_compare()  # 进入工具自动退出对比，避免显示错乱
        self._exit_tool_previews()
        self._active_tool = tool
        if tool == "mask":
            self.tool_panel.set_active_tool("mask")
            self._schedule_overlay()
            self.status("笔刷遮罩：画前景 → 确定，保留画笔区域、删除其余")
        elif tool == "crop":
            self._set_crop_mode(True)
        elif tool == "preprocess":
            self.tool_panel.set_active_tool("preprocess")
            self.status("预处理：调整亮度/对比度/饱和度/色温，实时作用到当前图片")
        elif tool == "bg":
            self.tool_panel.set_active_tool("bg")
            self._render(fit=False)
            self.status("背景填充：此页实时预览，切换/退出工具后恢复透明预览，导出仍按此设置")
        elif tool == "retouch":
            if self.alpha is None:
                self._info(
                    "提示", "请先完成抠图，再用橡皮擦笔刷微调结果。"
                )
                self._active_tool = ""
                self.tool_panel.set_active_tool("")
                self.status("请先完成抠图")
                return
            self.tool_panel.set_active_tool("retouch")
            self.tool_panel.set_retouch_mode("erase")
            self._sync_brush_cursor()
            self.status("橡皮擦：擦除没抠干净的区域，或点「恢复」加回误删区域")
        else:
            self.tool_panel.set_active_tool("")
            self._render(fit=False)
            self.status("就绪")

    def _exit_tool_previews(self) -> None:
        """退出所有工具的预览状态：裁剪框、笔刷光标、遮罩叠加全部清除。"""
        self._crop_mode = False
        self.view.set_crop_mode(False)
        self._brush_mode = "none"
        self._retouch_mode = "none"
        self.view.set_brush_active(False)
        self.tool_panel.set_retouch_mode("none")
        self.tool_panel.set_brush_mode("none")
        self._schedule_overlay()

    def _exit_all_tools(self) -> None:
        """完全退出所有工具（含工具栏选中态），清空所有预览。"""
        self._active_tool = ""
        self.tool_panel.set_active_tool("")
        self._exit_tool_previews()
        self._disable_compare()

    def _disable_compare(self) -> None:
        if self.compare_enabled:
            self.compare_button.setChecked(False)

    def _on_brush_mode_changed(self, mode: str) -> None:
        self._last_stroke_xy = None
        self._mask_before = None
        if mode != "none":
            self._disable_compare()
            if self._active_tool != "mask":
                self._active_tool = "mask"
                self.tool_panel.set_active_tool("mask")
                self._crop_mode = False
                self.view.set_crop_mode(False)
                self._schedule_overlay()
        self._brush_mode = mode
        self.view.set_brush_active(mode != "none")
        self._sync_brush_cursor()

    def _sync_brush_cursor(self) -> None:
        if self._active_tool == "retouch":
            size, hardness, mode = self.tool_panel.get_retouch()
        else:
            size, hardness, mode = self.tool_panel.get_brush()
        self.view.set_brush_cursor(size, hardness / 100.0)
        if self._active_tool == "retouch":
            if mode != self._retouch_mode:
                self._retouch_mode = mode
                self.view.set_brush_active(mode != "none")
        else:
            if mode != self._brush_mode:
                self._brush_mode = mode
                self.view.set_brush_active(mode != "none")

    def _on_retouch_mode_changed(self, mode: str) -> None:
        """橡皮擦模式：erase=删除区域，add=恢复误删。"""
        self._last_stroke_xy = None
        if mode != "none":
            self._disable_compare()
            if self._active_tool != "retouch":
                self._active_tool = "retouch"
                self.tool_panel.set_active_tool("retouch")
                self._crop_mode = False
                self.view.set_crop_mode(False)
                self._schedule_overlay()
        self._retouch_mode = mode
        self.view.set_brush_active(mode != "none")
        self._sync_brush_cursor()

    def _on_retouch_stroke(self, x: float, y: float) -> None:
        if self.working_rgb is None or self.alpha is None or self._busy:
            return
        size, hardness, mode = self.tool_panel.get_retouch()
        if mode == "none":
            return
        radius = max(1, size // 2)
        hardness_f = hardness / 100.0
        prev = self._last_stroke_xy
        if prev is None:
            self._retouch_before = self.alpha.copy()
            paint_mask(self.alpha, x, y, radius, hardness_f, mode)
        else:
            dist = math.hypot(x - prev[0], y - prev[1])
            step = max(1.0, radius * 0.5)
            steps = min(64, max(1, int(math.ceil(dist / step))))
            for i in range(1, steps + 1):
                t = i / steps
                paint_mask(
                    self.alpha,
                    prev[0] + (x - prev[0]) * t,
                    prev[1] + (y - prev[1]) * t,
                    radius,
                    hardness_f,
                    mode,
                )
        self._last_stroke_xy = (x, y)
        self._schedule_render()

    def _on_retouch_finished(self) -> None:
        self._last_stroke_xy = None
        if self._retouch_before is not None:
            self.history.push(
                self.working_rgb,
                Image.fromarray(self._retouch_before),
                self.tool_panel.get_preprocess(),
            )
            self._retouch_before = None
            self.status("橡皮擦微调已应用（Ctrl+Z 可撤销）")
            self._update_ui_state()

    def _clear_mask_state(self) -> None:
        self._last_stroke_xy = None
        self._mask_before = None
        self.mask_prior = None
        self._schedule_overlay()
        if self.tool_panel.get_brush()[2] != "none":
            self.tool_panel.set_brush_mode("none")

    def _apply_mask_to_image(self) -> None:
        """画笔「确定」：保留画到的区域，其余删除，作为新的工作图。"""
        if self.working_rgb is None:
            return
        if self.mask_prior is None or self.mask_prior.max() <= 0:
            self._info(
                "提示", "请先用「画前景」涂抹要保留的区域，再点确定。"
            )
            return
        source = self._display_source()
        mask_img = Image.fromarray(self.mask_prior)
        cutout = keep_masked_region(source, mask_img)
        if self.alpha is not None:
            # 抠图后再用画笔：保留画笔区域内的抠图细节，区域外彻底删除
            self.history.push(
                self.working_rgb,
                Image.fromarray(self.alpha),
                self.tool_panel.get_preprocess(),
            )
            self.alpha = (
                self.alpha.astype(np.float32)
                * (self.mask_prior.astype(np.float32) / 255.0)
            ).astype(np.uint8)
        else:
            self.history.push(
                source, mask_img, self.tool_panel.get_preprocess()
            )
        self.working_rgb = cutout
        self.prep_source = cutout
        self.fg_rgb = None
        self._paint_changed = False
        # 保留画笔遮罩作为后续抠图的约束：
        # 点「开始抠图」时模型会在画笔区域内做精细边缘，而不是对整图盲猜
        self._exit_all_tools()
        self._render(fit=False)
        self.single_status.setText(
            "画笔区域已保留，其余已删除；点「开始抠图」会在画笔区域内精细抠图"
        )
        self.status("画笔区域已保留，其余已删除；可继续抠图精细边缘")
        self._update_ui_state()

    def _build_overlay(self) -> None:
        self._overlay_pending = False
        if self.working_rgb is None:
            return
        if self.mask_prior is None and not self._crop_mode:
            # 无遮罩且非裁剪模式：清掉旧 overlay，避免每次重建全尺寸透明图
            self.view.set_overlay(QPixmap())
            return
        w, h = self.working_rgb.size
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        if self.mask_prior is not None and self._active_tool == "mask":
            m = self.mask_prior
            strong = m >= 180
            weak = (m > 15) & ~strong
            arr[strong] = (56, 235, 120, 95)
            arr[weak] = (56, 235, 120, 45)
        qimg = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
        pixmap = QPixmap.fromImage(qimg)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._crop_mode:
            rect = self.view.crop_rect()
            if rect is not None:
                x0 = max(0, min(w, int(round(rect.left()))))
                y0 = max(0, min(h, int(round(rect.top()))))
                x1 = max(0, min(w, int(round(rect.right()))))
                y1 = max(0, min(h, int(round(rect.bottom()))))
                shade = QColor(0, 0, 0, 150)
                painter.fillRect(0, 0, w, y0, shade)
                painter.fillRect(0, y1, w, h - y1, shade)
                painter.fillRect(0, y0, x0, y1 - y0, shade)
                painter.fillRect(x1, y0, w - x1, y1 - y0, shade)
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.drawRect(x0, y0, x1 - x0, y1 - y0)
                grid_pen = QPen(QColor(255, 255, 255, 110), 1)
                grid_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(grid_pen)
                for i in (1, 2):
                    gx = x0 + (x1 - x0) * i / 3
                    gy = y0 + (y1 - y0) * i / 3
                    painter.drawLine(int(gx), y0, int(gx), y1)
                    painter.drawLine(x0, int(gy), x1, int(gy))
                hs = 9
                hx = (x0, (x0 + x1) // 2, x1)
                hy = (y0, (y0 + y1) // 2, y1)
                for cx in hx:
                    for cy in hy:
                        if cx == (x0 + x1) // 2 and cy == (y0 + y1) // 2:
                            continue
                        painter.fillRect(
                            cx - hs // 2, cy - hs // 2, hs, hs, QColor(76, 141, 255)
                        )
                        painter.setPen(QPen(QColor(255, 255, 255), 1.2))
                        painter.drawRect(cx - hs // 2, cy - hs // 2, hs, hs)
        painter.end()
        self.view.set_overlay(pixmap)

    # ------------------------------------------------------------------
    # 裁剪
    # ------------------------------------------------------------------
    def _set_crop_mode(self, active: bool) -> None:
        was_active = self._crop_mode
        self._crop_mode = bool(active)
        self.view.set_crop_mode(active)
        if active:
            self._disable_compare()
            self._active_tool = "crop"
            self.tool_panel.set_active_tool("crop")
            self._brush_mode = "none"
            self.tool_panel.set_brush_mode("none")
            self.status(
                "裁剪：拖动框选区域，拖动边角/边线调整，双击或 Enter 确定 / Esc 取消"
            )
        else:
            if was_active and self._active_tool == "crop":
                self._active_tool = ""
                self.tool_panel.set_active_tool("")
                self.status("已退出裁剪")
        self._schedule_overlay()

    def _on_crop_rect_changed(self) -> None:
        if self._crop_mode:
            rect = self.view.crop_rect()
            if rect is not None:
                self.tool_panel.set_crop_info(
                    f"区域：{int(round(rect.width()))} × {int(round(rect.height()))}"
                )
        self._schedule_overlay()

    def _confirm_crop(self) -> None:
        if not self._crop_mode or self.working_rgb is None:
            return
        rect = self.view.crop_rect()
        if rect is None or rect.width() < 16 or rect.height() < 16:
            self._info("提示", "裁剪区域太小，请重新框选。")
            return
        w, h = self.working_rgb.size
        x0 = max(0, min(w, int(round(rect.left()))))
        y0 = max(0, min(h, int(round(rect.top()))))
        x1 = max(0, min(w, int(round(rect.right()))))
        y1 = max(0, min(h, int(round(rect.bottom()))))
        self._apply_crop((x0, y0, x1, y1))

    def _cancel_crop(self) -> None:
        self._set_crop_mode(False)

    def _apply_crop(self, box: tuple[int, int, int, int]) -> None:
        if self.original_image is None:
            return
        x0, y0, x1, y1 = box
        had_alpha = self.alpha is not None
        # 裁剪前入栈：无论是否已抠图，都支持 Ctrl+Z / 左上角撤销按钮恢复
        self.history.push(
            self.working_rgb,
            Image.fromarray(self.alpha) if had_alpha else None,
            self.tool_panel.get_preprocess(),
            (
                Image.fromarray(self.mask_prior)
                if self.mask_prior is not None
                else None
            ),
            original=self.original_image,
        )
        self.original_image = self.original_image.crop((x0, y0, x1, y1))
        if self.prep_source is not None:
            self.prep_source = self.prep_source.crop((x0, y0, x1, y1))
        self.working_rgb = adjust_image(
            self.prep_source, **self.tool_panel.get_preprocess()
        )
        self.fg_rgb = None
        if had_alpha:
            self.alpha = self.alpha[y0:y1, x0:x1].copy()
        self._paint_changed = False
        self._clear_mask_state()
        self._set_crop_mode(False)
        self._reset_view_modes()
        self._render(fit=True)
        name = Path(self.current_path).name if self.current_path else ""
        self.file_info.setText(
            f"文件名：{name}\n尺寸：{self.working_rgb.width} × "
            f"{self.working_rgb.height}"
        )
        self._update_drop_preview()
        self.status(f"已裁剪到 {x1 - x0} × {y1 - y0}")
        self._update_ui_state()

    def _schedule_overlay(self) -> None:
        if not self._overlay_pending:
            self._overlay_pending = True
            self._overlay_timer.start()

    def _on_brush_stroke(self, x: float, y: float) -> None:
        if self._active_tool == "retouch":
            self._on_retouch_stroke(x, y)
            return
        if self.working_rgb is None or self._brush_mode == "none" or self._busy:
            return
        if self.mask_prior is None:
            h, w = self.working_rgb.height, self.working_rgb.width
            self.mask_prior = np.zeros((h, w), dtype=np.uint8)
        size, hardness, _ = self.tool_panel.get_brush()
        radius = max(1, size // 2)  # 画笔大小=直径，与实际涂抹范围一致
        hardness_f = hardness / 100.0
        prev = self._last_stroke_xy
        if prev is None:
            self._mask_before = self.mask_prior.copy()
            paint_mask(self.mask_prior, x, y, radius, hardness_f, self._brush_mode)
        else:
            # 两点间插值，快速拖动也不会断线、顶部边缘也能连续覆盖
            dist = math.hypot(x - prev[0], y - prev[1])
            step = max(1.0, radius * 0.5)
            steps = min(64, max(1, int(math.ceil(dist / step))))
            for i in range(1, steps + 1):
                t = i / steps
                paint_mask(
                    self.mask_prior,
                    prev[0] + (x - prev[0]) * t,
                    prev[1] + (y - prev[1]) * t,
                    radius,
                    hardness_f,
                    self._brush_mode,
                )
        self._last_stroke_xy = (x, y)
        self._paint_changed = True
        self._schedule_overlay()

    def _on_brush_finished(self) -> None:
        if self._active_tool == "retouch":
            self._on_retouch_finished()
            return
        self._last_stroke_xy = None
        if self._paint_changed:
            self._paint_changed = False
            if self._mask_before is not None:
                # 记录笔画前状态，Ctrl+Z 可撤销笔刷笔画
                alpha_img = (
                    Image.fromarray(self.alpha)
                    if self.alpha is not None
                    else None
                )
                self.history.push(
                    self.working_rgb,
                    alpha_img,
                    self.tool_panel.get_preprocess(),
                    Image.fromarray(self._mask_before),
                )
                self._mask_before = None
            self._schedule_overlay()
            self.status(f"笔刷遮罩已更新（覆盖 {int((self.mask_prior > 15).mean() * 100)}%）")
            self._update_ui_state()

    def _on_brush_size_wheel(self, size: int) -> None:
        """滚轮调整画笔大小时同步到属性栏滑块。"""
        if self._active_tool == "retouch":
            self.tool_panel.retouch_size.setValue(size)
        else:
            self.tool_panel.brush_size.setValue(size)
        self.status(f"画笔大小：{size}px")

    def _on_tool_action(self) -> None:
        """回车完成当前工具。"""
        if self._active_tool == "mask":
            self._apply_mask_to_image()
        elif self._active_tool == "crop":
            self._confirm_crop()

    def _apply_feather(self, radius: int) -> None:
        if self.alpha is None:
            self._info("提示", "请先完成抠图。")
            return
        if radius <= 0:
            return
        self.alpha = np.asarray(
            soften_alpha(Image.fromarray(self.alpha), float(radius)),
            dtype=np.uint8,
        ).copy()
        self.history.push(
            self.working_rgb,
            Image.fromarray(self.alpha),
            self.tool_panel.get_preprocess(),
        )
        self._render(fit=False)
        self.status("已应用边缘羽化")
        self._update_ui_state()

    def _invert_alpha(self) -> None:
        if self.alpha is None:
            self._info("提示", "请先完成抠图。")
            return
        self.alpha = (255 - self.alpha).astype(np.uint8)
        self.history.push(
            self.working_rgb,
            Image.fromarray(self.alpha),
            self.tool_panel.get_preprocess(),
        )
        self._render(fit=False)
        self.status("已反选遮罩")
        self._update_ui_state()

    def _on_alpha_view_toggled(self, enabled: bool) -> None:
        self.alpha_view = bool(enabled)
        self._render(fit=False)

    def _apply_defringe(self, radius: int) -> None:
        if self.alpha is None:
            self._info("提示", "请先完成抠图。")
            return
        alpha_img = Image.fromarray(self.alpha)
        self.history.push(
            self.working_rgb,
            alpha_img,
            self.tool_panel.get_preprocess(),
        )
        self.fg_rgb = defringe(self.working_rgb, alpha_img, int(radius))
        self._render(fit=False)
        self.status(f"已去除色边（半径 {radius}）")
        self._update_ui_state()

    def _on_zoom_changed(self, zoom: float) -> None:
        self.zoom_label.setText(f"{int(round(zoom * 100))}%")

    def _on_compare_toggled(self, checked: bool) -> None:
        self.compare_enabled = bool(checked)
        if checked:
            if self.alpha is None:
                self.compare_button.setChecked(False)
                self._info("提示", "请先完成抠图再对比。")
                return
            self._render(fit=False)
            self.view.set_compare_enabled(True)
            self.status("对比模式：拖动白色分割线查看原图与结果")
        else:
            self.view.set_compare_enabled(False)
            self._render(fit=False)

    def _cancel_current_task(self) -> None:
        for attr in ("_matte_task", "_batch_task"):
            task = getattr(self, attr, None)
            try:
                running = task is not None and task.isRunning()
            except RuntimeError:
                running = False
            if running:
                task.stop()
        self.status("正在取消任务…")

    # ------------------------------------------------------------------
    # 撤销 / 重做
    # ------------------------------------------------------------------
    def undo(self) -> None:
        snap = self.history.undo()
        if snap:
            self._restore_snapshot(snap)

    def redo(self) -> None:
        snap = self.history.redo()
        if snap:
            self._restore_snapshot(snap)

    def _restore_snapshot(self, snap) -> None:
        source, alpha_img, mask_img = snapshot_to_images(snap)
        original_img = snapshot_original_image(snap)
        self.working_rgb = source
        self.prep_source = source
        self.fg_rgb = None
        if original_img is not None:
            self.original_image = original_img
        self.alpha = (
            np.asarray(alpha_img, dtype=np.uint8).copy()
            if alpha_img is not None
            else None
        )
        if snap.preprocess is not None:
            self.tool_panel.set_preprocess(snap.preprocess)
        self._paint_changed = False
        self._clear_mask_state()
        if mask_img is not None:
            self.mask_prior = np.asarray(mask_img, dtype=np.uint8).copy()
        self._render(fit=False)
        self.status("已恢复操作记录")
        if original_img is not None:
            name = Path(self.current_path).name if self.current_path else ""
            self.file_info.setText(
                f"文件名：{name}\n尺寸：{self.working_rgb.width} × "
                f"{self.working_rgb.height}"
            )
            self._update_drop_preview()
        self._update_ui_state()

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------
    def save_current(self) -> None:
        if self.alpha is None:
            self._info("提示", "请先完成抠图再保存。")
            return
        if not self.current_path:
            return
        fmt, suffix, quality, save_dir, _ = self.panel.get_output_settings()
        suffix = ensure_supported_suffix(suffix)
        out_dir = save_dir or str(Path(self.current_path).parent)
        out_path = build_output_path(self.current_path, out_dir, suffix, fmt)
        alpha_img = Image.fromarray(self.alpha)
        source = self._display_source()
        enabled, hex_color, opacity = self.tool_panel.get_bg_state()
        color = QColor(hex_color).getRgb()[:3]
        try:
            if fmt == "png":
                if enabled:
                    image = composite_background(
                        source, alpha_img, color, opacity / 100.0
                    )
                else:
                    image = alpha_to_cutout(source, alpha_img)
            else:
                image = opaque_over_white(
                    source, alpha_img, opacity / 100.0 if enabled else 1.0
                )
            save_image(image, out_path, fmt, quality)
        except Exception as exc:  # noqa: BLE001
            self._critical("保存失败", f"导出失败：\n{exc}")
            return
        self.status(f"已保存：{out_path}")
        box = MessageBox("保存完成", f"已保存到：\n{out_path}", self)
        box.yesButton.setText("打开所在文件夹")
        box.cancelButton.setText("确定")
        if box.exec():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(out_path).parent)))

    # ------------------------------------------------------------------
    # 批量
    # ------------------------------------------------------------------
    def _start_batch(self, options: BatchOptions) -> None:
        if self._busy:
            return
        if not options.files:
            self._info("提示", "请先在列表中添加要处理的图片。")
            return
        model_path = self._current_model_path()
        if not model_path:
            self._warn(
                "缺少模型", "尚未下载抠图模型，请先在「模型管理」中下载。"
            )
            self.open_model_manager()
            return
        self.engine.set_model_path(model_path)
        enabled, hex_color, opacity = self.tool_panel.get_bg_state()
        options.bg_enabled = enabled
        options.bg_color = QColor(hex_color).getRgb()[:3]
        options.bg_opacity = opacity / 100.0
        options.preprocess = self.tool_panel.get_preprocess()
        options.suffix = ensure_supported_suffix(options.suffix)
        options.max_side = self.panel.get_output_settings()[4]
        options.overrides = self.batch_panel.overrides()

        self._set_busy(True)
        self.batch_panel.set_running(True)
        self.batch_panel.set_progress(0, len(options.files))
        self.batch_panel.set_summary(f"处理中：0/{len(options.files)}")
        self.status(f"批量处理开始：{len(options.files)} 张")
        self._batch_task = BatchTask(self.engine, options, self)
        self._batch_task.overall_progress.connect(self._on_batch_progress)
        self._batch_task.file_status.connect(self._on_batch_file_status)
        self._batch_task.finished_ok.connect(self._on_batch_done)
        self._batch_task.failed.connect(self._on_batch_failed)
        self._batch_task.finished.connect(self._batch_task.deleteLater)
        self._batch_task.start()

    def _stop_batch(self) -> None:
        if self._batch_task:
            self._batch_task.stop()
            self.batch_panel.set_summary("正在停止…")

    def _on_batch_progress(self, done: int, total: int) -> None:
        self.batch_panel.set_progress(done, total)
        self.batch_panel.set_summary(f"处理中：{done}/{total}")
        self.status(f"批量处理：{done}/{total}")

    def _on_batch_file_status(self, index: int, name: str, text: str) -> None:
        self.batch_panel.set_status(index, text)

    def _on_batch_done(self, success: int, failed: int, elapsed: float) -> None:
        self._set_busy(False)
        self.batch_panel.set_running(False)
        text = f"完成：成功 {success} 张，失败 {failed} 张，耗时 {elapsed:.1f} 秒"
        self.batch_panel.set_summary(text)
        self.status(text)
        self._release_engine_memory()

    def _retry_failed_batch(self) -> None:
        if self._busy:
            return
        failed = self.batch_panel.failed_rows()
        if not failed:
            self._info("提示", "没有失败项可重试。")
            return
        self.batch_panel.set_progress(0, len(failed))
        options = BatchOptions(
            files=failed,
            out_dir=self.batch_panel.dir_edit.text().strip(),
            fmt=str(self.batch_panel.format_combo.currentData()),
            suffix=self.batch_panel.suffix_edit.text().strip(),
            quality=self.batch_panel.quality_spin.value(),
        )
        for i in range(self.batch_panel.file_list.count()):
            path = self.batch_panel.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            if path in failed:
                self.batch_panel.set_status(i, "等待重试…")
        self._start_batch(options)

    def _on_batch_failed(self, message: str) -> None:
        self._set_busy(False)
        self.batch_panel.set_running(False)
        self.batch_panel.set_summary(f"批量任务失败：{message}")
        self._critical("批量任务失败", message)
        self._release_engine_memory()

    def _open_batch_edit(self, row: int) -> None:
        files = self.batch_panel.files()
        if 0 <= row < len(files):
            self.switchTo(self.single_interface)
            self.import_image(files[row])

    # ------------------------------------------------------------------
    # 模型管理
    # ------------------------------------------------------------------
    def _current_model_path(self):
        model_id = self.settings.get("model_id", "")
        if model_id in MODEL_REGISTRY:
            path = model_file_path(model_id)
            if path.exists():
                return path
        elif model_id:
            path = Path(model_id)
            if path.exists():
                return path
        # 回退：使用第一个已下载的注册模型
        for mid in MODEL_REGISTRY:
            path = model_file_path(mid)
            if path.exists():
                return path
        return None

    def _set_engine_model_path(self) -> None:
        self.engine.set_model_path(self._current_model_path())

    def _preload_default_model(self) -> None:
        """后台自动加载当前默认模型，让首次抠图不用等加载。"""
        if os.environ.get("AIMATTING_NO_PRELOAD"):
            return
        if self._preload_task is not None and self._preload_task.isRunning():
            return
        path = self._current_model_path()
        if not path:
            return
        if self.engine.loaded:
            self.status(f"模型已就绪（{self.engine.provider}）")
            return
        self.engine.set_model_path(path)
        self._preload_task = ModelPreloadTask(self.engine, str(path), parent=self)
        self._preload_task.done.connect(self._on_model_preloaded)
        self._preload_task.failed.connect(self._on_model_preload_failed)
        self._preload_task.finished.connect(
            lambda: setattr(self, "_preload_task", None)
        )
        self._preload_task.start()
        self.status("正在后台加载模型…")

    def _on_model_preloaded(self, provider: str) -> None:
        self.status(f"模型已就绪（{provider}）")
        self._warn_slow_inference(provider)

    def _warn_slow_inference(self, provider: str) -> None:
        """CPU + HR 大模型组合速度较慢，给出可操作的提示。"""
        if provider != "CPU":
            return
        model_id = self.settings.get("model_id", "")
        if model_id == "birefnet_hr_matting":
            self.status(
                "当前为 CPU 推理且使用 HR 大模型，速度较慢；"
                "建议切换「BiRefNet lite 2K」或调低推理分辨率"
            )

    def _on_model_preload_failed(self, message: str) -> None:
        self.status(f"模型预加载失败（{message[:40]}…），抠图时会自动重试")

    def open_model_manager(self) -> None:
        model_id = self.settings.get("model_id", "")
        if model_id not in MODEL_REGISTRY:
            model_id = next(iter(MODEL_REGISTRY))
        dialog = ModelManagerDialog(model_id, self)
        dialog.model_changed.connect(self._on_model_changed)
        dialog.exec()

    def _on_model_changed(self, model_id: str) -> None:
        self.settings.set("model_id", model_id)
        self.settings.save()
        self.engine.unload()
        self._set_engine_model_path()
        self._preload_default_model()
        self.model_combo.blockSignals(True)
        index = self.model_combo.findData(model_id)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        self.model_combo.blockSignals(False)
        self._update_model_label()
        self.status("模型已更新，可开始抠图")

    def _update_model_label(self) -> None:
        model_id = self.settings.get("model_id", "")
        if model_id in MODEL_REGISTRY:
            label = MODEL_REGISTRY[model_id]["name"].split("（")[0]
        elif model_id:
            label = Path(model_id).stem
        else:
            label = "未下载模型"
        text = f"模型：{label}｜引擎：{self.engine.provider}"
        for model_label in self._model_labels:
            model_label.setText(text)

    # ------------------------------------------------------------------
    # 教程 / 关于
    # ------------------------------------------------------------------
    def open_tutorial(self) -> None:
        TutorialDialog(self).exec()

    def open_about(self) -> None:
        AboutDialog(self).exec()

    # ------------------------------------------------------------------
    # 拖拽
    # ------------------------------------------------------------------
    def _drop_enter(self, event) -> None:
        if event.mimeData().hasUrls() and any(
            is_supported(url.toLocalFile()) for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()

    def _drop(self, event) -> None:
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if is_supported(url.toLocalFile())
        ]
        if not paths:
            return
        if self.stackedWidget.currentWidget() is self.batch_panel:
            self.batch_panel.add_paths(paths)
            self.status(f"已加入批量列表：{len(paths)} 张")
        else:
            self.import_image(paths[0])
        event.acceptProposedAction()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        self._drop_enter(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        self._drop(event)

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------
    def status(self, text: str) -> None:
        for status_label in self._status_labels:
            status_label.setText(text)

    def _info(self, title: str, content: str) -> None:
        MessageBox(title, content, self).exec()

    def _warn(self, title: str, content: str) -> None:
        box = MessageBox(title, content, self)
        box.yesButton.setText("知道了")
        box.exec()

    def _critical(self, title: str, content: str) -> None:
        box = MessageBox(title, content, self)
        box.yesButton.setText("知道了")
        box.exec()

    def _question(self, title: str, content: str) -> bool:
        box = MessageBox(title, content, self)
        box.yesButton.setText("是")
        box.cancelButton.setText("否")
        return box.exec()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.import_action.setEnabled(not busy)
        self.import_button.setEnabled(not busy)
        self.undo_action.setEnabled(not busy)
        self.redo_action.setEnabled(not busy)
        self.panel.matte_button.setEnabled(not busy)
        self.panel.save_button.setEnabled(not busy)
        self.tool_panel.set_tools_enabled(not busy)
        self.batch_panel.add_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.model_combo.setEnabled(not busy)
        self._sync_action_buttons()

    def _update_ui_state(self) -> None:
        has_image = self.original_image is not None
        has_alpha = self.alpha is not None
        self.panel.matte_button.setEnabled(has_image and not self._busy)
        self.panel.save_button.setEnabled(has_alpha and not self._busy)
        self.import_action.setEnabled(not self._busy)
        self.import_button.setEnabled(not self._busy)
        self.undo_action.setEnabled(self.history.can_undo() and not self._busy)
        self.redo_action.setEnabled(self.history.can_redo() and not self._busy)
        self.panel.feather_button.setEnabled(has_alpha and not self._busy)
        self.panel.defringe_button.setEnabled(has_alpha and not self._busy)
        self.compare_button.setEnabled(has_alpha and not self._busy)
        self.tool_panel.set_tools_enabled(has_image and not self._busy)
        self._sync_action_buttons()

    # ------------------------------------------------------------------
    # 启动与退出
    # ------------------------------------------------------------------
    def _startup_model_check(self) -> None:
        if self._current_model_path():
            # 配置指向的模型缺失但存在其他可用模型时，自动切换配置
            model_id = self.settings.get("model_id", "")
            configured_ok = (
                model_id in MODEL_REGISTRY
                and model_file_path(model_id).exists()
            ) or (model_id and Path(model_id).exists())
            if not configured_ok:
                for mid in MODEL_REGISTRY:
                    if model_file_path(mid).exists():
                        self.settings.set("model_id", mid)
                        self.settings.save()
                        self._update_model_label()
                        break
            return
        QTimer.singleShot(300, self._prompt_model)

    def _prompt_model(self) -> None:
        if self._question(
            "模型未下载",
            "抠图功能需要 BiRefNet 模型（约 1GB）。是否现在打开「模型管理」下载？",
        ):
            self.open_model_manager()

    def _persist_settings(self) -> None:
        settings = self.settings
        enabled, hex_color, opacity = self.tool_panel.get_bg_state()
        settings.set("bg_enabled", enabled)
        settings.set("bg_color", hex_color)
        settings.set("bg_opacity", opacity)
        fmt, suffix, quality, save_dir, max_side = self.panel.get_output_settings()
        settings.set("output_format", fmt)
        settings.set("output_suffix", suffix)
        settings.set("quality", quality)
        settings.set("save_dir", save_dir)
        settings.set("infer_max_side", max_side)
        settings.set("release_model_after_matte", self.panel.get_release_model())
        settings.set_preprocess(self.tool_panel.get_preprocess())
        size, hardness, _ = self.tool_panel.get_brush()
        settings.set("brush_size", size)
        settings.set("brush_hardness", hardness)
        r_size, r_hardness, _ = self.tool_panel.get_retouch()
        settings.set("retouch_size", r_size)
        settings.set("retouch_hardness", r_hardness)
        settings.save()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._persist_settings()
        preload = self._preload_task
        try:
            still_running = preload is not None and preload.isRunning()
        except RuntimeError:
            still_running = False
        if still_running:
            preload.wait(1500)
        if not still_running:
            self.engine.unload()
        self.engine.shutdown()
        self.original_image = None
        self.prep_source = None
        self.working_rgb = None
        self.fg_rgb = None
        self.alpha = None
        self.mask_prior = None
        self.history.clear()
        self.view.clear_image()
        gc.collect()
        super().closeEvent(event)
