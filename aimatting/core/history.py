"""撤销/重做管理器：最多保留 20 步，按 PNG 字节快照存储。

PNG 编码放到后台线程，避免大图时界面卡顿；push 会立刻清空 redo，
undo/redo/clear 会先等待后台编码完成，保证时序一致。
"""
from __future__ import annotations

import io
import threading
from dataclasses import dataclass

from PIL import Image


@dataclass
class Snapshot:
    source_png: bytes
    alpha_png: bytes | None = None
    preprocess: dict | None = None
    mask_png: bytes | None = None
    original_png: bytes | None = None
    base_png: bytes | None = None


class HistoryManager:
    def __init__(self, max_steps: int = 20) -> None:
        self._max_steps = max(1, int(max_steps))
        self._undo: list[Snapshot] = []
        # 每一项是 (操作前, 操作后)，供重做真正恢复到操作后的状态
        self._redo: list[tuple[Snapshot, Snapshot]] = []
        self._cond = threading.Condition()
        self._pending: list[tuple] = []
        self._inflight = 0
        self._stop = False
        self._worker = threading.Thread(
            target=self._encode_loop,
            name="history-encoder",
            daemon=True,
        )
        self._worker.start()

    def _encode_loop(self) -> None:
        """后台编码线程：把待编码快照转成 PNG 字节并写入 undo 栈。"""
        while True:
            with self._cond:
                while not self._pending and not self._stop:
                    self._cond.wait()
                if self._stop and not self._pending:
                    return
                item = self._pending.pop(0)
                self._inflight += 1
            try:
                snap = _encode_item(item)
            except Exception:  # noqa: BLE001
                snap = None
            with self._cond:
                self._inflight -= 1
                if snap is not None:
                    self._undo.append(snap)
                    if len(self._undo) > self._max_steps:
                        self._undo.pop(0)
                self._cond.notify_all()

    def _flush(self) -> None:
        """等待所有待编码快照落栈（undo/redo/clear 前调用）。"""
        with self._cond:
            while (self._pending or self._inflight) and not self._stop:
                self._cond.wait(timeout=30.0)

    def push(
        self,
        source: Image.Image,
        alpha: Image.Image | None,
        preprocess: dict | None = None,
        mask: Image.Image | None = None,
        original: Image.Image | None = None,
        base: Image.Image | None = None,
    ) -> None:
        self._redo.clear()
        with self._cond:
            self._pending.append((source, alpha, preprocess, mask, original, base))
            self._cond.notify()

    def undo(self, current: Snapshot | None = None) -> Snapshot | None:
        self._flush()
        with self._cond:
            if not self._undo:
                return None
            before = self._undo.pop()
            # current 是操作后的当前状态；未提供时退化为 before（测试场景）
            after = current if current is not None else before
            self._redo.append((before, after))
            return before

    def redo(self) -> Snapshot | None:
        self._flush()
        with self._cond:
            if not self._redo:
                return None
            before, after = self._redo.pop()
            self._undo.append(before)
            return after

    def can_undo(self) -> bool:
        with self._cond:
            return bool(self._undo) or bool(self._pending) or self._inflight > 0

    def can_redo(self) -> bool:
        with self._cond:
            return bool(self._redo)

    def clear(self) -> None:
        self._flush()
        with self._cond:
            self._undo.clear()
            self._redo.clear()

    def shutdown(self) -> None:
        """停止后台编码线程（进程退出前可选调用）。"""
        with self._cond:
            self._stop = True
            self._cond.notify_all()


def _encode_item(item: tuple) -> Snapshot:
    source, alpha, preprocess, mask, original, base = item
    return Snapshot(
        _png_bytes(source),
        _png_bytes(alpha) if alpha is not None else None,
        dict(preprocess) if preprocess else None,
        _png_bytes(mask) if mask is not None else None,
        _png_bytes(original) if original is not None else None,
        _png_bytes(base) if base is not None else None,
    )


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def snapshot_to_images(
    snap: Snapshot,
) -> tuple[Image.Image, Image.Image | None, Image.Image | None]:
    return (
        Image.open(io.BytesIO(snap.source_png)).copy(),
        (
            Image.open(io.BytesIO(snap.alpha_png)).convert("L").copy()
            if snap.alpha_png
            else None
        ),
        (
            Image.open(io.BytesIO(snap.mask_png)).convert("L").copy()
            if snap.mask_png
            else None
        ),
    )


def snapshot_original_image(snap: Snapshot) -> Image.Image | None:
    """返回快照中记录的原始导入图（裁剪撤销用），没有则返回 None。"""
    if not snap.original_png:
        return None
    return Image.open(io.BytesIO(snap.original_png)).copy()


def snapshot_base_image(snap: Snapshot) -> Image.Image | None:
    """返回快照记录的处理基础图（预处理撤销用），没有则返回 None。"""
    if not snap.base_png:
        return None
    return Image.open(io.BytesIO(snap.base_png)).copy()


def make_snapshot(
    source: Image.Image,
    alpha: Image.Image | None = None,
    preprocess: dict | None = None,
    mask: Image.Image | None = None,
    original: Image.Image | None = None,
    base: Image.Image | None = None,
) -> Snapshot:
    """把当前界面状态打包成历史快照（用于撤销/重做）。"""
    return Snapshot(
        _png_bytes(source),
        _png_bytes(alpha) if alpha is not None else None,
        dict(preprocess) if preprocess else None,
        _png_bytes(mask) if mask is not None else None,
        _png_bytes(original) if original is not None else None,
        _png_bytes(base) if base is not None else None,
    )
