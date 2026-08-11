"""模型推理子进程客户端。

onnxruntime 创建 InferenceSession 时持有 GIL，即使放在线程里也会卡住主进程 UI。
因此把「加载 + 推理」放进独立子进程：主进程只做 IPC，界面始终保持流畅。
"""
from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import time
from typing import Callable

from PIL import Image


def _worker_main(queue, result) -> None:
    """子进程入口：串行处理 load / unload / matte / stop 命令。"""
    from aimatting.core.engine import MattingEngine

    engine: MattingEngine | None = None
    while True:
        try:
            msg = queue.get()
        except (EOFError, KeyboardInterrupt):
            return
        if not isinstance(msg, tuple) or not msg:
            continue
        kind = msg[0]
        try:
            if kind == "stop":
                return
            if kind == "load":
                path = msg[1]
                use_trt = bool(msg[2]) if len(msg) > 2 else False
                if engine is None:
                    engine = MattingEngine()
                engine.set_model_path(path)
                engine.set_tensorrt_enabled(use_trt)
                engine.load(path)
                result.put(("load_done", engine.provider))
            elif kind == "unload":
                if engine is not None:
                    engine.unload()
                result.put(("unload_done", None))
            elif kind == "matte":
                _, w, h, rgb_bytes, max_side = msg
                if engine is None or not engine.loaded:
                    raise RuntimeError("模型尚未加载，请稍后再试")
                image = Image.frombytes("RGB", (w, h), rgb_bytes)
                alpha, elapsed = engine.matte(
                    image,
                    max_side=max_side,
                    progress=lambda text: result.put(("progress", text)),
                )
                # 直接返回原始 alpha 字节，避免 PNG 编解码开销
                result.put(
                    ("matte_done", (alpha.width, alpha.height, alpha.tobytes(), elapsed))
                )
        except Exception as exc:  # noqa: BLE001
            if kind == "load":
                result.put(("load_failed", str(exc)))
            elif kind == "unload":
                result.put(("unload_failed", str(exc)))
            elif kind == "matte":
                result.put(("matte_failed", str(exc)))


class RemoteMattingEngine:
    """与 MattingEngine 同接口的客户端：推理在子进程完成，UI 不卡顿。"""

    def __init__(self) -> None:
        self._model_path: str | None = None
        self._provider = ""
        self._loaded = False
        self._queue: mp.Queue | None = None
        self._result: mp.Queue | None = None
        self._proc: mp.Process | None = None
        self._lock = threading.Lock()
        self._tensorrt = False
        # 惰性启动：真正需要加载模型时才拉起子进程

    def _ensure_started(self) -> None:
        if self._proc is None:
            self._start()

    def _start(self) -> None:
        self._queue = mp.Queue()
        self._result = mp.Queue()
        self._proc = mp.Process(
            target=_worker_main,
            args=(self._queue, self._result),
            daemon=True,
        )
        self._proc.start()

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def model_path(self) -> str | None:
        return self._model_path

    @property
    def provider(self) -> str:
        return self._provider or "未加载"

    def set_model_path(self, model_path) -> None:
        self._model_path = str(model_path) if model_path else None

    def set_tensorrt_enabled(self, enabled: bool) -> None:
        self._tensorrt = bool(enabled)

    def load(
        self,
        model_path: str | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        """加载模型（阻塞调用方线程，不阻塞主进程 UI）。"""
        with self._lock:
            path = str(model_path) if model_path else (self._model_path or "")
            if not path:
                raise RuntimeError("模型路径为空，请先选择模型")
            if self._loaded and self._model_path == path:
                return
            self._ensure_started()
            if progress:
                progress("正在加载模型…")
            self._send(("load", path, self._tensorrt))
            deadline = time.monotonic() + 300
            while True:
                if self._proc is None or not self._proc.is_alive():
                    raise RuntimeError("模型进程异常退出，请重新打开软件")
                try:
                    kind, payload = self._result.get(timeout=0.5)
                    break
                except queue.Empty:
                    if time.monotonic() > deadline:
                        raise RuntimeError("模型加载超时")
            if kind == "load_done":
                self._loaded = True
                self._model_path = path
                self._provider = payload
                if progress:
                    progress(f"模型加载完成（{payload}）")
            else:
                self._loaded = False
                raise RuntimeError(payload or "模型加载失败")

    def unload(self) -> None:
        with self._lock:
            if self._proc is None:
                self._loaded = False
                self._provider = ""
                return
            try:
                self._send(("unload", None))
                deadline = time.monotonic() + 10
                while True:
                    if self._proc is not None and not self._proc.is_alive():
                        break
                    try:
                        kind, _payload = self._result.get(timeout=0.5)
                    except queue.Empty:
                        if time.monotonic() > deadline:
                            break
                        continue
                    if kind in ("unload_done", "unload_failed"):
                        break
            except Exception:  # noqa: BLE001
                pass
            self._loaded = False
            self._provider = ""

    def matte(
        self,
        image: Image.Image,
        max_side: int = 0,
        progress: Callable[[str], None] | None = None,
    ) -> tuple[Image.Image, float]:
        """执行抠图，返回 (alpha L 图, 耗时秒)。阻塞调用方线程。"""
        with self._lock:
            if not self._loaded:
                raise RuntimeError("模型尚未加载，请先下载并选择模型")
            self._ensure_started()
            rgb = image if image.mode == "RGB" else image.convert("RGB")
            w, h = rgb.size
            self._send(("matte", w, h, rgb.tobytes(), int(max_side)))
            while True:
                if self._proc is None or not self._proc.is_alive():
                    raise RuntimeError("模型进程异常退出，请重新打开软件")
                try:
                    kind, payload = self._result.get(timeout=1.0)
                except queue.Empty:
                    continue
                if kind == "progress":
                    if progress:
                        progress(payload)
                    continue
                if kind == "matte_done":
                    aw, ah, alpha_bytes, elapsed = payload
                    alpha = Image.frombytes("L", (aw, ah), alpha_bytes)
                    return alpha, elapsed
                if kind == "matte_failed":
                    raise RuntimeError(payload)

    def shutdown(self) -> None:
        with self._lock:
            if self._proc is None:
                self._loaded = False
                self._provider = ""
                return
            try:
                if self._proc is not None and self._proc.is_alive():
                    self._send(("stop", None))
                    self._proc.join(timeout=2)
                    if self._proc.is_alive():
                        self._proc.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._loaded = False
            self._provider = ""

    def cancel(self) -> None:
        """强制终止推理子进程（取消任务/关闭窗口时调用），下次使用自动重启。"""
        proc = self._proc
        if proc is not None:
            try:
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=2)
                    if proc.is_alive():
                        proc.kill()
            except Exception:  # noqa: BLE001
                pass
        self._proc = None
        self._queue = None
        self._result = None
        self._loaded = False
        self._provider = ""

    def _send(self, msg: tuple) -> None:
        if self._queue is None:
            raise RuntimeError("模型进程未初始化")
        self._queue.put(msg)
