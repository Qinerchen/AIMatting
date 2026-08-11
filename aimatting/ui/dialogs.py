"""模型管理、使用教程、关于对话框（qfluentwidgets）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    ColorDialog,
    ComboBox,
    FluentStyleSheet,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    RadioButton,
    Slider,
    SpinBox,
    TitleLabel,
)

from aimatting.core.config import (
    MODEL_DIR,
    MODEL_REGISTRY,
    model_file_path,
    model_status,
)
from aimatting.core.io_utils import FORMAT_LABELS
from aimatting.workers.tasks import ModelDownloadTask


def human_size(size: int) -> str:
    return f"{size / 1024 / 1024:.0f} MB"


class ModelManagerDialog(QDialog):
    """模型下载与选择。"""

    model_changed = Signal(str)

    def __init__(self, current_model_id: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("模型管理")
        self.setMinimumWidth(560)
        self._current_model_id = current_model_id
        self._download_task: ModelDownloadTask | None = None
        self._radios: dict[str, RadioButton] = {}
        self._status_labels: dict[str, CaptionLabel] = {}
        FluentStyleSheet.DIALOG.apply(self)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = TitleLabel("BiRefNet ONNX 模型（官方发布，MIT 许可证）")
        layout.addWidget(title)

        self._group = QButtonGroup(self)
        for model_id, info in MODEL_REGISTRY.items():
            card = QWidget()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            radio = RadioButton(info["name"])
            self._radios[model_id] = radio
            self._group.addButton(radio)
            if model_id == self._current_model_id:
                radio.setChecked(True)
            desc = BodyLabel(info["description"])
            desc.setWordWrap(True)
            status = CaptionLabel("")
            self._status_labels[model_id] = status
            card_layout.addWidget(radio)
            card_layout.addWidget(desc)
            card_layout.addWidget(status)
            layout.addWidget(card)
            self._update_status(model_id)

        self.progress = ProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        btn_row = QHBoxLayout()
        self.download_button = PrimaryPushButton("下载选中模型")
        self.local_button = PushButton("选择本地 ONNX 文件…")
        btn_row.addWidget(self.download_button)
        btn_row.addWidget(self.local_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        note = CaptionLabel(
            "提示：模型较大（约 316MB / 1GB），下载需联网，"
            "完成后保存在软件 models 目录，不会上传任何图片。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = PrimaryPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self.download_button.clicked.connect(self._start_download)
        self.local_button.clicked.connect(self._pick_local)

    def _selected_model_id(self) -> str | None:
        for model_id, radio in self._radios.items():
            if radio.isChecked():
                return model_id
        return None

    def _update_status(self, model_id: str) -> None:
        status = model_status(model_id)
        label = self._status_labels[model_id]
        if status == "已下载":
            label.setText(
                f"状态：{status}（{human_size(model_file_path(model_id).stat().st_size)}）"
            )
        else:
            label.setText(f"状态：{status}")
        self._update_download_button()

    def _update_download_button(self) -> None:
        if not hasattr(self, "download_button"):
            return
        selected = self._selected_model_id()
        if selected and model_status(selected) == "已下载":
            self.download_button.setText("重新下载选中模型")
        else:
            self.download_button.setText("下载选中模型")

    def _start_download(self) -> None:
        model_id = self._selected_model_id()
        if not model_id:
            return
        info = MODEL_REGISTRY[model_id]
        save_path = str(model_file_path(model_id))
        self._download_task = ModelDownloadTask(info["url"], save_path, self)
        self._download_task.progress.connect(self._on_progress)
        self._download_task.done.connect(lambda _: self._on_download_done(model_id))
        self._download_task.failed.connect(self._on_download_failed)
        self.download_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress.setFormat(f"下载中 {info['filename']}：%p%")
        self._download_task.start()

    def _on_progress(self, downloaded: int, total: int, percent: int) -> None:
        if total:
            self.progress.setFormat(
                f"下载中：{human_size(downloaded)} / {human_size(total)}（%p%）"
            )
        self.progress.setValue(percent)

    def _on_download_done(self, model_id: str) -> None:
        self.progress.setVisible(False)
        self.download_button.setEnabled(True)
        self._radios[model_id].setChecked(True)
        self._update_status(model_id)
        self.model_changed.emit(model_id)

    def _on_download_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.download_button.setEnabled(True)
        box = MessageBox("下载失败", f"模型下载失败：\n{message}", self)
        box.yesButton.setText("知道了")
        box.exec()

    def _pick_local(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 ONNX 模型文件", str(MODEL_DIR), "ONNX 模型 (*.onnx)"
        )
        if path:
            self.model_changed.emit(path)
            box = MessageBox(
                "已选择模型", f"已切换到本地模型：\n{path}", self
            )
            box.yesButton.setText("知道了")
            box.exec()


class TutorialDialog(QDialog):
    """使用教程与常见问题。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("使用教程与常见问题")
        self.resize(680, 560)
        FluentStyleSheet.DIALOG.apply(self)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(
            "QTextBrowser { background: transparent; border: none; }"
        )
        browser.setHtml(TUTORIAL_HTML)
        layout.addWidget(browser)
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = PrimaryPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于 AIMatting")
        self.setMinimumWidth(420)
        FluentStyleSheet.DIALOG.apply(self)
        layout = QVBoxLayout(self)
        title = TitleLabel("AIMatting v0.0.3")
        layout.addWidget(title)
        text = BodyLabel(
            "基于 BiRefNet（MIT License）高精度抠图算法，"
            "本地运行、隐私安全。\n"
            "模型来源：ZhengPeng7/BiRefNet 官方 GitHub Release。\n"
            "本软件不联网收集任何图片数据。\n"
            "界面使用 PyQt-Fluent-Widgets（GPL-3.0）。"
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = PrimaryPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)


TUTORIAL_HTML = """
<style>
body { color: #d6dae3; font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; }
h2 { color: #ffffff; }
b { color: #ffffff; }
a { color: #4C8DFF; }
</style>
<h2>快速上手（5 步）</h2>
<ol>
  <li><b>下载模型</b>：点击工具栏「模型管理」，下载推荐的高精度模型（首次约 1GB，此后离线可用）。</li>
  <li><b>导入图片</b>：点击「导入」或将图片直接拖入左侧区域（支持 JPG / PNG / WEBP / TIFF / BMP）。</li>
  <li><b>可选预处理</b>：在「预处理」页调整亮度、对比度、饱和度、色温，优化后再抠图。</li>
  <li><b>开始抠图</b>：点击「开始抠图」按钮，等待进度提示；完成后可实时预览。</li>
  <li><b>填充背景并导出</b>：在「背景填充」页选择颜色与不透明度（实时预览），
      在「输出设置」页选择格式、命名后缀与保存目录，点击「保存 / 导出」。</li>
</ol>

<h2>核心功能</h2>
<ul>
  <li><b>高精度抠图</b>：BiRefNet HR-matting 模型，对发丝、毛发、玻璃等细边缘/半透明场景效果好。</li>
  <li><b>笔刷遮罩</b>：在「笔刷遮罩」页选「画前景」，沿主体大致涂一遍（绿色高亮），
      涂错用「擦除」；然后点「开始抠图」，AI 自动做精细边缘。
      画笔大小、硬度可调，光标圆圈即画笔大小。</li>
  <li><b>裁剪</b>：工具栏「裁剪」后在预览图上框选要保留的区域，确认后裁掉无用部分。</li>
  <li><b>前后对比</b>：工具栏「对比」按钮切换原图/结果滑动对比，拖动白色分割线查看差异。</li>
  <li><b>发丝级精修</b>：「手动微调」页提供「去色边」（消除半透明边缘的彩色描边）
      与「边缘羽化」（柔化边缘过渡）。</li>
  <li><b>纯色背景填充</b>：常用色一键选择，或色板 / RGB / HEX 自定义，支持 0-100% 不透明度实时预览。</li>
  <li><b>批量抠图</b>：批量页一次添加多张图片，统一参数处理；处理结果可在列表中逐张查看状态，
      也可「单独编辑选中图」进行微调。</li>
  <li><b>撤销 / 重做</b>：支持最多 20 步操作记录（Ctrl+Z / Ctrl+Y）。</li>
  <li><b>预览缩放</b>：滚轮缩放、拖拽平移，可放大查看边缘细节。</li>
</ul>

<h2>常见问题</h2>
<ul>
  <li><b>没有模型怎么办？</b> 首次使用需在「模型管理」中下载模型；下载中断可重新下载（会覆盖不完整文件）。</li>
  <li><b>笔刷遮罩怎么用？</b> 大致把主体涂满即可，边缘不需要精确；
      BiRefNet 会在遮罩范围内做精细 matting，边缘质量以 AI 结果为准。</li>
  <li><b>抠图很慢？</b> 取决于硬件：GPU 用户建议安装 <code>onnxruntime-gpu</code>；
      在「输出设置」中降低推理分辨率（512/1024）可明显提速，适合快速预览。</li>
  <li><b>4K 大图内存占用高？</b> 软件按需加载，建议先使用 lite 模型或降低推理分辨率。</li>
  <li><b>JPG 为什么不能透明？</b> JPG/WEBP 格式本身不支持透明通道，会以白色为底合成；透明素材请导出 PNG。</li>
  <li><b>半透明背景导出后为什么有白底？</b> JPG 不支持透明，半透明背景会平铺到白色底上；PNG 可完整保留半透明。</li>
  <li><b>隐私安全吗？</b> 所有处理均在本机完成，不收集、不上传任何本地图片。</li>
</ul>

<h2>快捷键</h2>
<p>Ctrl+O 导入 · Ctrl+R 抠图 · Ctrl+S 保存 · Ctrl+Z 撤销 · Ctrl+Y 重做 · F1 教程</p>
"""


class BatchItemSettingsDialog(QDialog):
    """批量单张参数设置：背景、格式、质量、后缀。"""

    def __init__(self, defaults: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("单独设置")
        self.setMinimumWidth(340)
        FluentStyleSheet.DIALOG.apply(self)
        defaults = defaults or {}
        self._color = tuple(defaults.get("bg_color", (76, 175, 80)))
        if isinstance(self._color, str):
            self._color = QColor(self._color).getRgb()[:3]
        self._build_ui(defaults or {})

    def _build_ui(self, defaults: dict) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.bg_enabled = CheckBox("启用纯色背景填充")
        self.bg_enabled.setChecked(bool(defaults.get("bg_enabled", True)))
        layout.addWidget(self.bg_enabled)

        color_row = QHBoxLayout()
        self.color_button = PushButton("背景颜色")
        self.color_button.setFixedWidth(100)
        color_row.addWidget(self.color_button)
        self.hex_label = CaptionLabel(self._hex())
        color_row.addWidget(self.hex_label)
        color_row.addStretch(1)
        layout.addLayout(color_row)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(CaptionLabel("不透明度"))
        self.opacity_slider = Slider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(float(defaults.get("bg_opacity", 1.0)) * 100))
        self.opacity_value = CaptionLabel(f"{self.opacity_slider.value()}%")
        self.opacity_value.setFixedWidth(40)
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_value.setText(f"{v}%")
        )
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_value)
        layout.addLayout(opacity_row)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(CaptionLabel("输出格式"))
        self.format_combo = ComboBox()
        for key, label in FORMAT_LABELS.items():
            self.format_combo.addItem(label, userData=key)
        index = self.format_combo.findData(defaults.get("fmt", "png"))
        if index >= 0:
            self.format_combo.setCurrentIndex(index)
        fmt_row.addWidget(self.format_combo, 1)
        layout.addLayout(fmt_row)

        q_row = QHBoxLayout()
        q_row.addWidget(CaptionLabel("质量"))
        self.quality_spin = SpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(int(defaults.get("quality", 95)))
        q_row.addWidget(self.quality_spin)
        q_row.addStretch(1)
        layout.addLayout(q_row)

        suffix_row = QHBoxLayout()
        suffix_row.addWidget(CaptionLabel("命名后缀"))
        self.suffix_edit = LineEdit()
        self.suffix_edit.setText(str(defaults.get("suffix", "抠图后")))
        suffix_row.addWidget(self.suffix_edit, 1)
        layout.addLayout(suffix_row)

        btn_row = QHBoxLayout()
        cancel_btn = PushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = PrimaryPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        btn_row.addStretch(1)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        self.color_button.clicked.connect(self._pick_color)
        self._refresh_color()

    def _hex(self) -> str:
        r, g, b = self._color
        return f"#{r:02X}{g:02X}{b:02X}"

    def _refresh_color(self) -> None:
        self.color_button.setStyleSheet(
            f"PushButton {{ background: {self._hex()}; border: 1px solid #999; }}"
        )
        self.hex_label.setText(self._hex())

    def _pick_color(self) -> None:
        dialog = ColorDialog(QColor(*self._color), "选择背景色", self)

        def apply_color(color: QColor) -> None:
            self._color = color.getRgb()[:3]
            self._refresh_color()

        dialog.colorChanged.connect(apply_color)
        dialog.exec()

    def values(self) -> dict:
        return {
            "bg_enabled": self.bg_enabled.isChecked(),
            "bg_color": tuple(self._color),
            "bg_opacity": self.opacity_slider.value() / 100.0,
            "fmt": str(self.format_combo.currentData()),
            "quality": self.quality_spin.value(),
            "suffix": self.suffix_edit.text().strip(),
        }
