"""
TopoEditor — Main Window and Layout System.
Coordinates the Top Menu, Left Sidebar Tool Palette, Central Canvas Workspace,
Right Contextual Properties Inspector, and File I/O workflows.
"""

import os
from typing import Optional

from PyQt6.QtCore import Qt, QMimeData, QPoint, pyqtSignal
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QToolBar, QToolButton, QLabel, QLineEdit, QTextEdit, QPushButton,
    QGroupBox, QFormLayout, QFileDialog, QMessageBox, QStatusBar,
    QScrollArea, QFrame, QDialog
)
from PyQt6.QtGui import (
    QAction, QIcon, QKeySequence, QFont, QColor, QDrag, QPixmap, QPainter
)

from topo_editor.topology_manager import TopologyModel, HostData, SwitchData, LinkData
from topo_editor.toponet_parser import ToponetParser, ToponetFormatError, TOPOLOGY_FILE_EXTENSION
from topo_editor.topology_canvas import TopologyCanvas, CanvasTool
from topo_editor.devices import BaseDeviceItem, HostItem, SwitchItem
from topo_editor.connections import LinkItem
from topo_editor.host_properties import HostPropertiesDialog
from topo_editor.switch_properties import SwitchPropertiesDialog
from topo_editor.link_properties import LinkPropertiesDialog


class DraggableToolButton(QPushButton):
    """
    Sidebar button that supports both clicking (to select tool)
    and dragging onto the canvas to place devices.
    """

    def __init__(self, text: str, dev_type: str, parent=None):
        super().__init__(text, parent)
        self.dev_type = dev_type
        self._drag_start_pos = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < 8:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-topoeditor-device", self.dev_type.encode("utf-8"))
        mime.setText(self.dev_type)
        drag.setMimeData(mime)

        # Create drag preview pixmap
        pix = QPixmap(64, 40)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#89b4fa" if self.dev_type == "switch" else "#1e66f5"))
        p.setPen(QColor("#ffffff"))
        p.drawRoundedRect(2, 2, 60, 36, 5, 5)
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, self.dev_type.capitalize())
        p.end()

        drag.setPixmap(pix)
        drag.setHotSpot(QPoint(32, 20))
        drag.exec(Qt.DropAction.CopyAction)


class MainWindow(QMainWindow):
    """
    Main Application Window for TopoEditor.
    """

    def __init__(self, initial_filepath: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.model = TopologyModel(self)
        self.setWindowTitle("TopoEditor — Network Topology Editor")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        self._init_theme()
        self._init_menu_bar()
        self._init_workspace()
        self._init_status_bar()

        # Connect model signals for title and inspector updates
        self.model.dirty_changed.connect(self._update_window_title)
        self.model.structure_changed.connect(self._update_properties_panel)
        self.canvas.selection_changed.connect(self._update_properties_panel)

        # Load initial file if provided
        if initial_filepath and os.path.exists(initial_filepath):
            self._load_file(initial_filepath)
        else:
            self._update_window_title(False)
            self._update_properties_panel()

    def _init_theme(self):
        """Applies a clean engineering dark theme."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QMenuBar {
                background-color: #181825;
                color: #cdd6f4;
                border-bottom: 1px solid #313244;
                padding: 2px;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background-color: #313244;
                color: #89b4fa;
            }
            QMenu {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 5px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #89b4fa;
                color: #11111b;
            }
            QStatusBar {
                background-color: #181825;
                color: #a6adc8;
                border-top: 1px solid #313244;
                font-size: 11px;
            }
            QSplitter::handle {
                background-color: #313244;
            }
            QSplitter::handle:hover {
                background-color: #89b4fa;
            }
            QGroupBox {
                border: 1px solid #313244;
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                color: #89b4fa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLineEdit, QTextEdit {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid #89b4fa;
            }
        """)

    # -------------------------------------------------------------------------
    # Menu Bar & Shortcuts (Section 3.A)
    # -------------------------------------------------------------------------
    def _init_menu_bar(self):
        menubar = self.menuBar()

        # --- File Menu ---
        menu_file = menubar.addMenu("&File")

        act_new = QAction("&New Topology", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.setStatusTip("Create a new empty network topology (Ctrl+N)")
        act_new.triggered.connect(self._on_action_new)
        menu_file.addAction(act_new)

        act_open = QAction("&Open...", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.setStatusTip("Open an existing .toponet topology file (Ctrl+O)")
        act_open.triggered.connect(self._on_action_open)
        menu_file.addAction(act_open)

        menu_file.addSeparator()

        self.act_save = QAction("&Save", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.setStatusTip("Save the current topology to file (Ctrl+S)")
        self.act_save.triggered.connect(self._on_action_save)
        menu_file.addAction(self.act_save)

        act_save_as = QAction("Save &As...", self)
        act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        act_save_as.setStatusTip("Save the current topology to a new .toponet file (Ctrl+Shift+S)")
        act_save_as.triggered.connect(self._on_action_save_as)
        menu_file.addAction(act_save_as)

        menu_file.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.setStatusTip("Exit TopoEditor")
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # --- Edit Menu ---
        menu_edit = menubar.addMenu("&Edit")

        self.act_undo = self.model.undo_stack.createUndoAction(self, "&Undo")
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        menu_edit.addAction(self.act_undo)

        self.act_redo = self.model.undo_stack.createRedoAction(self, "&Redo")
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        menu_edit.addAction(self.act_redo)

        menu_edit.addSeparator()

        act_del = QAction("&Delete Selected", self)
        act_del.setShortcut(QKeySequence.StandardKey.Delete)
        act_del.setStatusTip("Delete selected devices or links (Delete)")
        act_del.triggered.connect(lambda: self.canvas.delete_selected())
        menu_edit.addAction(act_del)

        act_select_all = QAction("&Select All", self)
        act_select_all.setShortcut(QKeySequence.StandardKey.SelectAll)
        act_select_all.setStatusTip("Select all devices and links on canvas (Ctrl+A)")
        act_select_all.triggered.connect(self._on_select_all)
        menu_edit.addAction(act_select_all)

        # --- View Menu ---
        menu_view = menubar.addMenu("&View")

        act_zoom_in = QAction("Zoom &In", self)
        act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        act_zoom_in.triggered.connect(lambda: self.canvas.zoom_in())
        menu_view.addAction(act_zoom_in)

        act_zoom_out = QAction("Zoom &Out", self)
        act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        act_zoom_out.triggered.connect(lambda: self.canvas.zoom_out())
        menu_view.addAction(act_zoom_out)

        act_fit = QAction("&Fit to Screen", self)
        act_fit.setShortcut("Ctrl+F")
        act_fit.triggered.connect(lambda: self.canvas.fit_to_screen())
        menu_view.addAction(act_fit)

        act_reset_zoom = QAction("&Reset Zoom", self)
        act_reset_zoom.setShortcut("Ctrl+0")
        act_reset_zoom.triggered.connect(lambda: self.canvas.reset_zoom())
        menu_view.addAction(act_reset_zoom)

        # --- Help Menu ---
        menu_help = menubar.addMenu("&Help")

        act_validate = QAction("&Validate Topology", self)
        act_validate.setStatusTip("Verify topology against simulator specifications")
        act_validate.triggered.connect(self._on_action_validate)
        menu_help.addAction(act_validate)

        act_about = QAction("&About TopoEditor", self)
        act_about.triggered.connect(self._on_action_about)
        menu_help.addAction(act_about)

    # -------------------------------------------------------------------------
    # Main Workspace Layout (Left Sidebar, Canvas, Right Sidebar)
    # -------------------------------------------------------------------------
    def _init_workspace(self):
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)

        # 1. Central Workspace — Canvas
        self.canvas = TopologyCanvas(self.model, self)
        self.canvas.status_message.connect(lambda msg: self.statusBar().showMessage(msg, 4000))
        self.canvas.edit_device_requested.connect(self._open_device_dialog)
        self.canvas.edit_link_requested.connect(self._open_link_dialog)

        # Connect scene item context menus
        self.model.device_added.connect(self._bind_device_signals)
        self.model.link_added.connect(self._bind_link_signals)

        # 2. Left Sidebar — Topology Elements Palette
        left_widget = self._create_left_sidebar()
        main_splitter.addWidget(left_widget)

        # Add Canvas to Splitter
        main_splitter.addWidget(self.canvas)

        # 3. Right Sidebar — Properties & Information Inspector
        right_widget = self._create_right_sidebar()
        main_splitter.addWidget(right_widget)

        # Set default proportions: 170px Left | 780px Canvas | 280px Right
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setStretchFactor(2, 0)
        main_splitter.setSizes([170, 780, 280])

        self.setCentralWidget(main_splitter)

    def _bind_device_signals(self, dev_id: str):
        item = self.canvas.topo_scene.device_items.get(dev_id.lower())
        if item:
            item.edit_requested.connect(self._open_device_dialog)
            item.delete_requested.connect(self.model.delete_device)

    def _bind_link_signals(self, link_id: str):
        item = self.canvas.topo_scene.link_items.get(link_id)
        if item:
            item.edit_requested.connect(self._open_link_dialog)
            item.delete_requested.connect(self.model.delete_link)

    # -------------------------------------------------------------------------
    # Left Sidebar — Topology Elements Palette (Section 3.B)
    # -------------------------------------------------------------------------
    def _create_left_sidebar(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("left_sidebar")
        widget.setStyleSheet("""
            QFrame#left_sidebar {
                background-color: #181825;
                border-right: 1px solid #313244;
            }
            QLabel {
                color: #89b4fa;
                font-weight: bold;
                font-size: 11px;
                padding-bottom: 2px;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 10px 8px;
                font-weight: bold;
                font-size: 11px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #45475a;
                color: #89b4fa;
                border: 1px solid #89b4fa;
            }
            QPushButton:checked {
                background-color: #89b4fa;
                color: #11111b;
                border: 1px solid #b4befe;
            }
        """)

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)

        lbl_tools = QLabel("TOOLS")
        layout.addWidget(lbl_tools)

        self.btn_tool_select = QPushButton("↖  Select / Move")
        self.btn_tool_select.setCheckable(True)
        self.btn_tool_select.setChecked(True)
        self.btn_tool_select.clicked.connect(lambda: self.canvas.set_tool(CanvasTool.SELECT))
        layout.addWidget(self.btn_tool_select)

        self.btn_tool_wire = QPushButton("🔗  Wire / Link")
        self.btn_tool_wire.setCheckable(True)
        self.btn_tool_wire.setToolTip("Click source node, then destination node to create connection")
        self.btn_tool_wire.clicked.connect(lambda: self.canvas.set_tool(CanvasTool.WIRE))
        layout.addWidget(self.btn_tool_wire)

        layout.addSpacing(10)
        lbl_devices = QLabel("DEVICES (DRAG OR CLICK)")
        layout.addWidget(lbl_devices)

        self.btn_add_host = DraggableToolButton("💻  Host", "host")
        self.btn_add_host.setToolTip("Drag onto canvas or click to place a Host device")
        self.btn_add_host.clicked.connect(lambda: self.canvas.set_tool(CanvasTool.ADD_HOST))
        layout.addWidget(self.btn_add_host)

        self.btn_add_switch = DraggableToolButton("🔀  Switch", "switch")
        self.btn_add_switch.setToolTip("Drag onto canvas or click to place an OpenFlow Switch")
        self.btn_add_switch.clicked.connect(lambda: self.canvas.set_tool(CanvasTool.ADD_SWITCH))
        layout.addWidget(self.btn_add_switch)

        layout.addSpacing(10)
        lbl_actions = QLabel("ACTIONS")
        layout.addWidget(lbl_actions)

        btn_delete = QPushButton("🗑  Delete Selected")
        btn_delete.setStyleSheet("QPushButton { background-color: #f38ba8; color: #11111b; text-align: center; } QPushButton:hover { background-color: #eba0ac; }")
        btn_delete.clicked.connect(lambda: self.canvas.delete_selected())
        layout.addWidget(btn_delete)

        btn_clear = QPushButton("🧹  Clear Canvas")
        btn_clear.clicked.connect(self._on_action_clear)
        layout.addWidget(btn_clear)

        layout.addStretch()

        # Canvas tool synchronization
        self.canvas.tool_changed.connect(self._on_canvas_tool_changed)

        return widget

    def _on_canvas_tool_changed(self, tool_name: str):
        self.btn_tool_select.setChecked(tool_name == CanvasTool.SELECT)
        self.btn_tool_wire.setChecked(tool_name == CanvasTool.WIRE)

    # -------------------------------------------------------------------------
    # Right Sidebar — Properties & Information (Section 3.D)
    # -------------------------------------------------------------------------
    def _create_right_sidebar(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("right_sidebar_scroll")
        scroll.setStyleSheet("""
            QScrollArea#right_sidebar_scroll {
                background-color: #181825;
                border-left: 1px solid #313244;
            }
        """)

        self.right_container = QWidget()
        self.right_layout = QVBoxLayout(self.right_container)
        self.right_layout.setContentsMargins(12, 12, 12, 12)
        self.right_layout.setSpacing(10)

        scroll.setWidget(self.right_container)
        return scroll

    def _update_properties_panel(self):
        """Refreshes contextual inspector on the right sidebar."""
        # Clear existing inspector widgets
        while self.right_layout.count():
            item = self.right_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        selected_items = self.canvas.topo_scene.selectedItems()

        # --- Mode 1: A Single Device or Link is Selected ---
        if len(selected_items) == 1:
            item = selected_items[0]
            if isinstance(item, HostItem):
                self._render_host_inspector(item.data)
                return
            elif isinstance(item, SwitchItem):
                self._render_switch_inspector(item.data)
                return
            elif isinstance(item, LinkItem):
                self._render_link_inspector(item.data)
                return

        # --- Mode 2: Multiple Items Selected ---
        if len(selected_items) > 1:
            lbl_multi = QLabel(f"<b>Multiple Objects Selected</b><br>{len(selected_items)} items selected.")
            lbl_multi.setStyleSheet("color: #89b4fa; padding: 10px;")
            self.right_layout.addWidget(lbl_multi)

            btn_del = QPushButton("Delete All Selected")
            btn_del.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; padding: 6px;")
            btn_del.clicked.connect(lambda: self.canvas.delete_selected())
            self.right_layout.addWidget(btn_del)
            self.right_layout.addStretch()
            return

        # --- Mode 3: Nothing Selected -> Display Topology Overview ---
        self._render_topology_overview()

    def _render_topology_overview(self):
        # Header
        lbl_head = QLabel("PROPERTIES & INFO")
        lbl_head.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_head.setStyleSheet("color: #89b4fa;")
        self.right_layout.addWidget(lbl_head)

        # File Overview Card
        grp_file = QGroupBox("Active File")
        form_file = QFormLayout(grp_file)
        form_file.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        fname = os.path.basename(self.model.current_filepath) if self.model.current_filepath else "Untitled Topology (Unsaved)"
        lbl_fname = QLabel(fname)
        lbl_fname.setWordWrap(True)
        lbl_fname.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        form_file.addRow("File:", lbl_fname)

        self.right_layout.addWidget(grp_file)

        # Statistics Card
        grp_stats = QGroupBox("Network Summary")
        form_stats = QFormLayout(grp_stats)
        form_stats.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        lbl_h_cnt = QLabel(str(len(self.model.hosts)))
        lbl_h_cnt.setStyleSheet("color: #cdd6f4; font-weight: bold;")
        form_stats.addRow("Total Hosts:", lbl_h_cnt)

        lbl_s_cnt = QLabel(str(len(self.model.switches)))
        lbl_s_cnt.setStyleSheet("color: #cdd6f4; font-weight: bold;")
        form_stats.addRow("Total Switches:", lbl_s_cnt)

        lbl_l_cnt = QLabel(str(len(self.model.links)))
        lbl_l_cnt.setStyleSheet("color: #cdd6f4; font-weight: bold;")
        form_stats.addRow("Total Links:", lbl_l_cnt)

        self.right_layout.addWidget(grp_stats)

        # Metadata Card
        grp_meta = QGroupBox("Topology Metadata")
        form_meta = QFormLayout(grp_meta)

        self.txt_topo_name = QLineEdit(self.model.topology_name)
        self.txt_topo_name.editingFinished.connect(self._on_topo_name_changed)
        form_meta.addRow("Name:", self.txt_topo_name)

        self.txt_topo_desc = QTextEdit()
        self.txt_topo_desc.setMaximumHeight(70)
        self.txt_topo_desc.setText(self.model.description)
        self.txt_topo_desc.textChanged.connect(self._on_topo_desc_changed)
        form_meta.addRow("Description:", self.txt_topo_desc)

        self.right_layout.addWidget(grp_meta)

        # Validation Status Card
        grp_val = QGroupBox("Validation Status")
        layout_val = QVBoxLayout(grp_val)

        errors = self.model.validate()
        if not errors:
            lbl_val = QLabel("✔ Topology is Valid\nReady for simulation.")
            lbl_val.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        else:
            lbl_val = QLabel(f"⚠ {len(errors)} Issue(s) Detected:\n• " + "\n• ".join(errors[:3]))
            lbl_val.setStyleSheet("color: #f38ba8; font-weight: bold;")
            lbl_val.setWordWrap(True)

        layout_val.addWidget(lbl_val)
        btn_val = QPushButton("Check Full Diagnostics")
        btn_val.clicked.connect(self._on_action_validate)
        layout_val.addWidget(btn_val)

        self.right_layout.addWidget(grp_val)
        self.right_layout.addStretch()

    def _render_host_inspector(self, host: HostData):
        lbl_head = QLabel(f"HOST: {host.id.upper()}")
        lbl_head.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_head.setStyleSheet("color: #1e66f5;")
        self.right_layout.addWidget(lbl_head)

        grp = QGroupBox("Host Attributes")
        form = QFormLayout(grp)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        form.addRow("Display Name:", QLabel(host.name))
        form.addRow("IP Address:", QLabel(host.ip))
        form.addRow("Role:", QLabel(host.role.capitalize()))
        form.addRow("Send Rate:", QLabel(f"{host.send_rate_mbps:.1f} Mbps"))
        form.addRow("Max Recv Rate:", QLabel(f"{host.max_receive_rate_mbps:.1f} Mbps"))
        form.addRow("Send To:", QLabel(host.send_to.upper() if host.send_to else "(None)"))
        form.addRow("Receive From:", QLabel(host.receive_from.upper() if host.receive_from else "(None)"))
        form.addRow("Position (x, y):", QLabel(f"{host.x:.3f}, {host.y:.3f}"))

        self.right_layout.addWidget(grp)

        btn_edit = QPushButton("✏ Edit Host Properties...")
        btn_edit.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; padding: 7px;")
        btn_edit.clicked.connect(lambda: self._open_device_dialog(host.id))
        self.right_layout.addWidget(btn_edit)

        btn_del = QPushButton("🗑 Delete Host")
        btn_del.setStyleSheet("background-color: #313244; color: #f38ba8; padding: 6px;")
        btn_del.clicked.connect(lambda: self.model.delete_device(host.id))
        self.right_layout.addWidget(btn_del)

        self.right_layout.addStretch()

    def _render_switch_inspector(self, sw: SwitchData):
        lbl_head = QLabel(f"SWITCH: {sw.id.upper()}")
        lbl_head.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_head.setStyleSheet("color: #89b4fa;")
        self.right_layout.addWidget(lbl_head)

        grp = QGroupBox("Switch Attributes")
        form = QFormLayout(grp)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        form.addRow("Name:", QLabel(sw.name))
        form.addRow("DPID:", QLabel(str(sw.dpid)))
        form.addRow("Role:", QLabel(sw.role.capitalize()))
        form.addRow("Protocol:", QLabel(sw.protocols))
        conns = self.model.get_connected_links(sw.id)
        form.addRow("Connected Links:", QLabel(f"{len(conns)} link(s)"))
        form.addRow("Position (x, y):", QLabel(f"{sw.x:.3f}, {sw.y:.3f}"))

        self.right_layout.addWidget(grp)

        btn_edit = QPushButton("✏ Edit Switch Properties...")
        btn_edit.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; padding: 7px;")
        btn_edit.clicked.connect(lambda: self._open_device_dialog(sw.id))
        self.right_layout.addWidget(btn_edit)

        btn_del = QPushButton("🗑 Delete Switch")
        btn_del.setStyleSheet("background-color: #313244; color: #f38ba8; padding: 6px;")
        btn_del.clicked.connect(lambda: self.model.delete_device(sw.id))
        self.right_layout.addWidget(btn_del)

        self.right_layout.addStretch()

    def _render_link_inspector(self, link: LinkData):
        lbl_head = QLabel(f"LINK: {link.src.upper()} ↔ {link.dst.upper()}")
        lbl_head.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_head.setStyleSheet("color: #a6e3a1;")
        self.right_layout.addWidget(lbl_head)

        grp = QGroupBox("Link Attributes")
        form = QFormLayout(grp)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        form.addRow("Link ID:", QLabel(link.id))
        form.addRow("Bandwidth (BW):", QLabel(f"<b>{link.bw_mbps:.1f} Mbps</b>"))
        form.addRow("Delay:", QLabel(f"{link.delay_ms:.1f} ms"))
        form.addRow("Queue Limit:", QLabel(f"{link.max_queue} pkts"))
        form.addRow("Packet Loss:", QLabel(f"{link.loss_pct:.1f} %"))
        form.addRow("Bottleneck:", QLabel("YES (Critical)" if link.is_bottleneck else "No"))
        if link.path_segment:
            form.addRow("Path Segment:", QLabel(link.path_segment))

        self.right_layout.addWidget(grp)

        btn_edit = QPushButton("✏ Edit Link Properties...")
        btn_edit.setStyleSheet("background-color: #89b4fa; color: #11111b; font-weight: bold; padding: 7px;")
        btn_edit.clicked.connect(lambda: self._open_link_dialog(link.id))
        self.right_layout.addWidget(btn_edit)

        btn_del = QPushButton("🗑 Delete Link")
        btn_del.setStyleSheet("background-color: #313244; color: #f38ba8; padding: 6px;")
        btn_del.clicked.connect(lambda: self.model.delete_link(link.id))
        self.right_layout.addWidget(btn_del)

        self.right_layout.addStretch()

    def _on_topo_name_changed(self):
        new_name = self.txt_topo_name.text().strip()
        if new_name and new_name != self.model.topology_name:
            self.model.topology_name = new_name
            self.model.undo_stack.setClean()

    def _on_topo_desc_changed(self):
        new_desc = self.txt_topo_desc.toPlainText().strip()
        if new_desc != self.model.description:
            self.model.description = new_desc

    # -------------------------------------------------------------------------
    # Dialog Openers
    # -------------------------------------------------------------------------
    def _open_device_dialog(self, dev_id: str):
        dev_id = dev_id.lower()
        if dev_id in self.model.hosts:
            host = self.model.hosts[dev_id]
            dlg = HostPropertiesDialog(host, self.model, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.model.update_host(dev_id, dlg.updated_host)
        elif dev_id in self.model.switches:
            sw = self.model.switches[dev_id]
            dlg = SwitchPropertiesDialog(sw, self.model, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.model.update_switch(dev_id, dlg.updated_switch)

    def _open_link_dialog(self, link_id: str):
        if link_id in self.model.links:
            lk = self.model.links[link_id]
            dlg = LinkPropertiesDialog(lk, self.model, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.model.update_link(link_id, dlg.updated_link)

    # -------------------------------------------------------------------------
    # Status Bar
    # -------------------------------------------------------------------------
    def _init_status_bar(self):
        status = QStatusBar(self)
        self.setStatusBar(status)
        status.showMessage("Ready. Drag devices from the left sidebar or select the Wire tool to connect.", 5000)

    def _update_window_title(self, is_dirty: bool = False):
        fname = os.path.basename(self.model.current_filepath) if self.model.current_filepath else "Untitled"
        dirty_flag = " *" if is_dirty else ""
        self.setWindowTitle(f"TopoEditor — [{fname}{dirty_flag}]")

    # -------------------------------------------------------------------------
    # File Operations & Dirty Checking (Section 3.A, 8)
    # -------------------------------------------------------------------------
    def _check_unsaved_changes(self) -> bool:
        """
        Prompts user to save unsaved changes before New/Open/Exit.
        Returns True if safe to proceed, False if user cancelled.
        """
        if not self.model.is_dirty:
            return True

        res = QMessageBox.question(
            self,
            "Unsaved Changes",
            "The current topology contains unsaved changes.\nDo you want to save before proceeding?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save
        )

        if res == QMessageBox.StandardButton.Save:
            return self._on_action_save()
        elif res == QMessageBox.StandardButton.Discard:
            return True
        else:
            return False

    def _on_action_new(self):
        if not self._check_unsaved_changes():
            return
        self.model.clear()
        self._update_window_title(False)
        self.statusBar().showMessage("Created new blank topology.", 4000)

    def _on_action_open(self):
        if not self._check_unsaved_changes():
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open Topology File",
            os.getcwd(),
            f"Topologia Network Files (*{TOPOLOGY_FILE_EXTENSION});;All Files (*)"
        )
        if not filepath:
            return

        self._load_file(filepath)

    def _load_file(self, filepath: str):
        try:
            data = ToponetParser.load(filepath)
            self.model.load_from_dict(data)
            self.canvas.fit_to_screen()
            self._update_window_title(False)
            self.statusBar().showMessage(f"Successfully loaded '{os.path.basename(filepath)}'.", 5000)
        except Exception as err:
            QMessageBox.critical(self, "Failed to Open Topology", f"Could not load '{filepath}':\n\n{err}")

    def _on_action_save(self) -> bool:
        if not self.model.current_filepath:
            return self._on_action_save_as()
        return self._save_to_path(self.model.current_filepath)

    def _on_action_save_as(self) -> bool:
        default_name = os.path.basename(self.model.current_filepath) if self.model.current_filepath else "my_topology.toponet"
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Topology As",
            os.path.join(os.getcwd(), default_name),
            f"Topologia Network Files (*{TOPOLOGY_FILE_EXTENSION});;All Files (*)"
        )
        if not filepath:
            return False

        if not filepath.lower().endswith(TOPOLOGY_FILE_EXTENSION):
            filepath += TOPOLOGY_FILE_EXTENSION

        return self._save_to_path(filepath)

    def _save_to_path(self, filepath: str) -> bool:
        # Pre-save validation
        errors = self.model.validate()
        if errors:
            res = QMessageBox.warning(
                self,
                "Topology Validation Warnings",
                f"The topology has {len(errors)} validation issue(s):\n• " +
                "\n• ".join(errors[:4]) +
                "\n\nDo you want to save anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if res != QMessageBox.StandardButton.Yes:
                return False

        try:
            data = self.model.to_dict()
            ToponetParser.save(data, filepath)
            self.model.current_filepath = os.path.abspath(filepath)
            self.model.set_clean()
            self._update_window_title(False)
            self.statusBar().showMessage(f"Saved topology to '{os.path.basename(filepath)}'.", 5000)
            return True
        except Exception as err:
            QMessageBox.critical(self, "Save Error", f"Could not save topology:\n\n{err}")
            return False

    def _on_action_clear(self):
        if QMessageBox.question(
            self, "Clear Canvas",
            "Are you sure you want to clear all devices and links on the canvas?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.model.clear()
            self.statusBar().showMessage("Cleared canvas.", 3000)

    def _on_select_all(self):
        for item in self.canvas.topo_scene.items():
            if isinstance(item, (BaseDeviceItem, LinkItem)):
                item.setSelected(True)

    def _on_action_validate(self):
        errors = self.model.validate()
        if not errors:
            QMessageBox.information(
                self,
                "Topology Diagnostics",
                "✔ Topology is fully valid!\n\n"
                f"• Switches: {len(self.model.switches)}\n"
                f"• Hosts: {len(self.model.hosts)}\n"
                f"• Links: {len(self.model.links)}\n\n"
                "All device IDs are unique, links reference existing devices, and bandwidth rates are valid."
            )
        else:
            QMessageBox.warning(
                self,
                "Topology Diagnostics — Issues Found",
                f"The following {len(errors)} issue(s) need attention:\n\n• " +
                "\n• ".join(errors)
            )

    def _on_action_about(self):
        QMessageBox.about(
            self,
            "About TopoEditor",
            "<b>TopoEditor — Network Topology Editor</b><br>"
            "Version 1.0.0<br><br>"
            "A visual engineering companion tool for SDN simulation and socket programming.<br>"
            "Construct, edit, and export custom <code>.toponet</code> topologies consumed directly by the SDN controller and network emulator.<br><br>"
            "<b>Key Shortcuts:</b><br>"
            "• <b>Ctrl+N:</b> New Topology<br>"
            "• <b>Ctrl+O:</b> Open .toponet file<br>"
            "• <b>Ctrl+S:</b> Save Topology<br>"
            "• <b>Ctrl+Z / Ctrl+Y:</b> Undo / Redo<br>"
            "• <b>Delete:</b> Delete selected device or link<br>"
            "• <b>Ctrl+F:</b> Fit topology to screen<br>"
            "• <b>Ctrl+0:</b> Reset zoom"
        )

    def closeEvent(self, event):
        if self._check_unsaved_changes():
            event.accept()
        else:
            event.ignore()
