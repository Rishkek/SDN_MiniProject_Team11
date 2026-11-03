"""
TopoEditor — Interactive Topology Canvas and Scene.
Implements the resizable, grid-based graphical workspace supporting
device dragging, link routing, wire creation mode, zoom/pan, and context actions.
"""

from typing import Optional, Dict
import math

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsLineItem,
    QGraphicsSceneMouseEvent, QMenu, QMessageBox
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QWheelEvent,
    QMouseEvent, QKeyEvent, QDragEnterEvent, QDropEvent
)

from topo_editor.topology_manager import TopologyModel, HostData, SwitchData, LinkData
from topo_editor.devices import BaseDeviceItem, HostItem, SwitchItem
from topo_editor.connections import LinkItem


class CanvasTool:
    SELECT = "select"
    WIRE = "wire"
    ADD_HOST = "add_host"
    ADD_SWITCH = "add_switch"


class TopologyScene(QGraphicsScene):
    """Custom graphics scene managing devices, links, and temporary wire previews."""

    def __init__(self, model: TopologyModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.setSceneRect(0, 0, 1200, 800)

        self.device_items: Dict[str, BaseDeviceItem] = {}
        self.link_items: Dict[str, LinkItem] = {}

        # Connect model signals
        self.model.device_added.connect(self._on_device_added)
        self.model.device_removed.connect(self._on_device_removed)
        self.model.device_updated.connect(self._on_device_updated)
        self.model.device_moved.connect(self._on_device_moved)

        self.model.link_added.connect(self._on_link_added)
        self.model.link_removed.connect(self._on_link_removed)
        self.model.link_updated.connect(self._on_link_updated)

        self.model.structure_changed.connect(self._rebuild_scene)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """Draws subtle dark engineering grid with major and minor lines."""
        painter.fillRect(rect, QColor("#181825"))

        # Minor grid (20px)
        minor_pen = QPen(QColor("#1e1e2e"), 1, Qt.PenStyle.SolidLine)
        painter.setPen(minor_pen)

        left = int(rect.left()) - (int(rect.left()) % 20)
        top = int(rect.top()) - (int(rect.top()) % 20)

        for x in range(left, int(rect.right()), 20):
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
        for y in range(top, int(rect.bottom()), 20):
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)

        # Major grid (100px)
        major_pen = QPen(QColor("#313244"), 1, Qt.PenStyle.SolidLine)
        painter.setPen(major_pen)

        left_m = int(rect.left()) - (int(rect.left()) % 100)
        top_m = int(rect.top()) - (int(rect.top()) % 100)

        for x in range(left_m, int(rect.right()), 100):
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
        for y in range(top_m, int(rect.bottom()), 100):
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)

    def _rebuild_scene(self):
        """Re-syncs all items from the model."""
        self.clear()
        self.device_items.clear()
        self.link_items.clear()

        # Add switches
        for sw in self.model.switches.values():
            self._add_switch_item(sw)

        # Add hosts
        for h in self.model.hosts.values():
            self._add_host_item(h)

        # Add links
        for lk in self.model.links.values():
            self._add_link_item(lk)

    def _add_host_item(self, host_data: HostData):
        sx = host_data.x * self.width()
        sy = host_data.y * self.height()
        item = HostItem(host_data)
        item.setPos(sx, sy)
        self.addItem(item)
        self.device_items[host_data.id.lower()] = item

    def _add_switch_item(self, switch_data: SwitchData):
        sx = switch_data.x * self.width()
        sy = switch_data.y * self.height()
        item = SwitchItem(switch_data)
        item.setPos(sx, sy)
        self.addItem(item)
        self.device_items[switch_data.id.lower()] = item

    def _add_link_item(self, link_data: LinkData):
        src_item = self.device_items.get(link_data.src.lower())
        dst_item = self.device_items.get(link_data.dst.lower())
        if src_item and dst_item:
            item = LinkItem(link_data, src_item, dst_item)
            self.addItem(item)
            self.link_items[link_data.id] = item

    def _on_device_added(self, dev_id: str):
        dev_id = dev_id.lower()
        if dev_id in self.model.hosts:
            self._add_host_item(self.model.hosts[dev_id])
        elif dev_id in self.model.switches:
            self._add_switch_item(self.model.switches[dev_id])

    def _on_device_removed(self, dev_id: str):
        dev_id = dev_id.lower()
        item = self.device_items.pop(dev_id, None)
        if item:
            self.removeItem(item)

    def _on_device_updated(self, dev_id: str):
        dev_id = dev_id.lower()
        item = self.device_items.get(dev_id)
        if item:
            if dev_id in self.model.hosts:
                item.update_data(self.model.hosts[dev_id])
            elif dev_id in self.model.switches:
                item.update_data(self.model.switches[dev_id])

    def _on_device_moved(self, dev_id: str, norm_x: float, norm_y: float):
        item = self.device_items.get(dev_id.lower())
        if item:
            target_x = norm_x * self.width()
            target_y = norm_y * self.height()
            if abs(item.pos().x() - target_x) > 1.0 or abs(item.pos().y() - target_y) > 1.0:
                item.setPos(target_x, target_y)

    def _on_link_added(self, link_id: str):
        if link_id in self.model.links:
            self._add_link_item(self.model.links[link_id])

    def _on_link_removed(self, link_id: str):
        item = self.link_items.pop(link_id, None)
        if item:
            item.cleanup()
            self.removeItem(item)

    def _on_link_updated(self, link_id: str):
        item = self.link_items.get(link_id)
        if item and link_id in self.model.links:
            item.update_data(self.model.links[link_id])

    def on_device_drag_finished(self, dev_id: str, old_pos: QPointF, new_pos: QPointF):
        """Called when a user finishes dragging a device. Commits movement to undo stack."""
        ox = max(0.02, min(0.98, old_pos.x() / self.width()))
        oy = max(0.02, min(0.98, old_pos.y() / self.height()))
        nx = max(0.02, min(0.98, new_pos.x() / self.width()))
        ny = max(0.02, min(0.98, new_pos.y() / self.height()))

        if abs(ox - nx) > 0.001 or abs(oy - ny) > 0.001:
            self.model.move_devices([(dev_id, ox, oy, nx, ny)])


class TopologyCanvas(QGraphicsView):
    """
    Main interactive workspace for TopoEditor.
    Supports tool switching (Select, Wire, Add Host, Add Switch),
    smooth zooming/panning, rubberband selection, and drag & drop.
    """
    tool_changed = pyqtSignal(str)
    status_message = pyqtSignal(str)
    selection_changed = pyqtSignal()
    edit_device_requested = pyqtSignal(str)
    edit_link_requested = pyqtSignal(str)

    def __init__(self, model: TopologyModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.topo_scene = TopologyScene(model, self)
        self.setScene(self.topo_scene)

        self.current_tool = CanvasTool.SELECT
        self._wire_source_item: Optional[BaseDeviceItem] = None
        self._temp_wire_line: Optional[QGraphicsLineItem] = None

        self._is_panning = False
        self._pan_start_pos = QPointF()

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.TextAntialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setAcceptDrops(True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        self.topo_scene.selectionChanged.connect(self._on_scene_selection_changed)

    def set_tool(self, tool_name: str):
        """Switches active canvas tool."""
        self._cancel_wire_creation()
        self.current_tool = tool_name

        if tool_name == CanvasTool.SELECT:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.status_message.emit("Tool: Select / Move Devices. Left-click to select, drag to move.")
        elif tool_name == CanvasTool.WIRE:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.status_message.emit("Wire Tool: Click source device, then click destination device.")
        elif tool_name == CanvasTool.ADD_HOST:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.status_message.emit("Add Host Tool: Click on canvas to place a new Host.")
        elif tool_name == CanvasTool.ADD_SWITCH:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.status_message.emit("Add Switch Tool: Click on canvas to place a new Switch.")

        self.tool_changed.emit(tool_name)

    def _cancel_wire_creation(self):
        """Cancels any in-progress wire drawing."""
        if self._temp_wire_line:
            self.topo_scene.removeItem(self._temp_wire_line)
            self._temp_wire_line = None
        self._wire_source_item = None

    def _on_scene_selection_changed(self):
        # Relay selection change for property sidebar
        self.selection_changed.emit()

    # -------------------------------------------------------------------------
    # Mouse & Keyboard Event Handlers
    # -------------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent):
        # Middle click or Space + Left click initiates panning
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and (event.modifiers() & Qt.KeyboardModifier.SpaceModifier)):
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        sp = self.mapToScene(event.pos())
        item = self.topo_scene.itemAt(sp, self.transform())

        # Find top-level DeviceItem or LinkItem if hit
        device_item = None
        link_item = None
        curr = item
        while curr:
            if isinstance(curr, BaseDeviceItem):
                device_item = curr
                break
            elif isinstance(curr, LinkItem):
                link_item = curr
                break
            curr = curr.parentItem()

        # 1. Wire Creation Mode
        if self.current_tool == CanvasTool.WIRE and event.button() == Qt.MouseButton.LeftButton:
            if device_item:
                if self._wire_source_item is None:
                    # Stage 1: Select source device
                    self._wire_source_item = device_item
                    p1 = device_item.get_center_scene_pos()
                    self._temp_wire_line = QGraphicsLineItem(p1.x(), p1.y(), sp.x(), sp.y())
                    self._temp_wire_line.setPen(QPen(QColor("#89b4fa"), 2, Qt.PenStyle.DashLine))
                    self._temp_wire_line.setZValue(1)
                    self.topo_scene.addItem(self._temp_wire_line)
                    self.status_message.emit(f"Source: {device_item.dev_id.upper()}. Now click destination device.")
                else:
                    # Stage 2: Select destination device and finalize
                    src_id = self._wire_source_item.dev_id
                    dst_id = device_item.dev_id
                    self._create_connection(src_id, dst_id)
                    self._cancel_wire_creation()
            else:
                # Clicked empty canvas during wire creation: cancel
                self._cancel_wire_creation()
                self.status_message.emit("Wire creation cancelled.")
            event.accept()
            return

        # 2. Add Host Mode
        if self.current_tool == CanvasTool.ADD_HOST and event.button() == Qt.MouseButton.LeftButton:
            norm_x = max(0.05, min(0.95, sp.x() / self.topo_scene.width()))
            norm_y = max(0.05, min(0.95, sp.y() / self.topo_scene.height()))
            new_id = self.model.generate_next_host_id()
            num = re.search(r"\d+", new_id).group() if re.search(r"\d+", new_id) else "1"
            host = HostData(
                id=new_id,
                name=f"Host {new_id.upper()}",
                ip=f"10.0.0.{num}",
                x=norm_x,
                y=norm_y
            )
            self.model.add_host(host)
            self.set_tool(CanvasTool.SELECT)
            event.accept()
            return

        # 3. Add Switch Mode
        if self.current_tool == CanvasTool.ADD_SWITCH and event.button() == Qt.MouseButton.LeftButton:
            norm_x = max(0.05, min(0.95, sp.x() / self.topo_scene.width()))
            norm_y = max(0.05, min(0.95, sp.y() / self.topo_scene.height()))
            new_id = self.model.generate_next_switch_id()
            num = int(re.search(r"\d+", new_id).group()) if re.search(r"\d+", new_id) else 1
            sw = SwitchData(
                id=new_id,
                dpid=num,
                name=f"Switch {new_id.upper()}",
                x=norm_x,
                y=norm_y
            )
            self.model.add_switch(sw)
            self.set_tool(CanvasTool.SELECT)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_panning:
            delta = event.pos() - self._pan_start_pos
            self._pan_start_pos = event.pos()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            event.accept()
            return

        # Update temporary wire line endpoint to follow cursor
        if self._temp_wire_line and self._wire_source_item:
            sp = self.mapToScene(event.pos())
            p1 = self._wire_source_item.get_center_scene_pos()
            self._temp_wire_line.setLine(p1.x(), p1.y(), sp.x(), sp.y())

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._is_panning and (event.button() == Qt.MouseButton.MiddleButton or event.button() == Qt.MouseButton.LeftButton):
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor if self.current_tool == CanvasTool.SELECT else Qt.CursorShape.CrossCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        """Smooth zooming anchored under mouse cursor."""
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor

        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent):
        # Escape cancels wire tool or current action
        if event.key() == Qt.Key.Key_Escape:
            if self.current_tool == CanvasTool.WIRE or self._wire_source_item:
                self._cancel_wire_creation()
                self.set_tool(CanvasTool.SELECT)
                self.status_message.emit("Wire creation cancelled.")
                event.accept()
                return

        # Delete key removes selected items
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            event.accept()
            return

        super().keyPressEvent(event)

    # -------------------------------------------------------------------------
    # Drag and Drop from Left Sidebar
    # -------------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat("application/x-topoeditor-device"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-topoeditor-device"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasFormat("application/x-topoeditor-device"):
            dev_type = event.mimeData().text().strip().lower()
            sp = self.mapToScene(event.position().toPoint())
            norm_x = max(0.05, min(0.95, sp.x() / self.topo_scene.width()))
            norm_y = max(0.05, min(0.95, sp.y() / self.topo_scene.height()))

            if dev_type == "host":
                new_id = self.model.generate_next_host_id()
                m = re.search(r"\d+", new_id)
                num = m.group() if m else "1"
                host = HostData(
                    id=new_id,
                    name=f"Host {new_id.upper()}",
                    ip=f"10.0.0.{num}",
                    x=norm_x,
                    y=norm_y
                )
                self.model.add_host(host)
                self.status_message.emit(f"Added Host {new_id.upper()} at ({norm_x:.2f}, {norm_y:.2f}).")
            elif dev_type == "switch":
                new_id = self.model.generate_next_switch_id()
                m = re.search(r"\d+", new_id)
                num = int(m.group()) if m else 1
                sw = SwitchData(
                    id=new_id,
                    dpid=num,
                    name=f"Switch {new_id.upper()}",
                    x=norm_x,
                    y=norm_y
                )
                self.model.add_switch(sw)
                self.status_message.emit(f"Added Switch {new_id.upper()} at ({norm_x:.2f}, {norm_y:.2f}).")

            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    # -------------------------------------------------------------------------
    # Connection Validation & Creation
    # -------------------------------------------------------------------------
    def _create_connection(self, src_id: str, dst_id: str):
        src_id = src_id.lower()
        dst_id = dst_id.lower()

        # 1. Prevent connecting device to itself
        if src_id == dst_id:
            QMessageBox.warning(self, "Invalid Connection", "Cannot connect a device to itself.")
            return

        # 2. Prevent duplicate connections
        existing = self.model.find_link_between(src_id, dst_id)
        if existing:
            QMessageBox.warning(
                self,
                "Duplicate Connection",
                f"A connection already exists between {src_id.upper()} and {dst_id.upper()} (Link ID: '{existing.id}')."
            )
            return

        # 3. Connection type rules
        is_src_host = src_id in self.model.hosts
        is_dst_host = dst_id in self.model.hosts

        if is_src_host and is_dst_host:
            link_type = "host_edge"
            bw = 100.0
            delay = 1.0
        elif is_src_host or is_dst_host:
            link_type = "host_edge"
            bw = 100.0
            delay = 1.0
        else:
            link_type = "switch_link"
            bw = 10.0
            delay = 5.0

        link_id = self.model.generate_next_link_id(src_id, dst_id)
        link = LinkData(
            id=link_id,
            src=src_id,
            dst=dst_id,
            bw_mbps=bw,
            delay_ms=delay,
            max_queue=1000 if link_type == "host_edge" else 100,
            type=link_type,
            pen_color="#89b4fa" if link_type == "host_edge" else "#cdd6f4",
            label=f"{src_id.upper()}->{dst_id.upper()}" if link_type == "host_edge" else f"{bw:.1f} Mbps"
        )
        self.model.add_link(link)
        self.status_message.emit(f"Created connection: {src_id.upper()} ↔ {dst_id.upper()} ({bw:.1f} Mbps).")

    # -------------------------------------------------------------------------
    # Operations: Delete, Zoom, Fit
    # -------------------------------------------------------------------------
    def delete_selected(self):
        """Deletes any currently selected devices and links with full undo support."""
        sel_items = self.topo_scene.selectedItems()
        if not sel_items:
            return

        # Process devices first (this will also delete their links)
        deleted_devices = set()
        for item in sel_items:
            if isinstance(item, BaseDeviceItem):
                self.model.delete_device(item.dev_id)
                deleted_devices.add(item.dev_id)

        # Process individual links that were selected
        for item in sel_items:
            if isinstance(item, LinkItem):
                if item.data.src not in deleted_devices and item.data.dst not in deleted_devices:
                    self.model.delete_link(item.data.id)

        self.status_message.emit("Deleted selected objects.")

    def zoom_in(self):
        self.scale(1.2, 1.2)

    def zoom_out(self):
        self.scale(1.0 / 1.2, 1.0 / 1.2)

    def reset_zoom(self):
        self.resetTransform()

    def fit_to_screen(self):
        items = self.topo_scene.items()
        if items:
            rect = self.topo_scene.itemsBoundingRect().adjusted(-50, -50, 50, 50)
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self.fitInView(self.topo_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
