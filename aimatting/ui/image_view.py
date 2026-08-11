"""可缩放/平移的抠图预览画布：笔刷遮罩涂抹、裁剪、前后对比。"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

from PIL import Image


_MIN_CROP = 8.0
_HANDLE_CURSORS = {
    "n": Qt.CursorShape.SizeVerCursor,
    "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor,
    "w": Qt.CursorShape.SizeHorCursor,
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
}


def _checker_brush() -> QBrush:
    size = 16
    pm = QPixmap(size * 2, size * 2)
    pm.fill(QColor("#3A3D45"))
    painter = QPainter(pm)
    painter.fillRect(0, 0, size, size, QColor("#2A2D34"))
    painter.fillRect(size, size, size, size, QColor("#2A2D34"))
    painter.end()
    return QBrush(pm)


class ImageView(QGraphicsView):
    """预览画布：滚轮缩放、拖拽平移、笔刷涂抹、裁剪、前后对比。"""

    brushStroke = Signal(float, float)
    brushStrokeFinished = Signal()
    brushSizeChanged = Signal(int)
    toolActionRequested = Signal()
    zoomChanged = Signal(float)
    cropRectChanged = Signal()
    cropConfirmed = Signal()
    cropCanceled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(_checker_brush())
        self.setScene(self._scene)
        self._item = QGraphicsPixmapItem()
        self._scene.addItem(self._item)
        self._overlay_item = QGraphicsPixmapItem()
        self._overlay_item.setZValue(1)
        self._scene.addItem(self._overlay_item)
        self._cursor_ring = QGraphicsEllipseItem()
        self._cursor_ring.setZValue(2)
        self._cursor_ring.setPen(QPen(QColor(255, 255, 255, 235), 1.6))
        self._cursor_ring.setBrush(Qt.BrushStyle.NoBrush)
        self._cursor_inner = QGraphicsEllipseItem()
        self._cursor_inner.setZValue(2)
        self._cursor_inner.setPen(QPen(QColor(120, 200, 255, 220), 1.2))
        self._cursor_inner.setBrush(Qt.BrushStyle.NoBrush)
        self._cursor_dot = QGraphicsEllipseItem()
        self._cursor_dot.setZValue(2)
        self._cursor_dot.setPen(QPen(QColor(255, 255, 255), 1.0))
        self._cursor_dot.setBrush(QColor(255, 255, 255))
        self._scene.addItem(self._cursor_ring)
        self._scene.addItem(self._cursor_inner)
        self._scene.addItem(self._cursor_dot)
        self._cursor_items = (self._cursor_ring, self._cursor_inner, self._cursor_dot)
        self._hide_cursor()

        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform)
        self._zoom = 1.0
        self._zoom_anim: QVariantAnimation | None = None
        self._brush_active = False
        self._painting = False
        self._brush_size = 60
        self._brush_hardness = 0.7
        self._crop_mode = False
        self._crop_rect: QRectF | None = None
        self._crop_hover_handle: str | None = None
        self._crop_drag: str | None = None  # "create" | "move" | 手柄名称
        self._crop_drag_offset = QPointF()
        self._crop_start_rect = QRectF()
        self._crop_start_pos = QPointF()
        self._compare_enabled = False
        self._compare_ratio = 0.5
        self._compare_original = QPixmap()
        self._compare_result = QPixmap()
        self._compare_dragging = False
        self.setMouseTracking(True)

    # ---------- 图像 ----------
    def set_pil_image(self, image: Image.Image, fit: bool = True) -> None:
        image = image.convert("RGBA")
        data = image.tobytes("raw", "RGBA")
        qimg = QImage(
            data,
            image.width,
            image.height,
            image.width * 4,
            QImage.Format.Format_RGBA8888,
        )
        pixmap = QPixmap.fromImage(qimg.copy())
        self._item.setPixmap(pixmap)
        self._overlay_item.setPixmap(QPixmap())
        self._scene.setSceneRect(self._item.boundingRect())
        if self._crop_mode and self._crop_rect is None:
            self._crop_rect = self._image_rect()
            self.cropRectChanged.emit()
        if fit:
            self.fit()

    def clear_image(self) -> None:
        self._item.setPixmap(QPixmap())
        self._overlay_item.setPixmap(QPixmap())
        self._scene.setSceneRect(QRectF(0, 0, 0, 0))

    def set_overlay(self, pixmap: QPixmap) -> None:
        self._overlay_item.setPixmap(pixmap)

    @property
    def has_image(self) -> bool:
        return not self._item.pixmap().isNull()

    # ---------- 缩放/平移 ----------
    def fit(self) -> None:
        if self.has_image:
            self._stop_zoom_anim()
            self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)
            # 显示真实缩放比例，避免「适合窗口」后标签仍写 100%
            self._zoom = self.transform().m11()
            self.zoomChanged.emit(self._zoom)

    def actual_size(self) -> None:
        self._stop_zoom_anim()
        self.resetTransform()
        self._zoom = 1.0
        self.zoomChanged.emit(1.0)

    def zoom_in(self) -> None:
        self._apply_zoom(1.25)

    def zoom_out(self) -> None:
        self._apply_zoom(1.0 / 1.25)

    def _apply_zoom(self, factor: float) -> None:
        start = self._current_zoom()
        target = start * factor
        if not (0.02 <= target <= 100.0):
            return
        self._zoom = target
        self.zoomChanged.emit(target)
        self._stop_zoom_anim()
        anim = QVariantAnimation(self)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        prev = [start]

        def on_frame(f: float) -> None:
            self.scale(f / prev[0], f / prev[0])
            prev[0] = f

        anim.valueChanged.connect(on_frame)
        anim.finished.connect(anim.deleteLater)
        anim.finished.connect(lambda: setattr(self, "_zoom_anim", None))
        self._zoom_anim = anim
        anim.start()

    def _current_zoom(self) -> float:
        try:
            running = (
                self._zoom_anim is not None
                and self._zoom_anim.state() == QVariantAnimation.State.Running
            )
        except RuntimeError:
            self._zoom_anim = None
            running = False
        if running:
            return float(self._zoom_anim.currentValue())
        return self._zoom

    def _stop_zoom_anim(self) -> None:
        if self._zoom_anim is not None:
            anim = self._zoom_anim
            self._zoom_anim = None
            try:
                anim.stop()
                anim.deleteLater()
            except RuntimeError:
                pass

    def wheelEvent(self, event) -> None:  # noqa: N802
        if event.angleDelta().y() == 0:
            return
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if self._brush_active and not ctrl:
            # 画笔工具下滚轮 = 调整画笔大小；Ctrl+滚轮 = 缩放
            step = 5 if event.angleDelta().y() > 0 else -5
            new_size = max(1, min(500, self._brush_size + step))
            if new_size != self._brush_size:
                self._brush_size = new_size
                self._update_cursor()
                self.brushSizeChanged.emit(new_size)
            event.accept()
            return
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self._apply_zoom(factor)
        event.accept()

    # ---------- 笔刷遮罩 ----------
    def set_brush_active(self, active: bool) -> None:
        self._brush_active = bool(active)
        if active:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)
            self._show_cursor()
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.unsetCursor()
            self._hide_cursor()

    def set_brush_cursor(self, size: int, hardness: float) -> None:
        self._brush_size = max(1, int(size))
        self._brush_hardness = float(max(0.0, min(1.0, hardness)))
        self._update_cursor()

    def _hide_cursor(self) -> None:
        for item in self._cursor_items:
            item.hide()

    def _show_cursor(self) -> None:
        if self._brush_active:
            self._update_cursor()

    def _update_cursor(self) -> None:
        if not self._brush_active:
            self._hide_cursor()
            return
        for item in self._cursor_items:
            item.show()

    def _move_cursor(self, scene_pos: QPointF) -> None:
        if not self._brush_active:
            return
        r = self._brush_size / 2.0
        self._cursor_ring.setRect(
            QRectF(scene_pos.x() - r, scene_pos.y() - r, self._brush_size, self._brush_size)
        )
        inner_r = max(0.5, r * self._brush_hardness)
        self._cursor_inner.setRect(
            QRectF(
                scene_pos.x() - inner_r,
                scene_pos.y() - inner_r,
                inner_r * 2,
                inner_r * 2,
            )
        )
        self._cursor_dot.setRect(
            QRectF(scene_pos.x() - 1.2, scene_pos.y() - 1.2, 2.4, 2.4)
        )

    # ---------- 裁剪 ----------
    def set_crop_mode(self, active: bool) -> None:
        self._crop_mode = bool(active)
        self._crop_drag = None
        self._crop_hover_handle = None
        if active:
            self._brush_active = False
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)
            self._hide_cursor()
            if self.has_image and self._crop_rect is None:
                self._crop_rect = self._image_rect()
            self.cropRectChanged.emit()
        else:
            self._crop_rect = None
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.unsetCursor()

    def crop_rect(self) -> QRectF | None:
        """当前裁剪区域（场景坐标 = 图像像素坐标）。"""
        if self._crop_rect is None:
            return None
        return QRectF(self._crop_rect)

    def crop_hover_handle(self) -> str | None:
        """当前鼠标悬停/拖拽中的裁剪控制点，用于高亮反馈。"""
        return self._crop_hover_handle

    def clear_crop_rect(self) -> None:
        self._crop_rect = None
        self._crop_drag = None
        self.cropRectChanged.emit()

    def _image_rect(self) -> QRectF:
        return QRectF(self._item.boundingRect())

    def _crop_click_outside_image(self, scene_pos: QPointF) -> bool:
        """判断场景点是否位于图片外（不再用于确认裁剪）。"""
        return self._crop_rect is not None and not self._image_rect().contains(scene_pos)

    def _clamp_rect(self, rect: QRectF) -> QRectF:
        r = rect.normalized()
        bounds = self._image_rect()
        if bounds.isNull():
            return r
        x0 = max(bounds.left(), r.left())
        y0 = max(bounds.top(), r.top())
        x1 = min(bounds.right(), r.right())
        y1 = min(bounds.bottom(), r.bottom())
        if x1 - x0 < _MIN_CROP:
            if r.center().x() <= bounds.center().x():
                x1 = min(bounds.right(), x0 + _MIN_CROP)
            else:
                x0 = max(bounds.left(), x1 - _MIN_CROP)
        if y1 - y0 < _MIN_CROP:
            if r.center().y() <= bounds.center().y():
                y1 = min(bounds.bottom(), y0 + _MIN_CROP)
            else:
                y0 = max(bounds.top(), y1 - _MIN_CROP)
        return QRectF(x0, y0, x1 - x0, y1 - y0)

    def _handle_at(self, view_pos: QPointF, tolerance: float = 18.0) -> str | None:
        if self._crop_rect is None:
            return None
        rect = self._crop_rect
        points = {
            "nw": rect.topLeft(),
            "n": QPointF(rect.center().x(), rect.top()),
            "ne": rect.topRight(),
            "e": QPointF(rect.right(), rect.center().y()),
            "se": rect.bottomRight(),
            "s": QPointF(rect.center().x(), rect.bottom()),
            "sw": rect.bottomLeft(),
            "w": QPointF(rect.left(), rect.center().y()),
        }
        best: str | None = None
        best_d = tolerance
        for name, scene_pt in points.items():
            view_pt = self.mapFromScene(scene_pt)
            dx = view_pt.x() - view_pos.x()
            dy = view_pt.y() - view_pos.y()
            d = (dx * dx + dy * dy) ** 0.5
            if d <= best_d:
                best = name
                best_d = d
        return best

    def _apply_handle(
        self, handle: str, start_rect: QRectF, start_pos: QPointF, pos: QPointF
    ) -> QRectF:
        r = QRectF(start_rect)
        dx = pos.x() - start_pos.x()
        dy = pos.y() - start_pos.y()
        if "n" in handle:
            r.setTop(r.top() + dy)
        if "s" in handle:
            r.setBottom(r.bottom() + dy)
        if "w" in handle:
            r.setLeft(r.left() + dx)
        if "e" in handle:
            r.setRight(r.right() + dx)
        return self._clamp_rect(r)

    def _crop_cursor(self, view_pos: QPointF) -> Qt.CursorShape:
        """裁剪模式下的光标反馈：手柄=缩放、框内=移动、框外=新建选区。"""
        if self._crop_rect is None:
            return Qt.CursorShape.CrossCursor
        handle = self._handle_at(view_pos)
        if handle:
            return _HANDLE_CURSORS.get(handle, Qt.CursorShape.CrossCursor)
        pt = view_pos.toPoint() if isinstance(view_pos, QPointF) else view_pos
        scene_pos = self.mapToScene(pt)
        if self._crop_rect.contains(scene_pos):
            return Qt.CursorShape.SizeAllCursor
        return Qt.CursorShape.CrossCursor

    # ---------- 前后对比 ----------
    def set_compare_images(self, original: QPixmap, result: QPixmap) -> None:
        self._compare_original = original
        self._compare_result = result
        if self._compare_enabled:
            self._rebuild_compare()

    def set_compare_enabled(self, enabled: bool) -> None:
        self._compare_enabled = bool(enabled)
        self._compare_dragging = False
        if enabled:
            self._rebuild_compare()

    def set_compare_ratio(self, ratio: float) -> None:
        self._compare_ratio = float(max(0.0, min(1.0, ratio)))
        if self._compare_enabled:
            self._rebuild_compare()

    def _rebuild_compare(self) -> None:
        if self._compare_result.isNull():
            return
        w = self._compare_result.width()
        combined = self._compare_result.copy()
        if not self._compare_original.isNull() and self._compare_ratio > 0:
            painter = QPainter(combined)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            split_w = int(w * self._compare_ratio)
            painter.drawPixmap(
                QRectF(0, 0, split_w, combined.height()),
                self._compare_original,
                QRectF(0, 0, split_w, self._compare_original.height()),
            )
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawLine(split_w, 0, split_w, combined.height())
            # 中间拖拽圆点：方便抓住分隔线
            cy = combined.height() / 2.0
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.setBrush(QColor(76, 141, 255))
            painter.drawEllipse(QPointF(split_w, cy), 10, 10)
            painter.setBrush(QColor(255, 255, 255))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(split_w, cy), 3.5, 3.5)
            painter.end()
        self._item.setPixmap(combined)

    def _divider_scene_x(self) -> float:
        return self._compare_ratio * self._compare_result.width()

    def _near_divider(self, view_pos: QPointF, tolerance: float = 16.0) -> bool:
        if not self._compare_enabled or self._compare_result.isNull():
            return False
        scene = self.mapToScene(view_pos.toPoint())
        return abs(scene.x() - self._divider_scene_x()) <= tolerance

    # ---------- 鼠标事件 ----------
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if (
            self._compare_enabled
            and event.button() == Qt.MouseButton.LeftButton
            and self._near_divider(event.position())
        ):
            self._compare_dragging = True
            event.accept()
            return
        if self._crop_mode and event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.position().toPoint())
            if self._crop_click_outside_image(pos):
                # 单击图片外空白处不再确认裁剪，避免误触；
                # 双击或按 Enter 才完成裁剪。
                event.accept()
                return
            handle = self._handle_at(event.position())
            if handle:
                self._crop_drag = handle
                self._crop_start_rect = QRectF(self._crop_rect)
                self._crop_start_pos = pos
            elif self._crop_rect is not None and self._crop_rect.contains(pos):
                self._crop_drag = "move"
                self._crop_drag_offset = pos - self._crop_rect.topLeft()
            else:
                self._crop_drag = "create"
                self._crop_drag_offset = pos
                self._crop_rect = self._clamp_rect(QRectF(pos, pos))
                self.cropRectChanged.emit()
            event.accept()
            return
        if self._brush_active and event.button() == Qt.MouseButton.LeftButton:
            self._painting = True
            self._emit_stroke(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self._crop_mode and event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.position().toPoint())
            if (
                self._crop_rect is not None
                and self._crop_rect.contains(pos)
                and self._image_rect().contains(pos)
            ):
                self.cropConfirmed.emit()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._compare_dragging and self._compare_enabled:
            scene = self.mapToScene(event.position().toPoint())
            width = max(1, self._compare_result.width())
            self.set_compare_ratio(scene.x() / width)
            event.accept()
            return
        if self._crop_mode:
            pos = self.mapToScene(event.position().toPoint())
            if self._crop_drag:
                self._crop_hover_handle = self._crop_drag
                if self._crop_drag == "create":
                    self._crop_rect = self._clamp_rect(
                        QRectF(self._crop_drag_offset, pos)
                    )
                elif self._crop_drag == "move":
                    moved = QRectF(self._crop_rect)
                    moved.moveTopLeft(pos - self._crop_drag_offset)
                    self._crop_rect = self._clamp_rect(moved)
                else:
                    self._crop_rect = self._apply_handle(
                        self._crop_drag,
                        self._crop_start_rect,
                        self._crop_start_pos,
                        pos,
                    )
                self.cropRectChanged.emit()
            else:
                handle = self._handle_at(event.position())
                if handle != self._crop_hover_handle:
                    self._crop_hover_handle = handle
                    self.cropRectChanged.emit()
                self.setCursor(self._crop_cursor(event.position()))
            event.accept()
            return
        if self._brush_active:
            self._move_cursor(self.mapToScene(event.position().toPoint()))
            if self._painting:
                self._emit_stroke(event.position())
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._compare_dragging and event.button() == Qt.MouseButton.LeftButton:
            self._compare_dragging = False
            event.accept()
            return
        if self._crop_mode and self._crop_drag and event.button() == Qt.MouseButton.LeftButton:
            self._crop_drag = None
            self._crop_hover_handle = self._handle_at(event.position())
            self.cropRectChanged.emit()
            event.accept()
            return
        if self._painting and event.button() == Qt.MouseButton.LeftButton:
            self._painting = False
            self.brushStrokeFinished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._crop_mode:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._crop_rect is not None:
                    self.cropConfirmed.emit()
                event.accept()
                return
            if key == Qt.Key.Key_Escape:
                self.cropCanceled.emit()
                event.accept()
                return
            if self._crop_rect is not None and key in (
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
            ):
                step = 10.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
                moved = QRectF(self._crop_rect)
                if key == Qt.Key.Key_Up:
                    moved.translate(0, -step)
                elif key == Qt.Key.Key_Down:
                    moved.translate(0, step)
                elif key == Qt.Key.Key_Left:
                    moved.translate(-step, 0)
                else:
                    moved.translate(step, 0)
                self._crop_rect = self._clamp_rect(moved)
                self.cropRectChanged.emit()
                event.accept()
                return
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and self._brush_active
        ):
            # 回车 = 完成当前工具（如画笔遮罩「确定」）
            self.toolActionRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def _emit_stroke(self, view_pos) -> None:
        scene_pos = self.mapToScene(view_pos.toPoint())
        self.brushStroke.emit(scene_pos.x(), scene_pos.y())
