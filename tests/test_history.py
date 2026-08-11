from __future__ import annotations

from PIL import Image

from aimatting.core.history import (
    HistoryManager,
    make_snapshot,
    snapshot_to_images,
)


def _image(color=0) -> Image.Image:
    return Image.new("RGB", (4, 4), (color, color, color))


def _alpha(value=0) -> Image.Image:
    return Image.new("L", (4, 4), value)


def test_push_undo_redo() -> None:
    history = HistoryManager(20)
    history.push(_image(10), _alpha(10), {"brightness": 1})
    history.push(_image(20), _alpha(20), {"brightness": 2})
    assert history.can_undo() and history.can_redo() is False
    snap = history.undo()
    assert snap.preprocess == {"brightness": 2}
    source, alpha, mask = snapshot_to_images(snap)
    assert source.getpixel((0, 0)) == (20, 20, 20)
    assert alpha.getpixel((0, 0)) == 20
    assert mask is None
    assert history.can_redo()
    history.redo()
    assert history.can_redo() is False


def test_push_with_mask_and_optional_alpha() -> None:
    history = HistoryManager(20)
    history.push(_image(5), None, mask=_alpha(7))
    assert history.can_undo()
    snap = history.undo()
    source, alpha, mask = snapshot_to_images(snap)
    assert alpha is None
    assert mask.getpixel((0, 0)) == 7


def test_cap_at_max_steps() -> None:
    history = HistoryManager(3)
    for i in range(10):
        history.push(_image(i), _alpha(i))
    steps = 0
    while history.undo():
        steps += 1
    assert steps == 3


def test_push_clears_redo() -> None:
    history = HistoryManager(5)
    history.push(_image(1), _alpha(1))
    history.push(_image(2), _alpha(2))
    history.undo()
    assert history.can_redo()
    history.push(_image(3), _alpha(3))
    assert history.can_redo() is False


def test_redo_restores_after_state() -> None:
    history = HistoryManager(5)
    history.push(_image(10), None)  # 操作前
    before = history.undo(make_snapshot(_image(20), None))  # 当前=操作后
    assert snapshot_to_images(before)[0].getpixel((0, 0)) == (10, 10, 10)
    after = history.redo()
    assert snapshot_to_images(after)[0].getpixel((0, 0)) == (20, 20, 20)
