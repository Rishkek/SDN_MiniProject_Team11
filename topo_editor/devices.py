"""
TopoEditor — Device Visual Items for Topology Canvas.
Provides interactive HostItem and SwitchItem with vector rendering,
movement tracking, selection highlights, and connection updates.
"""

from typing import List, Optional, Set
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtWidgets import (
    QGraphicsObject, QGraphicsItem, QGraphicsSceneMouseEvent,
    QGraphicsSceneContextMenuEvent, QMenu, QStyleOptionGraphicsItem, QWidget
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QLinearGradient
)


class BaseDeviceItem(QGraphicsObject):
    """
    Base class for interactive network devices (Hosts and Switches).
    Handles positioning, selection, attached link notifications, and move undo.
    """
    # Signals
    position_changed = pyqtSignal(str, float, float)
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    selected_changed = pyqtSignal(str, bool)

    def __init__(self, dev_id: str, x: float, y: float, parent=None):
        super().__init__(parent)
        self.dev_id = dev_id.lower()
        self.attached_links: Set[Any] = set()

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(10)  # Nodes sit above connection lines

        self._drag_start_pos: Optional[QPointF] = None
        self._is_hovered = False

    def attach_link(self, link_item):
        self.attached_links.add(link_item)

    def detach_link(self, link_item):
        self.attached_links.discard(link_item)

    def get_center_scene_pos(self) -> QPointF:
        """Returns the center point of the device in scene coordinates."""
        return self.scenePos() + self.boundingRect().center()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Notify all attached links to update their endpoints
            for link in list(self.attached_links):
                link.update_geometry()
            self.position_changed.emit(self.dev_id, self.pos().x(), self.pos().y())
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.selected_changed.emit(self.dev_id, bool(value))
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

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        super().mouseReleaseEvent(event)
        if self._drag_start_pos is not None:
            if (self.pos() - self._drag_start_pos).manhattanLength() > 2.0:
                scene = self.scene()
                if scene and hasattr(scene, "on_device_drag_finished"):
                    scene.on_device_drag_finished(self.dev_id, self._drag_start_pos, self.pos())
            self._drag_start_pos = None

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.edit_requested.emit(self.dev_id)
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
        act_edit = menu.addAction(f"✏ Edit Properties ({self.dev_id.upper()})...")
        menu.addSeparator()
        act_delete = menu.addAction(f"🗑 Delete {self.dev_id.upper()}")

        action = menu.exec(event.screenPos())
        if action == act_edit:
            self.edit_requested.emit(self.dev_id)
        elif action == act_delete:
            self.delete_requested.emit(self.dev_id)
        event.accept()


class HostItem(BaseDeviceItem):
    """
    Renders an end-host machine (Computer / Workstation).
    Displays computer monitor, screen with terminal prompt, ID badge, IP, and role.
    """

    def __init__(self, host_data, parent=None):
        super().__init__(host_data.id, host_data.x, host_data.y, parent)
        self.data = host_data

    def update_data(self, host_data):
        self.data = host_data
        self.update()

    def boundingRect(self) -> QRectF:
        # 60px wide, 50px tall monitor body + 22px text area below
        return QRectF(-32, -30, 64, 74)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_sel = self.isSelected()
        role = self.data.role.lower()

        # Accent colors based on role
        if "receiver" in role and "sender" not in role:
            accent_color = QColor("#a6e3a1")  # Green
            role_tag = "Recv"
        elif "sender" in role and "receiver" not in role:
            accent_color = QColor("#1e66f5")  # Blue
            role_tag = "Send"
        else:
            accent_color = QColor("#cba6f7")  # Mauve / Both
            role_tag = "Both"

        # 1. Selection & Hover Aura
        if is_sel:
            painter.setPen(QPen(QColor("#f9e2af"), 3, Qt.PenStyle.SolidLine))
            painter.setBrush(QColor(249, 226, 175, 40))
            painter.drawRoundedRect(-31, -29, 62, 56, 8, 8)
        elif self._is_hovered:
            painter.setPen(QPen(accent_color.lighter(130), 2, Qt.PenStyle.DotLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(-30, -28, 60, 54, 8, 8)

        # 2. Monitor Stand
        painter.setPen(QPen(QColor("#45475a"), 1))
        painter.setBrush(QBrush(QColor("#313244")))
        # Neck
        painter.drawRect(-4, 12, 8, 8)
        # Base
        painter.drawRoundedRect(-14, 18, 28, 4, 2, 2)

        # 3. Monitor Bezel (Outer Body)
        bezel_rect = QRectF(-26, -26, 52, 38)
        bezel_grad = QLinearGradient(bezel_rect.topLeft(), bezel_rect.bottomLeft())
        bezel_grad.setColorAt(0.0, QColor("#1e1e2e"))
        bezel_grad.setColorAt(1.0, QColor("#11111b"))

        border_pen = QPen(accent_color if not is_sel else QColor("#f9e2af"), 2)
        painter.setPen(border_pen)
        painter.setBrush(QBrush(bezel_grad))
        painter.drawRoundedRect(bezel_rect, 6, 6)

        # 4. Monitor Screen
        screen_rect = QRectF(-22, -22, 44, 28)
        painter.setPen(QPen(QColor("#313244"), 1))
        painter.setBrush(QBrush(QColor("#11111b")))
        painter.drawRoundedRect(screen_rect, 4, 4)

        # 5. Device ID on Screen
        painter.setPen(QColor("#cdd6f4"))
        font_id = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font_id)
        painter.drawText(screen_rect, Qt.AlignmentFlag.AlignCenter, self.data.id.upper())

        # Tiny terminal prompt `>` icon in top-left of screen
        painter.setPen(accent_color)
        font_prompt = QFont("Consolas", 7, QFont.Weight.Bold)
        painter.setFont(font_prompt)
        painter.drawText(int(screen_rect.x() + 3), int(screen_rect.y() + 8), ">")

        # 6. Subtext below device (IP & Role tag)
        sub_y = 25
        painter.setPen(QColor("#a6adc8"))
        font_ip = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
        painter.setFont(font_ip)
        ip_text = self.data.ip or "10.0.0.x"
        painter.drawText(QRectF(-45, sub_y, 90, 13), Qt.AlignmentFlag.AlignCenter, ip_text)

        # Small Role Pill
        pill_rect = QRectF(-18, sub_y + 13, 36, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 50)))
        painter.drawRoundedRect(pill_rect, 3, 3)

        painter.setPen(accent_color)
        font_role = QFont("Segoe UI", 7, QFont.Weight.Bold)
        painter.setFont(font_role)
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, role_tag)


class SwitchItem(BaseDeviceItem):
    """
    Renders an OpenFlow / SDN network switch.
    Displays enterprise rack-mount chassis with Ethernet port LEDs and dual crossing routing arrows.
    """

    def __init__(self, switch_data, parent=None):
        super().__init__(switch_data.id, switch_data.x, switch_data.y, parent)
        self.data = switch_data

    def update_data(self, switch_data):
        self.data = switch_data
        self.update()

    def boundingRect(self) -> QRectF:
        # 68px wide, 40px tall switch chassis + 24px label below
        return QRectF(-36, -24, 72, 66)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_sel = self.isSelected()
        accent = QColor("#89b4fa")  # Sapphire Blue for SDN Switch

        # 1. Selection & Hover Aura
        if is_sel:
            painter.setPen(QPen(QColor("#f9e2af"), 3, Qt.PenStyle.SolidLine))
            painter.setBrush(QColor(249, 226, 175, 40))
            painter.drawRoundedRect(-35, -22, 70, 44, 7, 7)
        elif self._is_hovered:
            painter.setPen(QPen(accent.lighter(130), 2, Qt.PenStyle.DotLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(-34, -21, 68, 42, 7, 7)

        # 2. Switch Rack Chassis Body
        body_rect = QRectF(-30, -18, 60, 36)
        body_grad = QLinearGradient(body_rect.topLeft(), body_rect.bottomLeft())
        body_grad.setColorAt(0.0, QColor("#1e1e2e"))
        body_grad.setColorAt(1.0, QColor("#11111b"))

        border_pen = QPen(accent if not is_sel else QColor("#f9e2af"), 2)
        painter.setPen(border_pen)
        painter.setBrush(QBrush(body_grad))
        painter.drawRoundedRect(body_rect, 6, 6)

        # 3. Rack Ears / Mounting Brackets on sides
        painter.setPen(QPen(QColor("#45475a"), 1))
        painter.setBrush(QBrush(QColor("#313244")))
        painter.drawRect(-34, -14, 4, 28)
        painter.drawRect(30, -14, 4, 28)
        # Screw holes
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#11111b"))
        painter.drawEllipse(-33, -11, 2, 2)
        painter.drawEllipse(-33, 9, 2, 2)
        painter.drawEllipse(31, -11, 2, 2)
        painter.drawEllipse(31, 9, 2, 2)

        # 4. Ethernet Port Activity LEDs row at bottom of switch
        led_y = 10
        for i, lx in enumerate([-20, -12, -4, 4, 12, 20]):
            painter.setBrush(QColor("#a6e3a1") if i % 2 == 0 else QColor("#89b4fa"))
            painter.drawRect(lx, led_y, 4, 3)

        # 5. Dual Crossing OpenFlow Routing Arrows (Switch Fabric Icon)
        painter.setPen(QPen(QColor("#89b4fa"), 1.2))
        # Top-left to bottom-right arrow
        painter.drawLine(-18, -10, 18, 3)
        # Bottom-left to top-right arrow
        painter.drawLine(-18, 3, 18, -10)

        # 6. Switch ID Badge in Center
        badge_rect = QRectF(-18, -14, 36, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(17, 17, 27, 210))
        painter.drawRoundedRect(badge_rect, 4, 4)

        painter.setPen(QColor("#ffffff"))
        font_id = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font_id)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self.data.id.upper())

        # 7. Subtext below device (Role / Subtext)
        sub_y = 21
        painter.setPen(QColor("#a6adc8"))
        font_sub = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
        painter.setFont(font_sub)
        role_label = self.data.subtext or self.data.role.capitalize() or "Switch"
        painter.drawText(QRectF(-45, sub_y, 90, 16), Qt.AlignmentFlag.AlignCenter, role_label)
