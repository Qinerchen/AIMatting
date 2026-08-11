"""BiRefNet ONNX 推理引擎。

输入约定参考官方 BiRefNet 仓库（MIT License）与 Kazuhito00/BiRefNet-ONNX-Sample：
- 预处理：RGB、ImageNet 均值/方差归一化、NCHW float32；
- 后处理：取最后一个输出，squeeze 后做 sigmoid，得到 0-255 的软 alpha。
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
import threading
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image


MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _ensure_nvidia_dll_paths() -> None:
    """把 nvidia 系列包（cuDNN/cuBLAS/CUDA runtime 等）的 bin 目录加入 DLL 搜索路径。

    onnxruntime-gpu 需要外置 cuDNN（如 pip 安装的 nvidia-cudnn-cu13），
    这里让引擎能直接找到其 DLL，无需手动改系统 PATH。
    同时兼容 PyInstaller 打包版：文件可能位于 _internal/nvidia/...。
    """
    if os.name != "nt":
        return
    try:
        roots: list[Path] = []
        try:
            import site

            roots.extend(Path(base) for base in site.getsitepackages())
        except Exception:  # noqa: BLE001
            pass
        if getattr(sys, "frozen", False):
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                roots.append(Path(meipass))
            exe_dir = Path(sys.executable).resolve().parent
            roots.append(exe_dir)
            roots.append(exe_dir / "_internal")

        seen: set[str] = set()
        candidates: list[Path] = []
        for root in roots:
            nvidia_root = root / "nvidia"
            if not nvidia_root.is_dir():
                continue
            candidates.extend(nvidia_root.glob("*/bin"))
            # CUDA 13 consolidated wheel 布局：nvidia/cu13/bin/x86_64
            candidates.extend(nvidia_root.glob("*/bin/*"))
        for bin_dir in candidates:
            if not bin_dir.is_dir():
                continue
            if not (str(bin_dir).lower().endswith("bin") or bin_dir.name in ("x64", "x86_64")):
                continue
            key = str(bin_dir)
            if key in seen:
                continue
            seen.add(key)
            try:
                os.add_dll_directory(key)
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        pass


def _cuda_toolkit_bin_dir() -> str | None:
    """返回系统 CUDA 工具包的 bin 目录（优先 bin\\x64，CUDA 13 新布局）。"""
    if os.name != "nt":
        return None
    candidates: list[str] = []
    env_dir = os.environ.get("CUDA_PATH")
    if env_dir:
        candidates.append(os.path.join(env_dir, "bin", "x64"))
        candidates.append(os.path.join(env_dir, "bin"))
    base = Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA")
    if base.is_dir():
        for ver in sorted(base.iterdir(), key=lambda p: p.name, reverse=True):
            candidates.append(str(ver / "bin" / "x64"))
            candidates.append(str(ver / "bin"))
    for cand in candidates:
        if os.path.isfile(os.path.join(cand, "cudart64_13.dll")) or os.path.isfile(
            os.path.join(cand, "cudart64_12.dll")
        ):
            return cand
    return None


def _preload_cuda_dlls(ort) -> None:
    """用 onnxruntime 官方 preload_dlls 预载 CUDA/cuDNN，避免 CUDA EP 硬崩溃。"""
    if os.name != "nt" or not hasattr(ort, "preload_dlls"):
        return
    cuda_bin = _cuda_toolkit_bin_dir()
    try:
        ort.preload_dlls(cuda=True, cudnn=False, directory=cuda_bin)
    except Exception:  # noqa: BLE001
        if cuda_bin:
            try:
                os.add_dll_directory(cuda_bin)
            except OSError:
                pass
    try:
        # directory="" 表示从 NVIDIA site-packages 中加载 cuDNN
        ort.preload_dlls(cuda=False, cudnn=True, directory="")
    except Exception:  # noqa: BLE001
        pass


def _cuda_cudnn_available() -> bool:
    """CUDA EP 是否可用：要求 cuDNN 动态库能被加载且能解析 cudnnCreate。"""
    lib_names = (
        "cudnn64_9.dll",
        "cudnn64_8.dll",
        "libcudnn.so.9",
        "libcudnn.so.8",
    )
    loader = ctypes.WinDLL if os.name == "nt" else ctypes.CDLL
    for name in lib_names:
        try:
            cudnn = loader(name)
            cudnn.cudnnCreate
            return True
        except (OSError, AttributeError):
            continue
    return False


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x.astype(np.float32)))


class MattingEngine:
    """封装 onnxruntime 的 BiRefNet 推理。会话线程安全，可在工作线程中运行。"""

    def __init__(self) -> None:
        self._session = None
        self._model_path: str | None = None
        self._input_shape: tuple[int, int] | None = None  # (H, W)
        self._input_name: str | None = None
        self._dynamic: bool = False
        self._provider: str = ""
        self._tensorrt = False
        self._load_lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._session is not None

    @property
    def model_path(self) -> str | None:
        return self._model_path

    def set_model_path(self, model_path: str | Path | None) -> None:
        self._model_path = str(model_path) if model_path else None

    def set_tensorrt_enabled(self, enabled: bool) -> None:
        """设置是否优先尝试 TensorRT EP（需已安装且支持）。"""
        self._tensorrt = bool(enabled)

    @property
    def provider(self) -> str:
        return self._provider or "未加载"

    def load(
        self,
        model_path: str | Path,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        with self._load_lock:
            if self._session is not None and self._model_path == str(model_path):
                return  # 已加载同一模型，避免重复加载
            import onnxruntime as ort

            path = str(model_path)
            if progress:
                progress("正在加载模型…")
            _ensure_nvidia_dll_paths()
            _preload_cuda_dlls(ort)
            available = ort.get_available_providers()
            sess_options = ort.SessionOptions()
            # 全量图优化；单会话串行调度，减少线程争用
            sess_options.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            sess_options.inter_op_num_threads = 1
            sess_options.enable_cpu_mem_arena = True
            providers: list[str | tuple[str, dict]] = []
            use_trt = self._tensorrt and "TensorrtExecutionProvider" in available
            if use_trt:
                providers.append("TensorrtExecutionProvider")
            if (
                "CUDAExecutionProvider" in available
                and _cuda_cudnn_available()
            ):
                providers.append(
                    (
                        "CUDAExecutionProvider",
                        {
                            "device_id": 0,
                            # 按需申请显存，避免一次性占满
                            "arena_extend_strategy": "kSameAsRequested",
                            # 用启发式卷积搜索，避免首次推理长时间自动调优
                            "cudnn_conv_algo_search": "HEURISTIC",
                            "cudnn_conv_use_max_workspace": 1,
                        },
                    )
                )
            if "DmlExecutionProvider" in available and not providers:
                providers.append("DmlExecutionProvider")
            providers.append("CPUExecutionProvider")
            try:
                self._session = ort.InferenceSession(
                    path, sess_options=sess_options, providers=providers
                )
            except Exception:
                # TensorRT 首次构建引擎可能失败（显存不足/算子不支持），回退 CUDA/CPU
                if use_trt:
                    providers = [
                        p for p in providers if p != "TensorrtExecutionProvider"
                    ]
                    self._session = ort.InferenceSession(
                        path, sess_options=sess_options, providers=providers
                    )
                else:
                    raise
            # 以会话实际生效的 provider 为准，避免 CUDA 静默回退后仍显示 GPU
            active = self._session.get_providers()
            first = active[0] if active else ""
            if first == "CUDAExecutionProvider":
                self._provider = "CUDA (GPU)"
            elif first == "DmlExecutionProvider":
                self._provider = "DirectML (GPU)"
            elif first == "TensorrtExecutionProvider":
                self._provider = "TensorRT (GPU)"
            else:
                self._provider = "CPU"
            self._model_path = path
            inputs = self._session.get_inputs()
            self._input_name = inputs[0].name
            shape = inputs[0].shape
            self._dynamic = not all(isinstance(d, int) and d > 0 for d in shape[2:4])
            if not self._dynamic:
                self._input_shape = (int(shape[2]), int(shape[3]))
            else:
                self._input_shape = None
            if progress:
                progress(f"模型加载完成（{self._provider}）")

    def unload(self) -> None:
        with self._load_lock:
            self._session = None
            self._model_path = None
            self._input_shape = None
            self._input_name = None
            self._dynamic = False
            self._provider = ""

    def _target_size(self, image: Image.Image, max_side: int) -> tuple[int, int]:
        """返回推理用 (W, H)。固定输入尺寸模型用模型自身尺寸。"""
        if self._input_shape:
            return self._input_shape[1], self._input_shape[0]
        w, h = image.size
        target = max_side if max_side and max_side > 0 else 1024
        scale = min(1.0, target / max(h, w))
        tw = max(16, int(round(w * scale / 16.0)) * 16)
        th = max(16, int(round(h * scale / 16.0)) * 16)
        return tw, th

    @staticmethod
    def preprocess(image: Image.Image, tw: int, th: int) -> np.ndarray:
        if image.mode == "RGBA":
            # 透明区域平铺到白底，避免 convert 时变黑
            base = Image.new("RGB", image.size, (255, 255, 255))
            base.paste(image.convert("RGB"), mask=image.getchannel("A"))
            image = base
        elif image.mode != "RGB":
            image = image.convert("RGB")
        resized = image.resize((tw, th), Image.BICUBIC)
        arr = np.asarray(resized, dtype=np.float32) / 255.0
        arr = (arr - MEAN) / STD
        return arr.transpose(2, 0, 1)[np.newaxis, ...]

    @staticmethod
    def postprocess(raw: np.ndarray, size: tuple[int, int]) -> Image.Image:
        mask = np.squeeze(raw)
        if mask.ndim == 3:
            mask = mask[0]
        alpha = sigmoid(mask)
        alpha = np.clip(alpha, 0.0, 1.0) * 255.0
        alpha_img = Image.fromarray(alpha.astype(np.uint8), mode="L")
        # alpha 是平滑软蒙版，双线性即可，速度比 LANCZOS 快得多
        return alpha_img.resize(size, Image.BILINEAR)

    def matte(
        self,
        image: Image.Image,
        max_side: int = 0,
        progress: Callable[[str], None] | None = None,
    ) -> tuple[Image.Image, float]:
        """执行抠图，返回 (alpha L 图, 耗时秒)。"""
        if self._session is None:
            raise RuntimeError("模型尚未加载，请先下载并选择模型")
        tw, th = self._target_size(image, max_side)
        if progress:
            progress(f"预处理图像（{tw}x{th}）…")
        feed = self.preprocess(image, tw, th)
        if progress:
            progress("推理中…")
        t0 = time.perf_counter()
        outputs = self._session.run(None, {self._input_name: feed})
        elapsed = time.perf_counter() - t0
        if progress:
            progress("后处理中…")
        alpha = self.postprocess(outputs[-1], image.size)
        return alpha, elapsed
