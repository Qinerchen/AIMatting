from __future__ import annotations

import numpy as np
from PIL import Image

from aimatting.core.image_ops import (
    adjust_image,
    alpha_to_cutout,
    build_clean_alpha,
    composite_background,
    despill_edges,
    flatten_over_background,
    flatten_to_rgb,
    paint_mask,
    soften_alpha,
)


def _rgb(size=(8, 8), color=(200, 100, 50)) -> Image.Image:
    return Image.new("RGB", size, color)


def _alpha_array(value: int = 255, size=(4, 4)) -> np.ndarray:
    return np.full(size, value, dtype=np.uint8)


def test_flatten_rgba_over_white() -> None:
    rgba = Image.new("RGBA", (4, 4), (10, 20, 30, 0))
    out = flatten_to_rgb(rgba, background=(255, 255, 255))
    assert out.mode == "RGB"
    assert out.getpixel((0, 0)) == (255, 255, 255)


def test_composite_full_opacity_opaque() -> None:
    img = _rgb((4, 4), (200, 100, 50))
    alpha = _alpha_array(255)
    out = composite_background(img, alpha, (0, 0, 255), 1.0)
    assert out.mode == "RGBA"
    assert out.getpixel((0, 0))[:3] == (200, 100, 50)
    assert out.getpixel((0, 0))[3] == 255


def test_composite_zero_opacity_transparent() -> None:
    img = _rgb((4, 4), (200, 100, 50))
    alpha = _alpha_array(0)
    out = composite_background(img, alpha, (0, 0, 255), 0.0)
    assert out.getpixel((0, 0))[3] == 0


def test_composite_half_opacity_background() -> None:
    img = _rgb((4, 4), (200, 100, 50))
    alpha = _alpha_array(0)
    out = composite_background(img, alpha, (0, 0, 255), 0.5)
    r, g, b, a = out.getpixel((0, 0))
    assert a == 127
    assert (r, g, b) == (0, 0, 255)  # 纯背景区域显示背景色


def test_alpha_to_cutout() -> None:
    img = _rgb((4, 4))
    alpha = Image.fromarray(_alpha_array(128))
    out = alpha_to_cutout(img, alpha)
    assert out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 128


def test_flatten_over_background_uses_color() -> None:
    img = _rgb((4, 4), (200, 100, 50))
    alpha = _alpha_array(0)
    out = flatten_over_background(img, alpha, (0, 0, 255), 1.0)
    assert out.mode == "RGB"
    assert out.getpixel((0, 0)) == (0, 0, 255)


def test_flatten_over_background_keeps_foreground() -> None:
    img = _rgb((4, 4), (200, 100, 50))
    alpha = _alpha_array(255)
    out = flatten_over_background(img, alpha, (0, 0, 255), 1.0)
    assert out.getpixel((0, 0)) == (200, 100, 50)


def test_flatten_over_background_half_opacity_blends_white() -> None:
    img = _rgb((4, 4), (200, 100, 50))
    alpha = _alpha_array(0)
    out = flatten_over_background(img, alpha, (0, 0, 255), 0.5)
    # 背景层 = 蓝*0.5 + 白*0.5
    assert out.getpixel((0, 0)) == (127, 127, 255)


def test_build_clean_alpha_fills_interior_and_cleans_background() -> None:
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[16:48, 16:48] = 200          # 主体
    mask[31:34, 31:34] = 0            # 主体内部小洞
    mask[8, 8] = 255                  # 背景孤立噪点
    out = build_clean_alpha(mask, feather=1, edge_shrink=1, contrast=1.7)
    assert out[40, 40] == 255         # 主体内部强制不透明
    assert out[32, 32] == 255         # 内部小洞被闭运算填上
    assert out[8, 8] == 0             # 背景噪点被开运算去掉
    assert out[0, 0] == 0             # 背景保持透明


def test_build_clean_alpha_thresholds() -> None:
    mask = np.full((8, 8), 200, dtype=np.uint8)
    mask[0:4, 0:4] = 50               # 明显背景
    out = build_clean_alpha(mask, feather=0, edge_shrink=0, contrast=1.7)
    assert out[6, 6] == 255
    assert out[1, 1] == 0


def test_despill_edges_removes_background_spill() -> None:
    rgba = Image.new("RGBA", (32, 32), (255, 0, 0, 0))      # 红色透明背景
    rgba.putpixel((16, 16), (127, 0, 0, 128))               # 半透明边缘像素
    rgba.putpixel((8, 8), (200, 100, 50, 255))              # 不透明主体像素
    out = despill_edges(rgba)
    # 边缘像素反解前景色：去除红色背景渗入后接近 (0,0,0)
    r, g, b, a = out.getpixel((16, 16))
    assert a == 128
    assert r < 10 and g < 10 and b < 10
    # 不透明像素保持不变
    assert out.getpixel((8, 8))[:3] == (200, 100, 50)


def test_adjust_image_bounds() -> None:
    img = _rgb()
    for values in (
        dict(brightness=100, contrast=100, saturation=100, temperature=100),
        dict(brightness=-100, contrast=-100, saturation=-100, temperature=-100),
        dict(),
    ):
        out = adjust_image(img, **values)
        arr = np.asarray(out)
        assert arr.min() >= 0 and arr.max() <= 255


def test_paint_mask_add_and_erase() -> None:
    alpha = np.zeros((100, 100), dtype=np.uint8)
    paint_mask(alpha, 50, 50, radius=10, hardness=1.0, mode="add")
    assert alpha[50, 50] == 255
    assert alpha[50, 70] == 0
    paint_mask(alpha, 50, 50, radius=10, hardness=1.0, mode="erase")
    assert alpha[50, 50] == 0


def test_paint_mask_out_of_bounds() -> None:
    alpha = np.zeros((10, 10), dtype=np.uint8)
    paint_mask(alpha, -5, -5, radius=2, hardness=1.0, mode="add")
    paint_mask(alpha, 200, 200, radius=2, hardness=1.0, mode="add")
    assert alpha.sum() == 0


def test_paint_mask_covers_top_and_left_edges() -> None:
    alpha = np.zeros((100, 100), dtype=np.uint8)
    paint_mask(alpha, 50, 0, radius=10, hardness=1.0, mode="add")
    assert alpha[0, 50] == 255            # 顶部第 0 行要覆盖到
    assert alpha[99, 50] == 0             # 不能绕到图像底部
    paint_mask(alpha, 0, 50, radius=10, hardness=1.0, mode="add")
    assert alpha[50, 0] == 255            # 左侧第 0 列要覆盖到
    assert alpha[50, 99] == 0             # 不能绕到图像右侧


def test_soften_alpha() -> None:
    alpha = Image.fromarray(np.zeros((20, 20), dtype=np.uint8))
    alpha.putpixel((10, 10), 255)
    out = soften_alpha(alpha, 2.0)
    arr = np.asarray(out)
    assert arr.max() > 0 and arr.max() < 255
