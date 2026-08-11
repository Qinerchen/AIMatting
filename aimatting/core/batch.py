"""批量抠图任务定义与执行。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from aimatting.core.engine import MattingEngine
from aimatting.core.image_ops import (
    adjust_image,
    alpha_to_cutout,
    composite_background,
    flatten_over_background,
    flatten_to_rgb,
    load_image,
    opaque_over_white,
)
from aimatting.core.io_utils import build_output_path, save_image


@dataclass
class BatchOptions:
    files: list[str] = field(default_factory=list)
    out_dir: str = ""
    fmt: str = "png"
    suffix: str = "抠图后"
    quality: int = 95
    bg_enabled: bool = True
    bg_color: tuple[int, int, int] = (76, 175, 80)
    bg_opacity: float = 1.0
    preprocess: dict[str, int] = field(default_factory=dict)
    max_side: int = 0
    overrides: dict[str, dict] = field(default_factory=dict)  # 逐张覆盖参数


class BatchTask(QThread):
    """批量抠图工作线程：统一参数，逐张处理并回报状态。"""

    overall_progress = Signal(int, int)      # 已完成数, 总数
    file_status = Signal(int, str, str)      # 序号, 文件名, 状态文本
    finished_ok = Signal(int, int, float)    # 成功数, 失败数, 总耗时
    failed = Signal(str)

    def __init__(self, engine: MattingEngine, options: BatchOptions, parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._options = options
        self._stop = False
        self.results: dict[str, str] = {}

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        opts = self._options
        total = len(opts.files)
        success = failed_count = 0
        t0 = time.perf_counter()
        used_targets: dict[Path, int] = {}
        try:
            if not self._engine.loaded:
                self._engine.load(self._engine.model_path or "")
            for index, path in enumerate(opts.files):
                if self._stop:
                    break
                name = Path(path).name
                try:
                    self.file_status.emit(index, name, "处理中…")
                    fo = self._file_options(path)
                    image = load_image(path)
                    if fo["preprocess"]:
                        image = adjust_image(image, **fo["preprocess"])
                    rgb = flatten_to_rgb(image)
                    alpha, _ = self._engine.matte(
                        rgb, max_side=fo["max_side"], progress=lambda _: None
                    )
                    if fo["fmt"] in ("jpg", "webp"):
                        if fo["bg_enabled"]:
                            result = flatten_over_background(
                                rgb, alpha, fo["bg_color"], fo["bg_opacity"]
                            )
                        else:
                            result = opaque_over_white(rgb, alpha, 1.0)
                    elif fo["bg_enabled"]:
                        result = composite_background(
                            rgb, alpha, fo["bg_color"], fo["bg_opacity"]
                        )
                    else:
                        result = alpha_to_cutout(rgb, alpha)
                    out_path = build_output_path(
                        path, opts.out_dir, fo["suffix"], fo["fmt"]
                    )
                    # 同一批内多个文件映射到同一输出路径时自动编号，避免互相覆盖
                    if out_path in used_targets:
                        n = used_targets[out_path] + 1
                        out_path = out_path.with_name(
                            f"{out_path.stem} ({n}){out_path.suffix}"
                        )
                        used_targets[out_path] = 0
                    else:
                        used_targets[out_path] = 0
                    save_image(result, out_path, fo["fmt"], fo["quality"])
                    success += 1
                    self.results[path] = "完成"
                    self.file_status.emit(index, name, "完成")
                except Exception as exc:  # noqa: BLE001
                    if self._stop:
                        break
                    failed_count += 1
                    self.results[path] = f"失败：{exc}"
                    self.file_status.emit(index, name, f"失败：{exc}")
                self.overall_progress.emit(index + 1, total)
            self.finished_ok.emit(success, failed_count, time.perf_counter() - t0)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def _file_options(self, path: str) -> dict:
        base = {
            "fmt": self._options.fmt,
            "suffix": self._options.suffix,
            "quality": self._options.quality,
            "bg_enabled": self._options.bg_enabled,
            "bg_color": self._options.bg_color,
            "bg_opacity": self._options.bg_opacity,
            "preprocess": self._options.preprocess,
            "max_side": self._options.max_side,
        }
        override = self._options.overrides.get(path) or {}
        base.update(override)
        return base
