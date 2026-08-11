"""撤销/重做管理器：最多保留 20 步，按 PNG 字节快照存储。"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image


@dataclass
class Snapshot:
    source_png: bytes
    alpha_png: bytes | None = None
    preprocess: dict | None = None
    mask_png: bytes | None = None
    original_png: bytes | None = None


class HistoryManager:
    def __init__(self, max_steps: int = 20) -> None:
        self._max_steps = max(1, int(max_steps))
        self._undo: list[Snapshot] = []
        # 每一项是 (操作前, 操作后)，供重做真正恢复到操作后的状态
        self._redo: list[tuple[Snapshot, Snapshot]] = []

    def push(
        self,
        source: Image.Image,
        alpha: Image.Image | None,
        preprocess: dict | None = None,
        mask: Image.Image | None = None,
        original: Image.Image | None = None,
    ) -> None:
        self._undo.append(
            Snapshot(
                _png_bytes(source),
                _png_bytes(alpha) if alpha is not None else None,
                dict(preprocess) if preprocess else None,
                _png_bytes(mask) if mask is not None else None,
                _png_bytes(original) if original is not None else None,
            )
        )
        if len(self._undo) > self._max_steps:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self, current: Snapshot | None = None) -> Snapshot | None:
        if not self._undo:
            return None
        before = self._undo.pop()
        # current 是操作后的当前状态；未提供时退化为 before（测试场景）
        after = current if current is not None else before
        self._redo.append((before, after))
        return before

    def redo(self) -> Snapshot | None:
        if not self._redo:
            return None
        before, after = self._redo.pop()
        self._undo.append(before)
        return after

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def snapshot_to_images(snap: Snapshot) -> tuple[Image.Image, Image.Image | None, Image.Image | None]:
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
    """返回快照中记录的原始导入图（裁剪撤销用），没有则为 None。"""
    if not snap.original_png:
        return None
    return Image.open(io.BytesIO(snap.original_png)).copy()


def make_snapshot(
    source: Image.Image,
    alpha: Image.Image | None = None,
    preprocess: dict | None = None,
    mask: Image.Image | None = None,
    original: Image.Image | None = None,
) -> Snapshot:
    """把当前界面状态打包成历史快照（用于撤销/重做）。"""
    return Snapshot(
        _png_bytes(source),
        _png_bytes(alpha) if alpha is not None else None,
        dict(preprocess) if preprocess else None,
        _png_bytes(mask) if mask is not None else None,
        _png_bytes(original) if original is not None else None,
    )
