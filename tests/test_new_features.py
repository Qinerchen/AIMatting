from __future__ import annotations

import numpy as np
from PIL import Image

from aimatting.core.batch import BatchOptions, BatchTask
from aimatting.core.image_ops import defringe, merge_masks


def _make_image():
    img = Image.new("RGB", (32, 32), (255, 0, 0))      # 红色前景
    alpha = np.zeros((32, 32), dtype=np.uint8)
    alpha[8:24, 8:24] = 255                              # 中央不透明
    alpha[12:20, 12:20] = 128                            # 半透明内部
    return img, alpha


def test_defringe_removes_color_bleed() -> None:
    img, alpha = _make_image()
    # 给半透明边缘混入蓝色背景色
    arr = np.asarray(img).copy()
    arr[alpha > 0] = (255, 0, 0)
    arr[alpha == 128] = (200, 60, 60)  # 半透明像素混入背景色（偏暗偏蓝）
    arr[alpha == 0] = (0, 0, 255)
    img = Image.fromarray(arr)
    out = defringe(img, alpha, radius=3)
    out_arr = np.asarray(out)
    # 半透明像素颜色应接近纯红前景（蓝通道接近 0）
    semitransparent = out_arr[alpha == 128]
    assert semitransparent[:, 2].mean() < 40, "色边应被去除"
    assert semitransparent[:, 0].mean() > 220


def test_defringe_keeps_shape_and_mode() -> None:
    img, alpha = _make_image()
    out = defringe(img, alpha, radius=2)
    assert out.mode == "RGB"
    assert out.size == img.size


def test_merge_masks() -> None:
    a = np.zeros((10, 10), dtype=np.uint8)
    b = np.zeros((10, 10), dtype=np.uint8)
    a[0:5, 0:5] = 255
    b[5:10, 5:10] = 255
    merged = merge_masks([a, b])
    assert merged is not None
    assert merged[2, 2] == 255 and merged[7, 7] == 255
    assert merged[2, 7] == 0
    assert merge_masks([]) is None
    assert merge_masks([None, None]) is None


def test_batch_file_options_merge() -> None:
    options = BatchOptions(
        files=["a.png", "b.png"],
        fmt="png",
        suffix="默认",
        bg_enabled=True,
        bg_color=(255, 0, 0),
        bg_opacity=1.0,
        overrides={"a.png": {"fmt": "jpg", "suffix": "特例", "quality": 80}},
    )
    task = BatchTask.__new__(BatchTask)
    task._options = options
    a = task._file_options("a.png")
    b = task._file_options("b.png")
    assert a["fmt"] == "jpg" and a["suffix"] == "特例" and a["quality"] == 80
    assert b["fmt"] == "png" and b["suffix"] == "默认" and b["quality"] == 95
