"""命令行下载 BiRefNet / SAM ONNX 模型。

用法：
    python scripts/download_model.py                 # 下载推荐模型
    python scripts/download_model.py --model lite    # 下载轻量模型
    python scripts/download_model.py --all           # 下载全部
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aimatting.core.config import MODEL_DIR, MODEL_REGISTRY  # noqa: E402


def download(url: str, save_path: Path) -> None:
    import requests

    save_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"下载：{url}")
    print(f"保存：{save_path}")
    with requests.get(url, stream=True, timeout=30) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        done = 0
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    print(f"\r  {done / 1024 / 1024:.0f}MB / "
                          f"{total / 1024 / 1024:.0f}MB ({pct}%)", end="")
        print()
    print("完成。\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 BiRefNet ONNX 模型")
    parser.add_argument(
        "--model",
        choices=["hr", "lite"],
        default="hr",
        help="hr=高精度抠图模型（约1GB，推荐）；lite=轻量模型（约316MB）",
    )
    parser.add_argument("--all", action="store_true", help="下载全部模型")
    args = parser.parse_args()

    ids = list(MODEL_REGISTRY)
    if not args.all:
        ids = ["birefnet_hr_matting" if args.model == "hr" else "birefnet_lite_2k"]
    for model_id in ids:
        info = MODEL_REGISTRY[model_id]
        target = MODEL_DIR / info["filename"]
        if target.exists() and target.stat().st_size >= info["size_bytes"] - 1024 * 1024:
            print(f"已存在，跳过：{target.name}")
            continue
        download(info["url"], target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
