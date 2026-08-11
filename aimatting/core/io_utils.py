"""图片格式支持、保存与文件命名规则。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
}

FILE_DIALOG_FILTER = (
    "支持图片 (*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp);;"
    "所有文件 (*.*)"
)

FORMAT_LABELS = {
    "png": "PNG（透明背景）",
    "jpg": "JPG（纯色背景）",
    "webp": "WEBP",
}


def is_supported(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def output_extension(fmt: str) -> str:
    return {"png": ".png", "jpg": ".jpg", "jpeg": ".jpg", "webp": ".webp"}.get(
        fmt.lower(), ".png"
    )


def build_output_path(
    source_path: str | Path,
    out_dir: str | Path | None,
    suffix: str,
    fmt: str,
) -> Path:
    """命名规则：原始文件名 + 后缀 + 扩展名。"""
    src = Path(source_path)
    directory = Path(out_dir) if out_dir else src.parent
    name = src.stem + (suffix if suffix else "")
    target = directory / (name + output_extension(fmt))
    # 防覆盖源文件：后缀为空且格式与原图一致时，自动追加安全后缀
    if target.resolve() == src.resolve():
        target = directory / (name + "_out" + output_extension(fmt))
    return target


def save_image(
    image: Image.Image,
    path: str | Path,
    fmt: str = "png",
    quality: int = 95,
) -> Path:
    fmt = fmt.lower()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if fmt in ("jpg", "jpeg"):
        image.convert("RGB").save(target, format="JPEG", quality=int(quality))
    elif fmt == "webp":
        image.convert("RGBA").save(target, format="WEBP", quality=int(quality))
    elif fmt == "tif" or fmt == "tiff":
        image.save(target, format="TIFF")
    else:
        image.save(target, format="PNG")
    return target


def ensure_supported_suffix(name: str) -> str:
    """规范化用户输入的后缀，保证不以扩展名结尾。"""
    name = (name or "").strip()
    if Path(name).suffix:
        name = Path(name).stem
    return name
