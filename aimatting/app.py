"""应用程序装配与启动。"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _install_crash_logger() -> None:
    """把未捕获异常写入软件根目录 crash.log，便于定位启动失败。"""
    from aimatting.core.config import app_root

    log_path = app_root() / "crash.log"

    def hook(exc_type, exc_value, exc_tb) -> None:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        except OSError:
            pass

    sys.excepthook = hook


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import Theme, setTheme, setThemeColor

    from aimatting.core.config import app_root

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("AIMatting")
    app.setOrganizationName("AIMatting")
    app.setWindowIcon(QIcon(str(app_root() / "assets" / "aimatting_icon.png")))
    setTheme(Theme.DARK)
    setThemeColor("#4C8DFF")
    # 细灰分割线：左右面板与中间画布之间的间隔保持 1px、低对比度
    app.setStyleSheet(
        "QSplitter::handle { background: rgba(255, 255, 255, 0.08); }"
        "QSplitter::handle:horizontal { width: 1px; }"
        "QSplitter::handle:vertical { height: 1px; }"
        "QSplitter::handle:hover { background: rgba(255, 255, 255, 0.14); }"
    )

    from aimatting.ui.main_window import MainWindow

    try:
        window = MainWindow()
        window.show()
        return app.exec()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        from aimatting.core.config import app_root

        log_path = app_root() / "crash.log"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except OSError:
            pass
        raise


if __name__ == "__main__":
    _install_crash_logger()
    sys.exit(main())
