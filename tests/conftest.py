from __future__ import annotations

import os

# 测试环境不启动后台模型预加载，避免每个用例加载 1GB 模型
os.environ.setdefault("AIMATTING_NO_PRELOAD", "1")
