"""
TopoEditor — Connection / Link Visual Item for Topology Canvas.
Renders link cables, bandwidth labels, selection highlights,
and updates dynamically as endpoint devices move.
"""

from typing import Optional
import math

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtWidgets import (
    QGraphicsObject, QGraphicsItem, QGraphicsSceneMouseEvent,
    QGraphicsSceneContextMenuEvent, QMenu, QStyleOptionGraphicsItem, QWidget
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath
)


class LinkItem(QGraphicsObject):
    """
    Renders an interactive physical / virtual connection link between two devices.
    Connects src_item and dst_item, automatically tracking device movement.
    Displays configured bandwidth pill directly on the canvas.
    """
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    selected_changed = pyqtSignal(str, bool)

    def __init__(self, link_data, src_item, dst_item, parent=None):
        super().__init__(parent)
        self.data = link_data
        self.src_item = src_item
        self.dst_item = dst_item

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(2)  # Behind nodes (Z=10)

        self._is_hovered = False
        self._pill_rect = QRectF()

        # Register link with both endpoint items
        self.src_item.attach_link(self)
        self.dst_item.attach_link(self)

    def cleanup(self):
        """Detaches from endpoint items when removed."""
        if self.src_item:
            self.src_item.detach_link(self)
        if self.dst_item:
            self.dst_item.detach_link(self)

    def update_data(self, link_data):
        self.data = link_data
        self.update_geometry()

    def update_geometry(self):
        """Notifies scene of geometry change and triggers repaint."""
        self.prepareGeometryChange()
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.selected_changed.emit(self.data.id, bool(value))
            self.update()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.edit_requested.emit(self.data.id)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 5px 18px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #89b4fa;
                color: #11111b;
            }
        """)
        act_edit = menu.addAction(f"✏ Edit Link ({self.data.src.upper()} ↔ {self.data.dst.upper()})...")
        menu.addSeparator()
        act_delete = menu.addAction(f"🗑 Delete Link")

        action = menu.exec(event.screenPos())
        if action == act_edit:
            self.edit_requested.emit(self.data.id)
        elif action == act_delete:
            self.delete_requested.emit(self.data.id)
        event.accept()

    def get_endpoints(self) -> (QPointF, QPointF):
        p1 = self.src_item.get_center_scene_pos()
        p2 = self.dst_item.get_center_scene_pos()
        return p1, p2

    def boundingRect(self) -> QRectF:
        p1, p2 = self.get_endpoints()
        xmin = min(p1.x(), p2.x()) - 40
        xmax = max(p1.x(), p2.x()) + 40
        ymin = min(p1.y(), p2.y()) - 40
        ymax = max(p1.y(), p2.y()) + 40
        return QRectF(xmin, ymin, xmax - xmin, ymax - ymin)

    def shape(self) -> QPainterPath:
        """Thicker hit-testing area for easy clicking and selection."""
        p1, p2 = self.get_endpoints()
        path = QPainterPath()
        path.moveTo(p1)
        path.lineTo(p2)
        stroker = QPainterPath()
        # Create a 14px thick hit detection polygon around line
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        dist = math.hypot(dx, dy)
        if dist > 0:
            nx = -dy / dist * 8.0
            ny = dx / dist * 8.0
            stroker.moveTo(p1.x() + nx, p1.y() + ny)
            stroker.lineTo(p2.x() + nx, p2.y() + ny)
            stroker.lineTo(p2.x() - nx, p2.y() - ny)
            stroker.lineTo(p1.x() - nx, p1.y() - ny)
            stroker.closeSubpath()
        return stroker

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        p1, p2 = self.get_endpoints()
        is_sel = self.isSelected()

        # Link color styling
        if self.data.is_bottleneck:
            base_color = QColor("#f38ba8")  # Red for bottleneck link
        elif self.data.type == "host_edge":
            base_color = QColor("#89b4fa")  # Cyan/Blue for edge
        else:
            base_color = QColor("#cdd6f4")  # Clean silver-white for switch-to-switch trunk

        # 1. Selection & Hover Glow
        if is_sel:
            painter.setPen(QPen(QColor("#f9e2af"), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(p1, p2)
        elif self._is_hovered:
            painter.setPen(QPen(QColor("#89b4fa"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(p1, p2)

        # 2. Main Cable Line
        line_thickness = 3 if self.data.is_bottleneck else 2
        painter.setPen(QPen(base_color, line_thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(p1, p2)

        # 3. Bandwidth Label Pill at Midpoint
        mid_x = (p1.x() + p2.x()) / 2.0
        mid_y = (p1.y() + p2.y()) / 2.0

        label_text = f"{self.data.bw_mbps:.1f} Mbps"
        if self.data.delay_ms and self.data.delay_ms != 5.0:
            label_text += f" ({self.data.delay_ms:.0f}ms)"

        font_bw = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font_bw)

        # Calculate pill dimensions
        pill_w = max(64, len(label_text) * 7 + 10)
        pill_h = 16
        pill_rect = QRectF(mid_x - pill_w / 2.0, mid_y - pill_h / 2.0, pill_w, pill_h)
        self._pill_rect = pill_rect

        # Pill background
        painter.setPen(QPen(QColor("#f9e2af" if is_sel else ("#89b4fa" if self._is_hovered else "#45475a")), 1))
        painter.setBrush(QBrush(QColor("#11111b")))
        painter.drawRoundedRect(pill_rect, 4, 4)

        # Pill text
        painter.setPen(QColor("#f9e2af" if is_sel else ("#89b4fa" if self._is_hovered else "#cdd6f4")))
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, label_text)
