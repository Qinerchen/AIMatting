from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


APP_NAME = "AIMatting"
APP_VERSION = "0.0.8"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


MODEL_DIR = app_root() / "models"
SETTINGS_PATH = app_root() / "settings.json"


# 官方 BiRefNet 仓库（MIT License）发布的 ONNX 模型
MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "birefnet_general_v2": {
        "name": "BiRefNet 通用模型（主体识别更完整，默认）",
        "filename": "BiRefNet_HR-general-epoch_130.onnx",
        "url": "https://github.com/ZhengPeng7/BiRefNet/releases/download/v1/"
        "BiRefNet_HR-general-epoch_130.onnx",
        "size_bytes": 1_098_928_953,
        "recommended_max_side": 1024,
        "input_shape": (2048, 2048),
        "description": "与 AI_Matting_V2 同族的通用主体识别模型（官方 HR-general）："
        "先识别完整主体再生成遮罩，配合清晰边缘后处理，复杂背景下识别更完整。",
    },
    "birefnet_hr_matting": {
        "name": "BiRefNet HR-matting（高精度抠图）",
        "filename": "BiRefNet_HR-matting-epoch_135.onnx",
        "url": "https://github.com/ZhengPeng7/BiRefNet/releases/download/v1/"
        "BiRefNet_HR-matting-epoch_135.onnx",
        "size_bytes": 1_048 * 1024 * 1024,
        "recommended_max_side": 2048,
        "input_shape": (2048, 2048),
        "description": "2048x2048 分辨率训练的 matting 模型，发丝、毛发、玻璃等"
        "半透明与细边缘场景效果好，适合 4K 及以下图像。",
    },
}

DEFAULT_MODEL_ID = "birefnet_general_v2"

DEFAULT_SETTINGS: dict[str, Any] = {
    "model_id": DEFAULT_MODEL_ID,
    "infer_max_side": 0,          # 0 = 按模型推荐档位
    "bg_enabled": True,
    "bg_color": "#4CAF50",
    "bg_opacity": 100,            # 0-100
    "output_format": "png",       # png / jpg / webp
    "output_suffix": "抠图后",
    "save_dir": "",
    "quality": 95,
    "brush_size": 40,
    "brush_hardness": 80,
    "retouch_size": 60,
    "retouch_hardness": 70,
    "auto_matte": True,           # 导入图片后自动执行一次抠图
    "defringe_radius": 4,         # 去色边扩散半径
    "release_model_after_matte": True,   # 抠图完成后释放模型内存
    "use_tensorrt": False,               # 优先使用 TensorRT（若可用）
    "preprocess": {               # 亮度/对比度/饱和度/色温，-100..100
        "brightness": 0,
        "contrast": 0,
        "saturation": 0,
        "temperature": 0,
    },
}


def model_file_path(model_id: str) -> Path:
    return MODEL_DIR / MODEL_REGISTRY[model_id]["filename"]


def model_status(model_id: str) -> str:
    path = model_file_path(model_id)
    if not path.exists():
        return "未下载"
    expected = MODEL_REGISTRY[model_id].get("size_bytes", 0)
    if expected and abs(path.stat().st_size - expected) > 1024 * 1024:
        return "不完整"
    return "已下载"




class Settings:
    """轻量 JSON 配置，保存到软件根目录。"""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path else SETTINGS_PATH
        self._data = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._data = _deep_merge(dict(DEFAULT_SETTINGS), loaded)
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get_preprocess(self) -> dict[str, int]:
        return dict(self._data.get("preprocess", {}))

    def set_preprocess(self, values: dict[str, int]) -> None:
        self._data["preprocess"] = dict(values)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
