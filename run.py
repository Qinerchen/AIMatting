"""AIMatting 桌面程序启动入口。"""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aimatting.app import main  # noqa: E402


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()  # PyInstaller 打包后子进程支持
    main()
