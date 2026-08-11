"""左侧工具列 + 右侧参数面板（qfluentwidgets 现代化组件）。"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    ComboBox,
    FluentIcon,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    Slider,
    SpinBox,
    TabWidget,
    ToggleToolButton,
)

from aimatting.core.image_ops import PRESET_COLORS
from aimatting.core.io_utils import FORMAT_LABELS


def _slider_row(
    title: str,
    value: int = 0,
    minimum: int = -100,
    maximum: int = 100,
    suffix: str = "",
) -> tuple[QWidget, Slider, CaptionLabel]:
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    label = CaptionLabel(title)
    label.setFixedWidth(64)
    slider = Slider(Qt.Orientation.Horizontal)
    slider.setRange(minimum, maximum)
    slider.setValue(value)
    value_label = CaptionLabel(f"{value}{suffix}")
    value_label.setFixedWidth(48)
    value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
    slider.valueChanged.connect(lambda v: value_label.setText(f"{v}{suffix}"))
    layout.addWidget(label)
    layout.addWidget(slider, 1)
    layout.addWidget(value_label)
    return box, slider, value_label


def _is_dark(hex_color: str) -> bool:
    color = QColor(hex_color)
    return (color.red() * 299 + color.green() * 587 + color.blue() * 114) < 150000


# ---------- 工具图标（纯矢量绘制，随主题状态变色） ----------
def _paint_icon(draw, color: QColor) -> QPixmap:
    pm = QPixmap(28, 28)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(
        color,
        2.4,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    draw(painter, color)
    painter.end()
    return pm


def _draw_mask_icon(p, color: QColor) -> None:
    p.drawLine(QPointF(5, 23), QPointF(17, 11))  # 笔杆
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(20.5, 7.5), 3.4, 3.4)  # 笔尖


def _draw_crop_icon(p, color: QColor) -> None:
    p.drawLine(QPointF(4, 9), QPointF(10, 9))  # 左上角
    p.drawLine(QPointF(9, 9), QPointF(9, 20))
    p.drawLine(QPointF(24, 19), QPointF(18, 19))  # 右下角
    p.drawLine(QPointF(19, 19), QPointF(19, 8))


def _draw_preprocess_icon(p, color: QColor) -> None:
    for y in (7, 13, 19):
        p.drawLine(QPointF(4, y), QPointF(24, y))
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(16, 7), 2.6, 2.6)
    p.drawEllipse(QPointF(9, 13), 2.6, 2.6)
    p.drawEllipse(QPointF(19, 19), 2.6, 2.6)


def _draw_bg_icon(p, color: QColor) -> None:
    # 油漆桶：滴落 + 桶身
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(21.5, 5.5), 2.0, 2.0)
    p.setPen(
        QPen(
            color,
            2.2,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
    )
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(16.5, 9), QPointF(20, 5.5))
    p.drawLine(QPointF(16.5, 9), QPointF(16.5, 14))
    p.drawRoundedRect(QRectF(5.5, 14, 15, 9), 2.5, 2.5)


def _draw_retouch_icon(p, color: QColor) -> None:
    # 橡皮擦：斜向擦体 + 斜线
    p.drawLine(QPointF(13, 4), QPointF(25, 16))
    p.drawRoundedRect(QRectF(3.5, 12, 16, 10), 2.5, 2.5)
    p.drawLine(QPointF(7, 18), QPointF(21, 18))


def _tool_icon(kind: str) -> QIcon:
    draws = {
        "mask": _draw_mask_icon,
        "crop": _draw_crop_icon,
        "preprocess": _draw_preprocess_icon,
        "bg": _draw_bg_icon,
        "retouch": _draw_retouch_icon,
    }
    draw = draws[kind]
    icon = QIcon()
    icon.addPixmap(_paint_icon(draw, QColor("#9AA0AC")), QIcon.Mode.Normal)
    icon.addPixmap(_paint_icon(draw, QColor("#4C8DFF")), QIcon.Mode.Active)
    icon.addPixmap(_paint_icon(draw, QColor("#FFFFFF")), QIcon.Mode.Selected)
    return icon


def _circular_arrow_icon(direction: str) -> QIcon:
    """撤销/重做：圆圈箭头（↶ / ↷）。"""
    glyph = "↶" if direction == "undo" else "↷"

    def draw(p, color: QColor) -> None:
        from PySide6.QtGui import QFont

        font = QFont("Segoe UI Symbol", 15)
        p.setFont(font)
        p.setPen(QPen(color, 1))
        p.drawText(
            QRectF(0, 0, 28, 28),
            Qt.AlignmentFlag.AlignCenter,
            glyph,
        )

    icon = QIcon()
    icon.addPixmap(_paint_icon(draw, QColor("#E6E8EE")), QIcon.Mode.Normal)
    icon.addPixmap(_paint_icon(draw, QColor("#4C8DFF")), QIcon.Mode.Active)
    icon.addPixmap(_paint_icon(draw, QColor("#4C8DFF")), QIcon.Mode.Selected)
    return icon


# 工具按钮的 Fluent 图标映射
_TOOL_FLUENT_ICONS = {
    "mask": FluentIcon.BRUSH,
    "crop": FluentIcon.CLIPPING_TOOL,
    "preprocess": FluentIcon.CONSTRACT,
    "bg": FluentIcon.BACKGROUND_FILL,
    "retouch": FluentIcon.ERASE_TOOL,
}


def _muted_note(text: str) -> CaptionLabel:
    label = CaptionLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
    return label


class ToolPanel(QWidget):
    """左侧工具列：笔刷遮罩 / 裁剪 / 预处理 / 背景填充。"""

    tool_selected = Signal(str)  # "mask" / "crop" / "preprocess" / "bg" / ""
    mask_mode_changed = Signal(str)  # "add" / "erase" / "none"
    mask_clear_requested = Signal()
    brush_params_changed = Signal()
    mask_apply_requested = Signal()
    retouch_mode_changed = Signal(str)  # "erase" / "add" / "none"
    retouch_params_changed = Signal()
    crop_confirm_requested = Signal()
    crop_cancel_requested = Signal()
    preprocess_changed = Signal()
    preprocess_commit = Signal()
    bg_changed = Signal()

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._current_hex = "#4CAF50"
        self._color_widgets: list[QWidget] = []
        self._build_ui()
        self._apply_settings_to_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 8, 6, 4)
        root.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        title = CaptionLabel("工具")
        title.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        bar.addWidget(title)
        bar.addStretch(1)
        root.addLayout(bar)

        # 图标工具栏：悬停有说明，点击后下方出现属性栏
        icon_row = QHBoxLayout()
        icon_row.setSpacing(6)
        tool_specs = (
            (
                "mask",
                "笔刷遮罩",
                "涂抹主体区域，点「确定」只保留画笔部分、删除其余",
            ),
            ("crop", "裁剪", "框选要保留的区域，Enter 确定 / Esc 取消"),
            ("preprocess", "预处理", "调整亮度/对比度/饱和度/色温，实时作用到当前图片"),
            ("bg", "背景填充", "为抠图结果合成纯色背景（预览与导出）"),
            ("retouch", "橡皮擦", "抠图后微调：擦除没抠干净的区域，或恢复误删的区域"),
        )

        self._tool_buttons: dict[str, ToggleToolButton] = {}
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(False)
        for key, name, tip in tool_specs:
            btn = ToggleToolButton(_TOOL_FLUENT_ICONS[key], self)
            btn.setIconSize(QSize(22, 22))
            btn.setFixedSize(36, 36)
            btn.setToolTip(f"{name}：{tip}")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, k=key: self._tool_clicked(k))
            self._tool_group.addButton(btn)
            icon_row.addWidget(btn)
            self._tool_buttons[key] = btn

        icon_row.addStretch(1)
        root.addLayout(icon_row)

        # 属性栏：显示当前工具的详细设置
        self._property_title = BodyLabel("选择工具开始编辑")
        self._property_title.setObjectName("PropertyTitle")
        self._property_title.setWordWrap(True)
        self._property_title.setStyleSheet(
            "color: rgba(255, 255, 255, 0.85); padding: 2px 4px;"
        )
        root.addWidget(self._property_title)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_mask_page())
        self._stack.addWidget(self._build_crop_page())
        self._stack.addWidget(self._build_preprocess_page())
        self._stack.addWidget(self._build_bg_page())
        self._stack.addWidget(self._build_retouch_page())
        root.addWidget(self._stack, 1)
        root.addStretch(0)

    def _tool_clicked(self, key: str) -> None:
        if self._tool_buttons[key].isChecked():
            self.tool_selected.emit(key)
        else:
            self.tool_selected.emit("")

    def set_active_tool(self, tool: str) -> None:
        for key, btn in self._tool_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(key == tool)
            btn.blockSignals(False)
        self._stack.setVisible(bool(tool))
        titles = {
            "mask": "笔刷遮罩：画前景 → 确定",
            "crop": "裁剪：框选保留区域",
            "preprocess": "预处理：实时作用当前图片",
            "bg": "背景填充：预览与导出设置",
            "retouch": "橡皮擦：擦除 / 恢复抠图区域",
        }
        self._property_title.setText(titles.get(tool, "选择工具开始编辑"))
        self._property_title.setVisible(bool(tool))
        index = {
            "mask": 0,
            "crop": 1,
            "preprocess": 2,
            "bg": 3,
            "retouch": 4,
        }.get(tool, -1)
        if index >= 0:
            self._stack.setCurrentIndex(index)
        if tool:
            self._fade_in_stack()

    def _fade_in_stack(self) -> None:
        """属性栏切换时轻微淡入，交互更顺滑。"""
        effect = QGraphicsOpacityEffect(self._stack)
        self._stack.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(150)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self._stack.setGraphicsEffect(None))
        anim.finished.connect(anim.deleteLater)
        anim.start()

    # ---------- 笔刷遮罩 ----------
    def _build_mask_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        tool_row = QHBoxLayout()
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.btn_mask_add = PushButton("画前景")
        self.btn_mask_erase = PushButton("擦除")
        self.btn_mask_none = PushButton("浏览")
        for btn in (self.btn_mask_add, self.btn_mask_erase, self.btn_mask_none):
            btn.setCheckable(True)
            self.tool_group.addButton(btn)
            tool_row.addWidget(btn)
        self.btn_mask_none.setChecked(True)
        layout.addLayout(tool_row)

        size_row, self.brush_size, _ = _slider_row("画笔大小", 60, 1, 500, "px")
        layout.addWidget(size_row)
        hard_row, self.brush_hardness, _ = _slider_row("画笔硬度", 70, 0, 100, "%")
        layout.addWidget(hard_row)

        self.mask_clear_button = PushButton("清除遮罩")
        layout.addWidget(self.mask_clear_button)

        self.mask_apply_button = PrimaryPushButton("确定（保留画笔区域，删除其余）")
        self.mask_apply_button.setMinimumHeight(34)
        layout.addWidget(self.mask_apply_button)

        note = _muted_note(
            "用法：用「画前景」沿主体大致涂一遍，点「确定」后，"
            "画到的部分保留、其余删除；涂错的地方用「擦除」。"
        )
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    # ---------- 裁剪 ----------
    def _build_crop_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        self.crop_info = BodyLabel("在预览图上框选要保留的区域")
        self.crop_info.setWordWrap(True)
        layout.addWidget(self.crop_info)

        row = QHBoxLayout()
        self.crop_ok_button = PrimaryPushButton("确定")
        self.crop_cancel_button = PushButton("取消")
        row.addWidget(self.crop_ok_button)
        row.addWidget(self.crop_cancel_button)
        layout.addLayout(row)

        note = _muted_note(
            "进入裁剪后自动选中整张图：拖动框体移动，拖动边角/边线调整大小，"
            "Enter 确定、Esc 取消。"
        )
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def set_crop_info(self, text: str) -> None:
        self.crop_info.setText(text)

    # ---------- 预处理 ----------
    def _build_preprocess_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)
        self.prep_sliders: dict[str, Slider] = {}
        for key, title in (
            ("brightness", "亮度"),
            ("contrast", "对比度"),
            ("saturation", "饱和度"),
            ("temperature", "色温"),
        ):
            row, slider, _ = _slider_row(title)
            self.prep_sliders[key] = slider
            layout.addWidget(row)
        reset = PushButton("恢复默认")
        layout.addWidget(reset)
        reset.clicked.connect(self._reset_preprocess)
        note = _muted_note("调整会实时作用到当前图片，点「开始抠图」时基于调整后的图。")
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    # ---------- 背景填充 ----------
    def _build_bg_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        self.bg_enabled = CheckBox("启用纯色背景填充")
        layout.addWidget(self.bg_enabled)

        color_grid = QGridLayout()
        color_grid.setContentsMargins(0, 0, 0, 0)
        color_grid.setHorizontalSpacing(4)
        color_grid.setVerticalSpacing(4)
        self._color_widgets.clear()
        for idx, (label, hex_color) in enumerate(PRESET_COLORS.items()):
            btn = PushButton(label)
            btn.setFixedSize(44, 28)
            btn.setToolTip(f"{label} {hex_color}")
            text_color = "#FFFFFF" if _is_dark(hex_color) else "#000000"
            btn.setStyleSheet(
                f"PushButton {{ background: {hex_color}; color: {text_color};"
                " border: 1px solid #999; padding: 0px; }"
            )
            btn.clicked.connect(lambda _=False, h=hex_color: self._set_color(h))
            self._color_widgets.append(btn)
            color_grid.addWidget(btn, idx // 5, idx % 5)
        layout.addLayout(color_grid)

        custom_row = QHBoxLayout()
        self.color_preview = PushButton("自定义颜色")
        self.color_preview.setFixedSize(90, 30)
        custom_row.addWidget(self.color_preview)
        self.pipette_button = PushButton("吸管")
        self.pipette_button.setFixedWidth(56)
        self.pipette_button.setToolTip("从屏幕任意位置取色")
        custom_row.addWidget(self.pipette_button)
        self.hex_edit = LineEdit()
        self.hex_edit.setMaxLength(9)
        self.hex_edit.setPlaceholderText("#RRGGBB")
        custom_row.addWidget(self.hex_edit, 1)
        layout.addLayout(custom_row)

        rgb_grid = QGridLayout()
        self.rgb_spins: dict[str, SpinBox] = {}
        for col, name in enumerate(("R", "G", "B")):
            label = CaptionLabel(name)
            spin = SpinBox()
            spin.setRange(0, 255)
            spin.setKeyboardTracking(False)
            self.rgb_spins[name] = spin
            rgb_grid.addWidget(label, 0, col)
            rgb_grid.addWidget(spin, 1, col)
        layout.addLayout(rgb_grid)

        opacity_row, self.opacity_slider, self.opacity_label = _slider_row(
            "不透明度", 100, 0, 100, "%"
        )
        layout.addWidget(opacity_row)

        note = _muted_note(
            "此页为实时预览；切换/退出工具后预览恢复为透明效果，"
            "导出时仍按这里的选择合成。"
        )
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    # ---------- 橡皮擦（手动微调） ----------
    def _build_retouch_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        tool_row = QHBoxLayout()
        self.retouch_group = QButtonGroup(self)
        self.retouch_group.setExclusive(True)
        self.btn_retouch_erase = PushButton("擦除")
        self.btn_retouch_add = PushButton("恢复")
        for btn in (self.btn_retouch_erase, self.btn_retouch_add):
            btn.setCheckable(True)
            self.retouch_group.addButton(btn)
            tool_row.addWidget(btn)
        self.btn_retouch_erase.setChecked(True)
        layout.addLayout(tool_row)

        size_row, self.retouch_size, _ = _slider_row("画笔大小", 60, 1, 500, "px")
        layout.addWidget(size_row)
        hard_row, self.retouch_hardness, _ = _slider_row("画笔硬度", 70, 0, 100, "%")
        layout.addWidget(hard_row)

        note = _muted_note(
            "擦除：去掉没抠干净的多余区域；恢复：加回误删的区域。"
            "涂抹立即生效，可用 Ctrl+Z 撤销。"
        )
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    # ---------- 状态读写 ----------
    def _apply_settings_to_ui(self) -> None:
        self._set_color(str(self._settings.get("bg_color", "#4CAF50")), push=False)
        self.opacity_slider.setValue(int(self._settings.get("bg_opacity", 100)))
        self.bg_enabled.setChecked(bool(self._settings.get("bg_enabled", True)))
        prep = self._settings.get_preprocess()
        for key, slider in self.prep_sliders.items():
            slider.setValue(int(prep.get(key, 0)))
        self.brush_size.setValue(int(self._settings.get("brush_size", 60)))
        self.brush_hardness.setValue(int(self._settings.get("brush_hardness", 70)))
        self.retouch_size.setValue(int(self._settings.get("retouch_size", 60)))
        self.retouch_hardness.setValue(
            int(self._settings.get("retouch_hardness", 70))
        )

    def _connect_signals(self) -> None:
        self.bg_enabled.toggled.connect(lambda _: self.bg_changed.emit())
        self.opacity_slider.valueChanged.connect(lambda _: self.bg_changed.emit())
        self.color_preview.clicked.connect(self.pick_custom_color)
        self.pipette_button.clicked.connect(self.pick_screen_color)
        self.hex_edit.editingFinished.connect(self._apply_hex)
        for spin in self.rgb_spins.values():
            spin.valueChanged.connect(self._rgb_to_hex)
        for slider in self.prep_sliders.values():
            slider.valueChanged.connect(lambda _: self.preprocess_changed.emit())
            slider.sliderReleased.connect(self.preprocess_commit.emit)
        self.tool_group.buttonClicked.connect(self._mask_tool_clicked)
        self.retouch_group.buttonClicked.connect(self._retouch_tool_clicked)
        self.brush_size.valueChanged.connect(lambda _: self.brush_params_changed.emit())
        self.brush_hardness.valueChanged.connect(
            lambda _: self.brush_params_changed.emit()
        )
        self.retouch_size.valueChanged.connect(
            lambda _: self.retouch_params_changed.emit()
        )
        self.retouch_hardness.valueChanged.connect(
            lambda _: self.retouch_params_changed.emit()
        )
        self.mask_clear_button.clicked.connect(self.mask_clear_requested.emit)
        self.mask_apply_button.clicked.connect(self.mask_apply_requested.emit)
        self.crop_ok_button.clicked.connect(self.crop_confirm_requested.emit)
        self.crop_cancel_button.clicked.connect(self.crop_cancel_requested.emit)

    def _mask_tool_clicked(self, btn) -> None:
        if btn is self.btn_mask_add:
            self.mask_mode_changed.emit("add")
        elif btn is self.btn_mask_erase:
            self.mask_mode_changed.emit("erase")
        else:
            self.mask_mode_changed.emit("none")

    def _retouch_tool_clicked(self, btn) -> None:
        if btn is self.btn_retouch_erase:
            self.retouch_mode_changed.emit("erase")
        elif btn is self.btn_retouch_add:
            self.retouch_mode_changed.emit("add")
        else:
            self.retouch_mode_changed.emit("none")

    def get_retouch(self) -> tuple[int, int, str]:
        if self.btn_retouch_erase.isChecked():
            mode = "erase"
        elif self.btn_retouch_add.isChecked():
            mode = "add"
        else:
            mode = "none"
        return self.retouch_size.value(), self.retouch_hardness.value(), mode

    def set_retouch_mode(self, mode: str) -> None:
        self.retouch_group.blockSignals(True)
        if mode == "erase":
            self.btn_retouch_erase.setChecked(True)
            self.btn_retouch_add.setChecked(False)
        elif mode == "add":
            self.btn_retouch_add.setChecked(True)
            self.btn_retouch_erase.setChecked(False)
        else:
            self.btn_retouch_erase.setChecked(False)
            self.btn_retouch_add.setChecked(False)
        self.retouch_group.blockSignals(False)
        self.retouch_mode_changed.emit(mode)

    def set_tools_enabled(self, enabled: bool) -> None:
        for btn in self._tool_buttons.values():
            btn.setEnabled(enabled)
        for btn in (self.btn_mask_add, self.btn_mask_erase, self.btn_mask_none):
            btn.setEnabled(enabled)
        self.mask_clear_button.setEnabled(enabled)
        self.mask_apply_button.setEnabled(enabled)
        self.btn_retouch_erase.setEnabled(enabled)
        self.btn_retouch_add.setEnabled(enabled)
        self.crop_ok_button.setEnabled(enabled)
        self.crop_cancel_button.setEnabled(enabled)

    # ---------- 颜色 ----------
    def _set_color(self, color, push: bool = True) -> None:
        if not isinstance(color, QColor):
            color = QColor(str(color))
        if not color.isValid():
            return
        self._current_hex = color.name().upper()
        self.hex_edit.setText(self._current_hex)
        self.color_preview.setStyleSheet(
            f"PushButton {{ background: {self._current_hex};"
            " border: 1px solid #999; }"
        )
        self.rgb_spins["R"].setValue(color.red())
        self.rgb_spins["G"].setValue(color.green())
        self.rgb_spins["B"].setValue(color.blue())
        if push:
            self.bg_changed.emit()

    def _apply_hex(self) -> None:
        text = self.hex_edit.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        if QColor(text).isValid():
            self._set_color(text)
        else:
            self.hex_edit.setText(self._current_hex)

    def _rgb_to_hex(self, _=0) -> None:
        color = QColor(
            self.rgb_spins["R"].value(),
            self.rgb_spins["G"].value(),
            self.rgb_spins["B"].value(),
        )
        self._current_hex = color.name().upper()
        self.hex_edit.setText(self._current_hex)
        self.color_preview.setStyleSheet(
            f"PushButton {{ background: {self._current_hex};"
            " border: 1px solid #999; }"
        )
        self.bg_changed.emit()

    def pick_custom_color(self) -> None:
        from aimatting.ui.color_tools import run_color_dialog

        run_color_dialog(
            self, QColor(self._current_hex), "选择自定义背景色", self._set_color
        )

    def pick_screen_color(self) -> None:
        from aimatting.ui.eyedropper import Eyedropper

        picker = Eyedropper(self)
        if picker.exec() == QDialog.DialogCode.Accepted:
            self._set_color(picker.color())

    def get_bg_state(self) -> tuple[bool, str, int]:
        return (
            self.bg_enabled.isChecked(),
            self._current_hex,
            self.opacity_slider.value(),
        )

    def set_bg_state(self, enabled: bool, hex_color: str, opacity: int) -> None:
        self.bg_enabled.blockSignals(True)
        self.opacity_slider.blockSignals(True)
        self.bg_enabled.setChecked(enabled)
        self.opacity_slider.setValue(opacity)
        self.bg_enabled.blockSignals(False)
        self.opacity_slider.blockSignals(False)
        self._set_color(hex_color, push=False)

    def get_preprocess(self) -> dict[str, int]:
        return {key: slider.value() for key, slider in self.prep_sliders.items()}

    def set_preprocess(self, values: dict[str, int]) -> None:
        for key, slider in self.prep_sliders.items():
            slider.blockSignals(True)
            slider.setValue(int(values.get(key, 0)))
            slider.blockSignals(False)

    def _reset_preprocess(self) -> None:
        self.set_preprocess(
            {"brightness": 0, "contrast": 0, "saturation": 0, "temperature": 0}
        )
        self.preprocess_changed.emit()
        self.preprocess_commit.emit()

    def get_brush(self) -> tuple[int, int, str]:
        if self.btn_mask_add.isChecked():
            mode = "add"
        elif self.btn_mask_erase.isChecked():
            mode = "erase"
        else:
            mode = "none"
        return self.brush_size.value(), self.brush_hardness.value(), mode

    def set_brush_mode(self, mode: str) -> None:
        self.tool_group.blockSignals(True)
        if mode == "add":
            self.btn_mask_add.setChecked(True)
        elif mode == "erase":
            self.btn_mask_erase.setChecked(True)
        else:
            self.btn_mask_none.setChecked(True)
        self.tool_group.blockSignals(False)
        self.mask_mode_changed.emit(mode)


class ParamPanel(QWidget):
    """右侧参数面板：开始抠图 / 手动微调 / 输出设置。"""

    feather_requested = Signal(int)
    defringe_requested = Signal(int)
    matte_requested = Signal()
    save_requested = Signal()

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._build_ui()
        self._apply_settings_to_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        self.matte_button = PrimaryPushButton("开始抠图")
        self.matte_button.setMinimumHeight(40)
        root.addWidget(self.matte_button)

        self.tabs = TabWidget()
        self.tabs.setTabsClosable(False)
        self.tabs.addTab(self._build_edit_tab(), "手动微调")
        self.tabs.addTab(self._build_output_tab(), "输出设置")
        root.addWidget(self.tabs, 1)

        hint = _muted_note("流程：导入 → 工具（可选）→ 开始抠图 → 微调 → 导出")
        root.addWidget(hint)

    # ---------- 手动微调 ----------
    def _build_edit_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        defringe_row = QHBoxLayout()
        defringe_row.addWidget(CaptionLabel("去色边半径"))
        self.defringe_spin = SpinBox()
        self.defringe_spin.setRange(1, 10)
        self.defringe_spin.setValue(4)
        defringe_row.addWidget(self.defringe_spin)
        self.defringe_button = PushButton("去色边")
        defringe_row.addWidget(self.defringe_button)
        layout.addLayout(defringe_row)

        feather_row = QHBoxLayout()
        feather_row.addWidget(CaptionLabel("边缘羽化"))
        self.feather_spin = SpinBox()
        self.feather_spin.setRange(0, 10)
        self.feather_spin.setValue(1)
        feather_row.addWidget(self.feather_spin)
        self.feather_button = PushButton("应用羽化")
        feather_row.addWidget(self.feather_button)
        layout.addLayout(feather_row)

        note = _muted_note("去色边：消除半透明边缘的彩色描边；羽化：柔化边缘过渡")
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    # ---------- 输出设置 ----------
    def _build_output_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(CaptionLabel("输出格式"))
        self.format_combo = ComboBox()
        for key, label in FORMAT_LABELS.items():
            self.format_combo.addItem(label, userData=key)
        fmt_row.addWidget(self.format_combo, 1)
        layout.addLayout(fmt_row)

        suffix_row = QHBoxLayout()
        suffix_row.addWidget(CaptionLabel("命名后缀"))
        self.suffix_edit = LineEdit()
        suffix_row.addWidget(self.suffix_edit, 1)
        layout.addLayout(suffix_row)

        quality_row = QHBoxLayout()
        quality_row.addWidget(CaptionLabel("质量"))
        self.quality_spin = SpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(95)
        quality_row.addWidget(self.quality_spin)
        quality_row.addStretch(1)
        layout.addLayout(quality_row)

        side_row = QHBoxLayout()
        side_row.addWidget(CaptionLabel("推理分辨率"))
        self.max_side_combo = ComboBox()
        for label, data in (
            ("自动（按模型）", 0),
            ("512 px", 512),
            ("1024 px", 1024),
            ("1536 px", 1536),
            ("2048 px", 2048),
        ):
            self.max_side_combo.addItem(label, userData=data)
        side_row.addWidget(self.max_side_combo, 1)
        layout.addLayout(side_row)

        self.release_model_check = CheckBox("抠图完成后自动释放模型内存")
        layout.addWidget(self.release_model_check)
        release_note = _muted_note(
            "勾选后，抠图完成会立即释放模型内存，下次抠图需重新加载。"
        )
        layout.addWidget(release_note)

        dir_row = QHBoxLayout()
        dir_row.addWidget(CaptionLabel("保存目录"))
        self.dir_edit = LineEdit()
        self.dir_edit.setPlaceholderText("默认与源图片同目录")
        dir_row.addWidget(self.dir_edit, 1)
        browse = PushButton("浏览")
        dir_row.addWidget(browse)
        layout.addLayout(dir_row)
        browse.clicked.connect(self._browse_dir)

        self.save_button = PrimaryPushButton("保存 / 导出")
        self.save_button.setMinimumHeight(34)
        layout.addWidget(self.save_button)

        note = _muted_note(
            "说明：PNG 支持透明；JPG/WEBP 无透明通道，"
            "半透明背景会平铺到白色底上。"
        )
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    # ---------- 状态读写 ----------
    def _apply_settings_to_ui(self) -> None:
        fmt = self._settings.get("output_format", "png")
        index = self.format_combo.findData(fmt)
        if index >= 0:
            self.format_combo.setCurrentIndex(index)
        self.suffix_edit.setText(str(self._settings.get("output_suffix", "抠图后")))
        self.quality_spin.setValue(int(self._settings.get("quality", 95)))
        max_side = int(self._settings.get("infer_max_side", 0))
        index = self.max_side_combo.findData(max_side)
        if index >= 0:
            self.max_side_combo.setCurrentIndex(index)
        self.release_model_check.setChecked(
            bool(self._settings.get("release_model_after_matte", True))
        )
        self.dir_edit.setText(str(self._settings.get("save_dir", "")))

    def _connect_signals(self) -> None:
        self.defringe_button.clicked.connect(
            lambda: self.defringe_requested.emit(self.defringe_spin.value())
        )
        self.feather_button.clicked.connect(
            lambda: self.feather_requested.emit(self.feather_spin.value())
        )
        self.matte_button.clicked.connect(self.matte_requested.emit)
        self.save_button.clicked.connect(self.save_requested.emit)

    def get_output_settings(self) -> tuple[str, str, int, str, int]:
        return (
            str(self.format_combo.currentData()),
            self.suffix_edit.text().strip(),
            self.quality_spin.value(),
            self.dir_edit.text().strip(),
            int(self.max_side_combo.currentData()),
        )

    def set_output_settings(
        self, fmt: str, suffix: str, quality: int, save_dir: str, max_side: int = 0
    ) -> None:
        index = self.format_combo.findData(fmt)
        if index >= 0:
            self.format_combo.setCurrentIndex(index)
        self.suffix_edit.setText(suffix)
        self.quality_spin.setValue(quality)
        self.dir_edit.setText(save_dir)
        index = self.max_side_combo.findData(max_side)
        if index >= 0:
            self.max_side_combo.setCurrentIndex(index)

    def get_release_model(self) -> bool:
        return self.release_model_check.isChecked()

    def set_release_model(self, enabled: bool) -> None:
        self.release_model_check.setChecked(bool(enabled))

    def _browse_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "选择保存目录", self.dir_edit.text() or ""
        )
        if directory:
            self.dir_edit.setText(directory)
