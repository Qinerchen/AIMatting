"""UI 层工作线程：单张抠图、SAM 遮罩、模型下载（断点续传）。"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PIL import Image

from aimatting.core.engine import MattingEngine


class ModelPreloadTask(QThread):
    """后台预加载模型：启动时自动加载，避免首次抠图长时间等待。"""

    done = Signal(str)      # 引擎名称/provider
    failed = Signal(str)

    def __init__(self, engine: MattingEngine, model_path: str, parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._model_path = model_path

    def run(self) -> None:
        try:
            if not self._engine.loaded:
                self._engine.load(self._model_path)
            self.done.emit(self._engine.provider)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MattingTask(QThread):
    """单张 BiRefNet 抠图任务。进度按阶段回报（0-100）。"""

    progress = Signal(int, str)      # 百分比, 阶段文本
    done = Signal(object, float)     # alpha PIL.Image, 耗时
    failed = Signal(str)
    canceled = Signal()

    def __init__(
        self,
        engine: MattingEngine,
        image: Image.Image,
        max_side: int = 0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._image = image
        self._max_side = max_side
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            if not self._engine.loaded:
                self.progress.emit(5, "正在加载模型，首次加载可能需要一些时间…")
                self._engine.load(self._engine.model_path or "")
            if self._stop:
                self.canceled.emit()
                return
            alpha, elapsed = self._engine.matte(
                self._image,
                max_side=self._max_side,
                progress=lambda text: self.progress.emit(
                    _stage_for(text), text
                ),
            )
            if self._stop:
                self.canceled.emit()
                return
            self.done.emit(alpha, elapsed)
        except Exception as exc:  # noqa: BLE001
            if self._stop:
                self.canceled.emit()
            else:
                self.failed.emit(str(exc))


def _stage_for(text: str) -> int:
    if "预处理" in text:
        return 15
    if "推理" in text:
        return 55
    if "后处理" in text:
        return 85
    return 40


class ModelDownloadTask(QThread):
    """模型下载任务：支持断点续传、完整性校验与失败重试。"""

    progress = Signal(int, int, int)   # 已下载字节, 总字节, 百分比
    done = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        url: str,
        save_path: str,
        retries: int = 3,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._save_path = save_path
        self._retries = max(1, int(retries))
        self._stop = False
        self._expected = 0

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        import requests

        target = Path(self._save_path)
        partial = target.with_suffix(target.suffix + ".part")
        target.parent.mkdir(parents=True, exist_ok=True)
        last_error: Exception | None = None
        for attempt in range(self._retries):
            if self._stop:
                break
            try:
                self._download_once(partial)
                if (
                    self._expected
                    and partial.stat().st_size != self._expected
                ):
                    raise OSError(
                        f"文件不完整（{partial.stat().st_size} / {self._expected} 字节）"
                    )
                partial.replace(target)
                self.done.emit(str(target))
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if self._stop:
                    break
                time.sleep(1.0)
        if self._stop:
            return
        self.failed.emit(str(last_error or "下载失败"))

    def _download_once(self, partial: Path) -> None:
        import requests

        existing = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        with requests.get(self._url, stream=True, timeout=30, headers=headers) as resp:
            if resp.status_code == 206 and existing:
                total = existing + int(resp.headers.get("content-length", 0))
                mode = "ab"
            else:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                existing = 0
                mode = "wb"
            self._expected = total
            downloaded = existing
            with open(partial, mode) as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if self._stop or not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    percent = int(downloaded * 100 / total) if total else 0
                    self.progress.emit(downloaded, total, percent)
