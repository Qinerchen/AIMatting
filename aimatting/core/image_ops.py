"""图像加载、预处理、背景合成与遮罩笔刷工具。"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


PRESET_COLORS: dict[str, str] = {
    "白": "#FFFFFF",
    "黑": "#000000",
    "灰": "#808080",
    "红": "#E53935",
    "橙": "#FB8C00",
    "黄": "#FDD835",
    "绿": "#43A047",
    "青": "#00ACC1",
    "蓝": "#1E88E5",
    "品红": "#D81B60",
}


def load_image(path: str | Path) -> Image.Image:
    """加载图片并处理 EXIF 旋转；保留透明通道信息。"""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im = im.copy()
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        return im.convert("RGBA")
    return im.convert("RGB")


def flatten_to_rgb(image: Image.Image, background=(255, 255, 255)) -> Image.Image:
    """将带透明通道的图片平铺到纯色底上，得到不透明 RGB。"""
    if image.mode == "RGBA":
        base = Image.new("RGBA", image.size, tuple(background) + (255,))
        base.alpha_composite(image)
        return base.convert("RGB")
    return image.convert("RGB")


def adjust_image(
    image: Image.Image,
    brightness: int = 0,
    contrast: int = 0,
    saturation: int = 0,
    temperature: int = 0,
) -> Image.Image:
    """亮度/对比度/饱和度/色温调整，参数范围为 -100..100。

    输入为 RGBA 时保留原透明通道，只调整颜色。
    """
    keep_alpha = image.mode in ("RGBA", "LA")
    out = flatten_to_rgb(image)
    if brightness:
        out = ImageEnhance.Brightness(out).enhance(1.0 + brightness / 100.0)
    if contrast:
        c = contrast * 2.55
        factor = 259.0 * (c + 255.0) / (255.0 * (259.0 - c))
        out = ImageEnhance.Contrast(out).enhance(factor)
    if saturation:
        out = ImageEnhance.Color(out).enhance(1.0 + saturation / 100.0)
    if temperature:
        out = _apply_temperature(out, temperature)
    if keep_alpha:
        alpha = image.convert("RGBA").getchannel("A")
        out = out.convert("RGBA")
        out.putalpha(alpha)
    return out


def _apply_temperature(image: Image.Image, temperature: int) -> Image.Image:
    """色温：正值偏暖（R 增强、B 减弱），负值偏冷。"""
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    factor = 1.0 + (temperature / 100.0) * 0.25
    arr[..., 0] *= factor
    arr[..., 2] /= factor
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")


def composite_background(
    image: Image.Image,
    alpha,
    color=(255, 255, 255),
    opacity: float = 1.0,
) -> Image.Image:
    """前景（RGB）+ alpha（L 或 HxW 数组）合成到带不透明度的纯色背景上。

    返回 RGBA：背景透明度为 opacity（0=全透明，1=完全不透明），
    前景主体始终保持全不透明。适合导出 PNG；JPG 场景请再用白色平铺。
    """
    fg = np.asarray(flatten_to_rgb(image), dtype=np.float32)
    if isinstance(alpha, Image.Image):
        a = np.asarray(alpha.convert("L"), dtype=np.float32) / 255.0
    else:
        a = np.asarray(alpha, dtype=np.float32) / 255.0
    if a.ndim == 2:
        a = a[..., None]
    bg = np.zeros_like(fg)
    bg[:] = color
    out_alpha = a + (1.0 - a) * float(np.clip(opacity, 0.0, 1.0))
    out_rgb = (fg * a + bg * (1.0 - a) * float(opacity)) / np.maximum(out_alpha, 1e-6)
    rgba = np.dstack(
        [
            np.clip(out_rgb, 0, 255).astype(np.uint8),
            (np.clip(out_alpha, 0.0, 1.0) * 255).astype(np.uint8),
        ]
    )
    return Image.fromarray(rgba, mode="RGBA")


def alpha_to_cutout(image: Image.Image, alpha) -> Image.Image:
    """直接输出透明背景素材（RGBA）。"""
    rgba = flatten_to_rgb(image).convert("RGBA")
    if isinstance(alpha, Image.Image):
        rgba.putalpha(alpha.convert("L"))
    else:
        rgba.putalpha(Image.fromarray(np.asarray(alpha, dtype=np.uint8), mode="L"))
    return rgba


def keep_masked_region(image: Image.Image, mask) -> Image.Image:
    """只保留 mask 覆盖的区域，其余全部删除（透明），返回 RGBA。

    用于笔刷遮罩的「确定」：画到的部分保留，未画到部分变成透明。
    """
    rgba = flatten_to_rgb(image).convert("RGBA")
    if isinstance(mask, Image.Image):
        m = mask.convert("L")
    else:
        m = Image.fromarray(np.asarray(mask, dtype=np.uint8), mode="L")
    rgba.putalpha(m)
    return rgba


def opaque_over_white(image: Image.Image, alpha, opacity: float = 1.0) -> Image.Image:
    """JPG/WEBP 无透明通道场景：将半透明结果平铺到白色底。"""
    if float(opacity) >= 0.999:
        return composite_background(image, alpha, (255, 255, 255), 1.0).convert("RGB")
    return composite_background(image, alpha, (255, 255, 255), opacity).convert("RGB")


def soften_alpha(alpha, radius: float = 1.0) -> Image.Image:
    """对 alpha 做轻度高斯羽化，柔化边缘。"""
    if isinstance(alpha, np.ndarray):
        img = Image.fromarray(np.asarray(alpha, dtype=np.uint8), mode="L")
    else:
        img = alpha.convert("L")
    return img.filter(ImageFilter.GaussianBlur(radius))


_BRUSH_CACHE: dict[tuple[int, float], np.ndarray] = {}


def _brush_kernel(radius: int, hardness: float) -> np.ndarray:
    key = (radius, round(float(hardness), 2))
    if key in _BRUSH_CACHE:
        return _BRUSH_CACHE[key]
    r = max(1, int(radius))
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    dist = np.sqrt(xx.astype(np.float32) ** 2 + yy.astype(np.float32) ** 2)
    inner = max(0.0, float(r) * float(np.clip(hardness, 0.0, 1.0)))
    coverage = np.where(
        dist <= inner,
        1.0,
        np.where(dist <= r, (r - dist) / max(r - inner, 1e-6), 0.0),
    )
    _BRUSH_CACHE[key] = coverage.astype(np.float32)
    return _BRUSH_CACHE[key]


def paint_mask(
    alpha: np.ndarray,
    cx: float,
    cy: float,
    radius: int,
    hardness: float,
    mode: str,
) -> None:
    """在 alpha 上涂抹：mode='add' 修复/补充前景，mode='erase' 误抠擦除。"""
    kernel = _brush_kernel(radius, float(hardness))
    r = kernel.shape[0] // 2
    x0 = int(round(cx)) - r
    y0 = int(round(cy)) - r
    h, w = alpha.shape
    x1 = min(w, x0 + kernel.shape[1])
    y1 = min(h, y0 + kernel.shape[0])
    if x1 <= 0 or y1 <= 0 or x0 >= w or y0 >= h:
        return
    kx0 = max(0, -x0)
    ky0 = max(0, -y0)
    ix0 = max(0, x0)
    iy0 = max(0, y0)
    region = kernel[ky0 : ky0 + (y1 - y0), kx0 : kx0 + (x1 - x0)]
    region_alpha = alpha[iy0:y1, ix0:x1].astype(np.float32)
    if mode == "add":
        region_alpha = np.maximum(region_alpha, region * 255.0)
    else:
        region_alpha = np.minimum(region_alpha, 255.0 - region * 255.0)
    alpha[iy0:y1, ix0:x1] = region_alpha.astype(np.uint8)


def combine_with_target_mask(
    alpha,
    sam_mask,
    dilation: int = 8,
) -> Image.Image:
    """用 SAM 目标遮罩约束 BiRefNet alpha。

    流程：SAM 遮罩二值化后膨胀 dilation 像素，作为主体区域先验；
    BiRefNet 的软 alpha 仅保留在区域内，从而只抠出用户选定的主体，
    同时保留 BiRefNet 在细边缘上的质量。
    """
    a = np.asarray(alpha, dtype=np.float32)
    m = np.asarray(sam_mask, dtype=np.float32) / 255.0
    if a.ndim == 3:
        a = a[..., 0]
    m_bin = (m > 0.5).astype(np.uint8) * 255
    if dilation > 0:
        pil = Image.fromarray(m_bin, mode="L").filter(
            ImageFilter.MaxFilter(dilation * 2 + 1)
        )
        m_bin = np.asarray(pil)
    result = a * (m_bin / 255.0)
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), mode="L")


def mask_bbox(
    mask,
    margin_ratio: float = 0.15,
    min_margin: int = 16,
    threshold: int = 90,
) -> tuple[int, int, int, int] | None:
    """计算遮罩包围盒并向外扩展边距，供裁剪放大后精细抠图。"""
    m = np.asarray(mask)
    ys, xs = np.where(m > threshold)
    if len(ys) == 0:
        return None
    h, w = m.shape[:2]
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    margin = max(int((x1 - x0 + 1) * margin_ratio), min_margin)
    x0 = max(0, x0 - margin)
    y0 = max(0, y0 - margin)
    x1 = min(w - 1, x1 + margin)
    y1 = min(h - 1, y1 + margin)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return x0, y0, x1, y1


def defringe(image: Image.Image, alpha, radius: int = 4) -> Image.Image:
    """去除半透明边缘的彩色描边（色边）。

    原理：以完全不透明前景为种子，向半透明边缘逐层"扩散填充"最近前景色，
    使半透明像素保留前景色而非原图里混入的背景色；alpha 不变。
    """
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    if isinstance(alpha, Image.Image):
        a = np.asarray(alpha.convert("L"), dtype=np.float32) / 255.0
    else:
        a = np.asarray(alpha, dtype=np.float32) / 255.0
    h, w = a.shape[:2]
    if (h, w) != arr.shape[:2]:
        a = np.asarray(
            Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), mode="L")
            .resize((arr.shape[1], arr.shape[0]), Image.LANCZOS),
            dtype=np.float32,
        ) / 255.0
        h, w = arr.shape[:2]

    known = a >= 0.995
    out = arr.copy()
    radius = max(1, int(radius))
    for _ in range(radius):
        unknown = ~known
        if not unknown.any():
            break
        kp = np.pad(known.astype(np.float32), 1)
        op = np.pad(out, ((1, 1), (1, 1), (0, 0)))
        nsum = np.zeros_like(out)
        ncount = np.zeros((h, w), dtype=np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ks = kp[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
                cs = op[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
                nsum += cs * ks[..., None]
                ncount += ks
        fill = unknown & (ncount > 0)
        if not fill.any():
            break
        out[fill] = nsum[fill] / ncount[fill, None]
        known[fill] = True
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGB")


def merge_masks(masks) -> np.ndarray | None:
    """合并多个 SAM 目标遮罩（逐元素取最大）。"""
    arrays = [np.asarray(m, dtype=np.uint8) for m in masks if m is not None]
    if not arrays:
        return None
    return np.maximum.reduce(arrays).astype(np.uint8)
