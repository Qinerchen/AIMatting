"""屏幕取色（吸管）：全屏透明覆盖层 + 跟随光标的放大镜预览。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QGuiApplication,
    QRegion,
)
from PySide6.QtWidgets import QDialog, QWidget


_PATCH = 15       # 采样区域边长（像素）
_SCALE = 12       # 每个像素放大倍数
_RADIUS = _PATCH * _SCALE // 2


def eyedropper_icon() -> QIcon:
    """吸管按钮图标：斜杆 + 顶部圆球 + 底部尖嘴。"""
    def draw(p, color: QColor) -> None:
        pen = QPen(
            color,
            2.4,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        # 斜杆
        p.drawLine(QPoint(5, 24), QPoint(19, 10))
        # 顶部圆球（吸管头）
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPoint(21, 8), 3.6, 3.6)
        # 底部尖嘴
        p.drawPolygon(
            [
                QPoint(2, 26),
                QPoint(9, 26),
                QPoint(5, 22),
            ]
        )

    icon = QIcon()
    icon.addPixmap(_paint_icon(draw, QColor("#E6E8EE")), QIcon.Mode.Normal)
    icon.addPixmap(_paint_icon(draw, QColor("#4C8DFF")), QIcon.Mode.Active)
    icon.addPixmap(_paint_icon(draw, QColor("#4C8DFF")), QIcon.Mode.Selected)
    return icon


def _paint_icon(draw, color: QColor) -> QPixmap:
    pm = QPixmap(28, 28)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw(painter, color)
    painter.end()
    return pm


class Eyedropper(QDialog):
    """选择屏幕任意位置的颜色。

    用法：``picker = Eyedropper(parent); if picker.exec(): color = picker.color()``
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._picked: QColor | None = None
        self._screens: list[tuple[object, QRect, QPixmap]] = []
        self._capture_screens()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(self._virtual_geometry())
        self.setModal(True)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(30)
        self._refresh_timer.timeout.connect(self.update)

    # ------------------------------------------------------------------
    # 屏幕采集与取色
    # ------------------------------------------------------------------
    def _virtual_geometry(self) -> QRect:
        rect = QRect()
        for screen in QGuiApplication.screens():
            rect = rect.united(screen.geometry())
        return rect

    def _capture_screens(self) -> None:
        self._screens = []
        for screen in QGuiApplication.screens():
            pixmap = screen.grabWindow(0)
            self._screens.append((screen, screen.geometry(), pixmap))

    def _screen_and_pixmap_at(
        self, global_pos: QPoint
    ) -> tuple[object | None, QRect | None, QPixmap | None]:
        for screen, geometry, pixmap in self._screens:
            if geometry.contains(global_pos):
                return screen, geometry, pixmap
        return None, None, None

    def _color_at(self, global_pos: QPoint) -> QColor:
        screen, geometry, pixmap = self._screen_and_pixmap_at(global_pos)
        if geometry is None or pixmap is None or pixmap.isNull():
            return QColor(0, 0, 0)
        image = pixmap.toImage()
        ratio = screen.devicePixelRatio() if screen is not None else 1.0
        local = global_pos - geometry.topLeft()
        x = max(0, min(image.width() - 1, int(local.x() * ratio)))
        y = max(0, min(image.height() - 1, int(local.y() * ratio)))
        return QColor(image.pixel(x, y))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._refresh_timer.stop()
        super().hideEvent(event)

    def color(self) -> QColor:
        return self._picked or QColor(0, 0, 0)

    # ------------------------------------------------------------------
    # 绘制放大镜
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        pos = QCursor.pos()
        color = self._color_at(pos)
        center = self.mapFromGlobal(pos)
        radius = _RADIUS

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 放大镜圆底
        painter.setPen(QPen(QColor(255, 255, 255, 210), 2))
        painter.setBrush(QColor(24, 26, 32, 235))
        painter.drawEllipse(center, radius, radius)

        # 圆内绘制放大的像素
        screen, geometry, pixmap = self._screen_and_pixmap_at(pos)
        if geometry is not None and pixmap is not None and not pixmap.isNull():
            image = pixmap.toImage()
            ratio = screen.devicePixelRatio() if screen is not None else 1.0
            local = pos - geometry.topLeft()
            cx, cy = center.x(), center.y()
            region = QRegion(
                QRect(cx - radius, cy - radius, radius * 2, radius * 2),
                QRegion.RegionType.Ellipse,
            )
            painter.setClipRegion(region)
            half = _PATCH // 2
            for dy in range(-half, half + 1):
                for dx in range(-half, half + 1):
                    x = max(
                        0,
                        min(image.width() - 1, int(local.x() * ratio) + dx),
                    )
                    y = max(
                        0,
                        min(image.height() - 1, int(local.y() * ratio) + dy),
                    )
                    painter.fillRect(
                        cx + dx * _SCALE,
                        cy + dy * _SCALE,
                        _SCALE,
                        _SCALE,
                        QColor(image.pixel(x, y)),
                    )
            painter.setClipping(False)

            # 中心像素高亮框 + 十字参考线
            painter.setPen(QPen(QColor(255, 255, 255, 190), 1))
            painter.drawLine(cx - radius, cy, cx + radius, cy)
            painter.drawLine(cx, cy - radius, cx, cy + radius)
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(
                cx - _SCALE // 2, cy - _SCALE // 2, _SCALE, _SCALE
            )

        # 颜色信息卡
        self._draw_info_card(painter, color, center)
        painter.end()

    def _draw_info_card(self, painter: QPainter, color: QColor, center: QPoint) -> None:
        text = f"{color.name().upper()}  RGB({color.red()}, {color.green()}, {color.blue()})"
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        rect = painter.fontMetrics().boundingRect(text).adjusted(-10, -6, 10, 6)
        rect.moveCenter(center + QPoint(0, _RADIUS + 34))
        # 防止信息卡超出屏幕
        geo = self.geometry()
        if rect.right() > geo.right() - 8:
            rect.moveRight(geo.right() - 8)
        if rect.left() < geo.left() + 8:
            rect.moveLeft(geo.left() + 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(24, 26, 32, 240))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._picked = self._color_at(QCursor.pos())
            self.accept()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.reject()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self.update()
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._picked = self._color_at(QCursor.pos())
            self.accept()
            event.accept()
        else:
            super().keyPressEvent(event)
