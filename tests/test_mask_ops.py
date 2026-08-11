from __future__ import annotations

import numpy as np
from PIL import Image

from aimatting.core.image_ops import adjust_image, keep_masked_region


def test_keep_masked_region_keeps_painted_and_clears_rest() -> None:
    img = Image.new("RGB", (16, 16), (200, 100, 50))
    mask = np.zeros((16, 16), dtype=np.uint8)
    mask[4:12, 4:12] = 255
    out = keep_masked_region(img, mask)
    assert out.mode == "RGBA"
    arr = np.asarray(out)
    assert arr[8, 8, 3] == 255
    assert arr[1, 1, 3] == 0
    assert tuple(arr[8, 8, :3]) == (200, 100, 50)


def test_adjust_image_preserves_alpha() -> None:
    rgba = Image.new("RGBA", (8, 8), (10, 20, 30, 128))
    out = adjust_image(rgba, brightness=20)
    assert out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 128
