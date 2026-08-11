from __future__ import annotations

import numpy as np
from PIL import Image

from aimatting.core.engine import MattingEngine


def test_preprocess_shape_and_normalization() -> None:
    img = Image.new("RGB", (32, 64), (128, 128, 128))
    arr = MattingEngine.preprocess(img, tw=32, th=64)
    assert arr.shape == (1, 3, 64, 32)
    assert arr.dtype == np.float32
    # 归一化后像素 0.5 对应 (0.5-mean)/std
    assert abs(arr[0, 0, 0, 0] - (0.5019608 - 0.485) / 0.229) < 1e-3


def test_postprocess_shape_and_range() -> None:
    raw = np.zeros((1, 1, 16, 16), dtype=np.float32)
    out = MattingEngine.postprocess(raw, (32, 32))
    assert out.size == (32, 32)
    assert out.mode == "L"
    assert np.asarray(out).max() < 128  # sigmoid(0)=0.5 -> 127


def test_target_size_fixed_and_dynamic() -> None:
    engine = MattingEngine()
    engine._input_shape = (1024, 1024)
    engine._dynamic = False
    assert engine._target_size(Image.new("RGB", (4000, 3000)), 0) == (1024, 1024)
    engine._input_shape = None
    engine._dynamic = True
    tw, th = engine._target_size(Image.new("RGB", (4000, 3000)), 2048)
    assert tw <= 2048 and th <= 2048
    assert tw % 16 == 0 and th % 16 == 0
    assert max(tw, th) == 2048
