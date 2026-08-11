"""QGoodWindow 风格的原生窗口支持（Windows only）。

把自定义无边框标题栏与 Windows 原生窗口行为结合，参考
https://github.com/antonypro/QGoodWindow 的实现思路：

- ``WM_NCHITTEST`` 原生命中测试：窗口边缘返回 HT*，由系统执行缩放；
  标题栏返回 HTCLIENT（Qt 处理鼠标事件，拖动经 startSystemMove 走系统
  移动循环，支持 Win11 贴靠）；最大化按钮返回 HTMAXBUTTON，
  悬停时系统自动弹出 Win11 贴靠布局浮层；
- ``WM_GETMINMAXINFO`` 约束最小尺寸，避免原生缩放把窗口拖破；
- DWM 圆角（DWMWA_WINDOW_CORNER_PREFERENCE）、沉浸式深色标题栏
  （DWMWA_USE_IMMERSIVE_DARK_MODE）、边框颜色（DWMWA_BORDER_COLOR）；
- 系统菜单：标题栏右键 / Alt+Space 弹出原生系统菜单；
- 最大化状态下拖动标题栏：还原为普通大小并跟随光标（Win11 行为）。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QGuiApplication

# ---------------------------------------------------------------------------
# Win32 常量
# ---------------------------------------------------------------------------
GWL_STYLE = -16

WS_THICKFRAME = 0x00040000
WS_MAXIMIZEBOX = 0x00010000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

WM_NCMOUSEMOVE = 0x00A0
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCLBUTTONDBLCLK = 0x00A3
WM_NCMOUSELEAVE = 0x02A2
WM_NCHITTEST = 0x0084
WM_GETMINMAXINFO = 0x0024
WM_SYSKEYDOWN = 0x0104
WM_SYSCOMMAND = 0x0112
VK_SPACE = 0x20

# WM_NCHITTEST 返回值
HTNOWHERE = 0
HTCLIENT = 1
HTCAPTION = 2
HTMAXBUTTON = 9
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

# 系统菜单命令
SC_SIZE = 0xF000
SC_MOVE = 0xF010
SC_MINIMIZE = 0xF020
SC_MAXIMIZE = 0xF030
SC_CLOSE = 0xF060
SC_RESTORE = 0xF120

MF_BYCOMMAND = 0x0000
MF_ENABLED = 0x0000
MF_GRAYED = 0x0001

TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
TPM_LEFTALIGN = 0x0000
TPM_TOPALIGN = 0x0000

# DWM 属性
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWCP_DEFAULT = 0
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", _POINT),
        ("ptMaxSize", _POINT),
        ("ptMaxPosition", _POINT),
        ("ptMinTrackSize", _POINT),
        ("ptMaxTrackSize", _POINT),
    ]


if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _dwmapi = ctypes.windll.dwmapi

    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowLongW.restype = ctypes.c_long
    _user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    _user32.DefWindowProcW.restype = ctypes.c_longlong
    _user32.DefWindowProcW.argtypes = [
        wintypes.HWND,
        ctypes.c_uint,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    _user32.GetSystemMenu.restype = wintypes.HMENU
    _user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
    _user32.EnableMenuItem.restype = ctypes.c_uint
    _user32.EnableMenuItem.argtypes = [
        wintypes.HMENU,
        ctypes.c_uint,
        ctypes.c_uint,
    ]
    _user32.TrackPopupMenu.restype = ctypes.c_int
    _user32.TrackPopupMenu.argtypes = [
        wintypes.HMENU,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.RECT,
    ]
    _user32.SendMessageW.restype = ctypes.c_longlong
    _user32.SendMessageW.argtypes = [
        wintypes.HWND,
        ctypes.c_uint,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    _user32.GetCursorPos.restype = ctypes.c_int
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]

    _dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
    _dwmapi.DwmSetWindowAttribute.argtypes = [
        wintypes.HWND,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
else:
    _user32 = None
    _dwmapi = None


def _lparam_xy(lparam: int) -> tuple[int, int]:
    """从 LPARAM 解出物理屏幕坐标（带符号）。"""
    return (
        ctypes.c_short(lparam & 0xFFFF).value,
        ctypes.c_short((lparam >> 16) & 0xFFFF).value,
    )


class GoodWindowMixin:
    """混入任意 QWidget 窗口，获得 QGoodWindow 风格的原生窗口行为。

    子类需要提供：
    - ``max_button``：自定义最大化/还原按钮（用于触发 Win11 贴靠布局）；
    - ``_toggle_maximize()`` / ``_animate_minimize()`` / ``_animate_close()``：
      窗口按钮行为；
    - ``_is_maximized``：当前最大化状态（``changeEvent`` 中与原生状态同步）。
    """

    #: 标题栏高度（逻辑像素），与自绘标题栏高度保持一致。
    TITLE_BAR_HEIGHT = 44
    #: 原生缩放边框宽度（逻辑像素）。
    RESIZE_BORDER = 8
    #: 最小窗口尺寸（逻辑像素），与主窗口允许的缩放下限一致。
    MIN_WIDTH = 900
    MIN_HEIGHT = 600
    #: 原生边框颜色（未最大化时 DWM 描边的 1px 边框）。
    BORDER_COLOR = "#23252B"

    _gw_installed = False
    _gw_hwnd = 0
    _gw_caption_hover = 0
    _gw_caption_pressed = 0
    _gw_title_bar = None

    # ------------------------------------------------------------------
    # 安装 / DWM
    # ------------------------------------------------------------------
    def install_good_window(self) -> None:
        """安装原生窗口支持。窗口句柄可用后调用（winId 会创建句柄）。"""
        if self._gw_installed or _user32 is None or _dwmapi is None:
            return
        hwnd = int(self.winId())
        if not hwnd:
            return
        self._gw_hwnd = hwnd
        self._gw_add_native_styles()
        self._gw_apply_dwm()
        self._gw_installed = True

    def _gw_add_native_styles(self) -> None:
        """补上 WS_THICKFRAME/WS_MAXIMIZEBOX，让系统执行缩放与贴靠。"""
        hwnd = self._gw_hwnd
        if not hwnd:
            return
        style = _user32.GetWindowLongW(hwnd, GWL_STYLE)
        style |= WS_THICKFRAME | WS_MAXIMIZEBOX
        _user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        _user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
            | SWP_FRAMECHANGED,
        )

    def _gw_apply_dwm(self) -> None:
        """设置沉浸式深色标题栏、圆角与边框颜色。"""
        hwnd = self._gw_hwnd
        if not hwnd:
            return
        enabled = ctypes.c_int(1)
        _dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(enabled),
            ctypes.sizeof(enabled),
        )
        self._gw_update_corners()
        color = QColor(self.BORDER_COLOR)
        colorref = (color.blue() << 16) | (color.green() << 8) | color.red()
        border = ctypes.c_int(colorref)
        _dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_BORDER_COLOR,
            ctypes.byref(border),
            ctypes.sizeof(border),
        )

    def _gw_update_corners(self) -> None:
        """最大化时直角，普通状态圆角（与 Windows 11 原生行为一致）。"""
        if not self._gw_hwnd:
            return
        maximized = bool(
            getattr(self, "_is_maximized", False) or self.isMaximized()
        )
        pref = ctypes.c_int(
            DWMWCP_DONOTROUND if maximized else DWMWCP_ROUND
        )
        _dwmapi.DwmSetWindowAttribute(
            self._gw_hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref),
            ctypes.sizeof(pref),
        )

    # ------------------------------------------------------------------
    # nativeEvent：把窗口交给系统处理
    # ------------------------------------------------------------------
    def nativeEvent(self, event_type, message):  # noqa: N802
        if event_type != b"windows_generic_MSG":
            return False, 0
        if not self._gw_installed or not self._gw_hwnd:
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
        except (TypeError, ValueError):
            return False, 0

        m = msg.message

        if m == WM_NCHITTEST:
            return True, self._gw_nc_hit_test(msg.lParam)

        elif m == WM_GETMINMAXINFO:
            self._gw_minmax_info(msg.lParam)
            return True, 0

        elif m == WM_NCLBUTTONDOWN:
            hit = self._gw_nc_hit_test(msg.lParam)
            if hit == HTMAXBUTTON:
                self._gw_caption_pressed = HTMAXBUTTON
                self._gw_set_button_state(
                    getattr(self, "max_button", None), pressed=True
                )
                self.activateWindow()
                return True, 0
            # startSystemMove() 发送的消息 wParam=HTCAPTION 但 lParam=0，
            # 命中测试算不出位置，这里按 wParam 兜底
            if hit == HTCAPTION or msg.wParam == HTCAPTION:
                _user32.DefWindowProcW(
                    self._gw_hwnd, m, msg.wParam, msg.lParam
                )
                return True, 0

        elif m == WM_NCLBUTTONDBLCLK:
            hit = self._gw_nc_hit_test(msg.lParam)
            if hit == HTMAXBUTTON:
                # 双击最大化按钮只执行一次动作
                return True, 0

        elif m == WM_NCLBUTTONUP:
            hit = self._gw_nc_hit_test(msg.lParam)
            pressed = self._gw_caption_pressed
            if pressed:
                self._gw_caption_pressed = 0
                self._gw_set_button_state(
                    getattr(self, "max_button", None), pressed=False
                )
                if hit == pressed:
                    self._toggle_maximize()
                return True, 0

        elif m == WM_NCMOUSEMOVE:
            hit = self._gw_nc_hit_test(msg.lParam)
            if hit == HTMAXBUTTON:
                if self._gw_caption_hover != HTMAXBUTTON:
                    self._gw_caption_hover = HTMAXBUTTON
                    self._gw_set_button_state(
                        getattr(self, "max_button", None), hover=True
                    )
            elif self._gw_caption_hover:
                self._gw_clear_button_hover()

        elif m == WM_NCMOUSELEAVE:
            self._gw_clear_button_hover()

        elif m == WM_SYSKEYDOWN and msg.wParam == VK_SPACE:
            self._gw_show_system_menu(at_cursor=False)
            return True, 0

        return False, 0

    # ------------------------------------------------------------------
    # 命中测试
    # ------------------------------------------------------------------
    def _gw_nc_hit_test(self, lparam: int) -> int:
        px, py = _lparam_xy(lparam)
        dpr = self.devicePixelRatioF() or 1.0
        gpos = QPoint(int(px / dpr), int(py / dpr))
        local = self.mapFromGlobal(gpos)
        if not self.rect().contains(local):
            return HTNOWHERE

        w, h = self.width(), self.height()
        b = self.RESIZE_BORDER
        maximized = bool(
            getattr(self, "_is_maximized", False) or self.isMaximized()
        )

        # 缩放边框（非最大化状态）
        if not maximized:
            top = local.y() <= b
            bottom = local.y() >= h - b
            left = local.x() <= b
            right = local.x() >= w - b
            if top and left:
                return HTTOPLEFT
            if top and right:
                return HTTOPRIGHT
            if bottom and left:
                return HTBOTTOMLEFT
            if bottom and right:
                return HTBOTTOMRIGHT
            if top:
                return HTTOP
            if bottom:
                return HTBOTTOM
            if left:
                return HTLEFT
            if right:
                return HTRIGHT

        # 标题栏区域
        if local.y() <= self.TITLE_BAR_HEIGHT:
            max_button = getattr(self, "max_button", None)
            # 最大化按钮：非最大化时交给系统，悬停弹出 Win11 贴靠布局
            if (
                not maximized
                and max_button is not None
                and self._gw_point_in_widget(max_button, gpos)
            ):
                return HTMAXBUTTON
            widget = self.childAt(local)
            node = widget
            while node is not None:
                if node is self._gw_title_bar:
                    # 标题栏统一返回 HTCLIENT：由 Qt 处理鼠标事件，
                    # 拖动通过 startSystemMove() 启动原生移动循环，
                    # 这样双击/右键菜单不会被非客户区消息吞掉。
                    return HTCLIENT
                node = node.parentWidget()

        return HTCLIENT

    @staticmethod
    def _gw_point_in_widget(widget, gpos: QPoint) -> bool:
        return widget.rect().contains(widget.mapFromGlobal(gpos))

    def _gw_minmax_info(self, lparam: int) -> None:
        mmi = _MINMAXINFO.from_address(lparam)
        dpr = self.devicePixelRatioF() or 1.0
        min_w = max(self.minimumWidth(), self.MIN_WIDTH)
        min_h = max(self.minimumHeight(), self.MIN_HEIGHT)
        mmi.ptMinTrackSize.x = int(min_w * dpr)
        mmi.ptMinTrackSize.y = int(min_h * dpr)
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            wa = screen.availableGeometry()
            mmi.ptMaxPosition.x = int(wa.x() * dpr)
            mmi.ptMaxPosition.y = int(wa.y() * dpr)
            mmi.ptMaxSize.x = int(wa.width() * dpr)
            mmi.ptMaxSize.y = int(wa.height() * dpr)

    # ------------------------------------------------------------------
    # 按钮状态（最大化按钮走非客户区，Qt 收不到 hover/press）
    # ------------------------------------------------------------------
    def _gw_set_button_state(
        self, button, hover: bool | None = None, pressed: bool | None = None
    ) -> None:
        if button is None:
            return
        changed = False
        if hover is not None:
            changed |= bool(button.property("gw_hover")) != hover
            button.setProperty("gw_hover", hover)
        if pressed is not None:
            changed |= bool(button.property("gw_pressed")) != pressed
            button.setProperty("gw_pressed", pressed)
        if changed:
            style = button.style()
            style.unpolish(button)
            style.polish(button)
            button.update()

    def _gw_clear_button_hover(self) -> None:
        if self._gw_caption_hover:
            self._gw_caption_hover = 0
            self._gw_set_button_state(
                getattr(self, "max_button", None), hover=False
            )

    # ------------------------------------------------------------------
    # 系统菜单 / 行为
    # ------------------------------------------------------------------
    def _gw_show_system_menu(self, at_cursor: bool = True) -> None:
        hwnd = self._gw_hwnd
        menu = _user32.GetSystemMenu(hwnd, False)
        if not menu:
            return
        maximized = bool(
            getattr(self, "_is_maximized", False) or self.isMaximized()
        )
        _user32.EnableMenuItem(
            menu, SC_RESTORE, MF_BYCOMMAND | (MF_ENABLED if maximized else MF_GRAYED)
        )
        _user32.EnableMenuItem(
            menu, SC_MOVE, MF_BYCOMMAND | (MF_ENABLED if not maximized else MF_GRAYED)
        )
        _user32.EnableMenuItem(
            menu, SC_SIZE, MF_BYCOMMAND | (MF_ENABLED if not maximized else MF_GRAYED)
        )
        _user32.EnableMenuItem(
            menu,
            SC_MAXIMIZE,
            MF_BYCOMMAND | (MF_ENABLED if not maximized else MF_GRAYED),
        )
        _user32.EnableMenuItem(menu, SC_MINIMIZE, MF_BYCOMMAND | MF_ENABLED)
        _user32.EnableMenuItem(menu, SC_CLOSE, MF_BYCOMMAND | MF_ENABLED)

        if at_cursor:
            pos = _POINT()
            _user32.GetCursorPos(ctypes.byref(pos))
            x, y = pos.x, pos.y
        else:
            dpr = self.devicePixelRatioF() or 1.0
            tl = self.frameGeometry().topLeft()
            x, y = int(tl.x() * dpr), int(tl.y() * dpr)

        cmd = _user32.TrackPopupMenu(
            menu,
            TPM_RETURNCMD | TPM_NONOTIFY | TPM_LEFTALIGN | TPM_TOPALIGN,
            x,
            y,
            0,
            hwnd,
            None,
        )
        if cmd in (SC_RESTORE, SC_MAXIMIZE):
            self._toggle_maximize()
        elif cmd == SC_MINIMIZE:
            self._animate_minimize()
        elif cmd == SC_CLOSE:
            self._animate_close()
        elif cmd in (SC_MOVE, SC_SIZE):
            _user32.SendMessageW(hwnd, WM_SYSCOMMAND, cmd, 0)

    def _gw_sync_max_button(self) -> None:
        button = getattr(self, "max_button", None)
        if button is None:
            return
        button.setText("□" if not self._is_maximized else "❐")

    def _gw_show_menu_for_key(self) -> None:
        """Alt+Space 的 Qt 兜底（部分场景系统键不到达窗口）。"""
        self._gw_show_system_menu(at_cursor=False)

    @staticmethod
    def _gw_is_alt_space(event) -> bool:
        return (
            event.key() == Qt.Key.Key_Space
            and bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        )
