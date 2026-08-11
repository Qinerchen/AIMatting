"""批量抠图面板：文件列表、统一参数与进度状态（qfluentwidgets）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    CaptionLabel,
    ComboBox,
    LineEdit,
    ListWidget,
    MessageBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SpinBox,
)

from aimatting.core.batch import BatchOptions
from aimatting.core.io_utils import FILE_DIALOG_FILTER, FORMAT_LABELS, is_supported


class BatchPanel(QWidget):
    start_requested = Signal(object)
    stop_requested = Signal()
    retry_requested = Signal()
    edit_requested = Signal(int)

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._overrides: dict[str, dict] = {}
        self._item_status: dict[int, str] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        btn_row = QHBoxLayout()
        self.add_button = PrimaryPushButton("添加图片")
        self.remove_button = PushButton("移除选中")
        self.clear_button = PushButton("清空")
        btn_row.addWidget(self.add_button)
        btn_row.addWidget(self.remove_button)
        btn_row.addWidget(self.clear_button)
        layout.addLayout(btn_row)

        opt_row = QHBoxLayout()
        self.item_settings_button = PushButton("单独设置")
        self.retry_button = PushButton("重试失败")
        opt_row.addWidget(self.item_settings_button)
        opt_row.addWidget(self.retry_button)
        layout.addLayout(opt_row)

        self.file_list = ListWidget()
        self.file_list.setSelectionMode(
            ListWidget.SelectionMode.ExtendedSelection
        )
        layout.addWidget(self.file_list, 1)

        edit_row = QHBoxLayout()
        self.edit_button = PushButton("单独编辑选中图")
        self.edit_button.setEnabled(False)
        edit_row.addWidget(self.edit_button)
        layout.addLayout(edit_row)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(CaptionLabel("格式"))
        self.format_combo = ComboBox()
        for key, label in FORMAT_LABELS.items():
            self.format_combo.addItem(label, userData=key)
        fmt_row.addWidget(self.format_combo)
        fmt_row.addWidget(CaptionLabel("后缀"))
        self.suffix_edit = LineEdit()
        self.suffix_edit.setText(str(self._settings.get("output_suffix", "抠图后")))
        fmt_row.addWidget(self.suffix_edit, 1)
        layout.addLayout(fmt_row)

        q_row = QHBoxLayout()
        q_row.addWidget(CaptionLabel("质量"))
        self.quality_spin = SpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(int(self._settings.get("quality", 95)))
        q_row.addWidget(self.quality_spin)
        q_row.addStretch(1)
        layout.addLayout(q_row)

        dir_row = QHBoxLayout()
        dir_row.addWidget(CaptionLabel("保存目录"))
        self.dir_edit = LineEdit()
        self.dir_edit.setPlaceholderText("默认与源图片同目录")
        dir_row.addWidget(self.dir_edit, 1)
        browse = PushButton("浏览")
        dir_row.addWidget(browse)
        layout.addLayout(dir_row)
        browse.clicked.connect(self._browse_dir)

        run_row = QHBoxLayout()
        self.start_button = PrimaryPushButton("开始批量抠图")
        self.stop_button = PushButton("停止")
        self.stop_button.setEnabled(False)
        run_row.addWidget(self.start_button, 1)
        run_row.addWidget(self.stop_button)
        layout.addLayout(run_row)

        self.progress = ProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.summary = CaptionLabel("未开始")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.add_button.clicked.connect(self._add_files)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self.file_list.clear)
        self.file_list.itemSelectionChanged.connect(self._update_edit_button)
        self.edit_button.clicked.connect(self._emit_edit)
        self.start_button.clicked.connect(self._emit_start)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.item_settings_button.clicked.connect(self._open_item_settings)
        self.retry_button.clicked.connect(self.retry_requested.emit)

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择要批量抠图的图片", "", FILE_DIALOG_FILTER
        )
        self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> None:
        existing = {
            self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.file_list.count())
        }
        for path in paths:
            if not is_supported(path) or path in existing:
                continue
            item = QListWidgetItem(str(Path(path).name))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.file_list.addItem(item)
            self._refresh_item_text(self.file_list.count() - 1, "")

    def _refresh_item_text(self, row: int, status: str) -> None:
        item = self.file_list.item(row)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        marker = " ⚙自定义" if path in self._overrides else ""
        suffix = f"　{status}" if status else ""
        item.setText(f"{Path(path).name}{marker}{suffix}")
        item.setToolTip(path)

    def files(self) -> list[str]:
        return [
            self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.file_list.count())
        ]

    def _remove_selected(self) -> None:
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def _update_edit_button(self) -> None:
        self.edit_button.setEnabled(len(self.file_list.selectedItems()) == 1)

    def _emit_edit(self) -> None:
        items = self.file_list.selectedItems()
        if items:
            row = self.file_list.row(items[0])
            self.edit_requested.emit(row)

    def _open_item_settings(self) -> None:
        from aimatting.ui.dialogs import BatchItemSettingsDialog

        rows = [
            self.file_list.row(item) for item in self.file_list.selectedItems()
        ]
        if not rows:
            box = MessageBox("提示", "请先选中要单独设置的图片。", self)
            box.yesButton.setText("知道了")
            box.exec()
            return
        paths = [
            self.file_list.item(r).data(Qt.ItemDataRole.UserRole) for r in rows
        ]
        defaults = self._overrides.get(paths[0], {})
        dialog = BatchItemSettingsDialog(defaults, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            values = dialog.values()
            for path in paths:
                self._overrides[path] = dict(values)
            for r in rows:
                self._refresh_item_text(r, self._item_status.get(r, ""))

    def failed_rows(self) -> list[str]:
        failed = []
        for i in range(self.file_list.count()):
            if "失败" in self._item_status.get(i, ""):
                failed.append(
                    self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
                )
        return failed

    def overrides(self) -> dict[str, dict]:
        return dict(self._overrides)

    def _browse_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "选择批量保存目录", self.dir_edit.text() or ""
        )
        if directory:
            self.dir_edit.setText(directory)

    def _emit_start(self) -> None:
        options = BatchOptions(
            files=self.files(),
            out_dir=self.dir_edit.text().strip(),
            fmt=str(self.format_combo.currentData()),
            suffix=self.suffix_edit.text().strip(),
            quality=self.quality_spin.value(),
        )
        self.start_requested.emit(options)

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.add_button.setEnabled(not running)
        self.remove_button.setEnabled(not running)
        self.clear_button.setEnabled(not running)
        self.item_settings_button.setEnabled(not running)
        self.retry_button.setEnabled(not running and bool(self.failed_rows()))

    def set_status(self, index: int, text: str) -> None:
        if 0 <= index < self.file_list.count():
            self._item_status[index] = text
            self._refresh_item_text(index, text)

    def set_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)

    def set_summary(self, text: str) -> None:
        self.summary.setText(text)
