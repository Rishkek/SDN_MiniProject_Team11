"""
TopoEditor — Switch Properties Configuration & Connection Inspection Dialog.
Allows configuring Switch ID, DPID, Role, OpenFlow protocols, and inspecting connections.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QPushButton, QGroupBox, QMessageBox, QHeaderView
)

from topo_editor.topology_manager import SwitchData, TopologyModel


class SwitchPropertiesDialog(QDialog):
    """
    Dedicated dialog for configuring switch devices and inspecting connected links.
    """

    def __init__(self, switch_data: SwitchData, model: TopologyModel, parent=None):
        super().__init__(parent)
        self.switch_data = switch_data
        self.model = model
        self.setWindowTitle(f"Switch Properties — {switch_data.id.upper()}")
        self.setMinimumWidth(500)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QGroupBox {
                border: 1px solid #45475a;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #89b4fa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 5px 8px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #89b4fa;
            }
            QTableWidget {
                background-color: #181825;
                color: #cdd6f4;
                gridline-color: #313244;
                border: 1px solid #45475a;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #313244;
                color: #89b4fa;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #45475a;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
            QPushButton#btn_save {
                background-color: #89b4fa;
                color: #11111b;
            }
            QPushButton#btn_save:hover {
                background-color: #b4befe;
            }
        """)

        self._init_ui()
        self._populate_fields()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # --- 1. General Identification ---
        grp_gen = QGroupBox("General")
        form_gen = QFormLayout(grp_gen)
        form_gen.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.txt_id = QLineEdit()
        self.txt_id.setPlaceholderText("e.g. s1")
        form_gen.addRow("Switch ID:", self.txt_id)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. S1 (Ingress)")
        form_gen.addRow("Display Name:", self.txt_name)

        self.spn_dpid = QSpinBox()
        self.spn_dpid.setRange(1, 65535)
        form_gen.addRow("DataPath ID (DPID):", self.spn_dpid)

        main_layout.addWidget(grp_gen)

        # --- 2. Operational Role & Protocols ---
        grp_role = QGroupBox("Role & OpenFlow Protocol")
        form_role = QFormLayout(grp_role)
        form_role.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.cmb_role = QComboBox()
        self.cmb_role.addItem("Ingress Switch", "ingress")
        self.cmb_role.addItem("Primary Path Switch", "primary")
        self.cmb_role.addItem("Backup Path Switch", "backup")
        self.cmb_role.addItem("Egress Switch", "egress")
        self.cmb_role.addItem("Standard Core / Edge Switch", "normal")
        form_role.addRow("SDN Switch Role:", self.cmb_role)

        self.cmb_proto = QComboBox()
        self.cmb_proto.addItem("OpenFlow 1.3", "OpenFlow13")
        self.cmb_proto.addItem("OpenFlow 1.0", "OpenFlow10")
        form_role.addRow("OpenFlow Protocol:", self.cmb_proto)

        main_layout.addWidget(grp_role)

        # --- 3. Connection Inspection Table ---
        grp_conn = QGroupBox("Connected Links & Interfaces")
        layout_conn = QVBoxLayout(grp_conn)

        self.tbl_conns = QTableWidget()
        self.tbl_conns.setColumnCount(4)
        self.tbl_conns.setHorizontalHeaderLabels(["Connected Device", "Type", "Bandwidth", "Delay"])
        self.tbl_conns.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_conns.verticalHeader().setVisible(False)
        self.tbl_conns.setMinimumHeight(120)
        self.tbl_conns.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout_conn.addWidget(self.tbl_conns)

        main_layout.addWidget(grp_conn)

        # --- Buttons ---
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("Save Properties")
        btn_save.setObjectName("btn_save")
        btn_save.clicked.connect(self._validate_and_save)
        btn_box.addWidget(btn_save)

        main_layout.addLayout(btn_box)

    def _populate_fields(self):
        self.txt_id.setText(self.switch_data.id)
        self.txt_name.setText(self.switch_data.name)
        self.spn_dpid.setValue(self.switch_data.dpid)

        # Role
        role_map = {"ingress": 0, "primary": 1, "backup": 2, "egress": 3, "normal": 4}
        idx = role_map.get(self.switch_data.role.lower(), 4)
        self.cmb_role.setCurrentIndex(idx)

        # Protocol
        if "10" in self.switch_data.protocols:
            self.cmb_proto.setCurrentIndex(1)
        else:
            self.cmb_proto.setCurrentIndex(0)

        # Populate Connected Links
        conns = self.model.get_connected_links(self.switch_data.id)
        self.tbl_conns.setRowCount(len(conns))

        for row, lk in enumerate(conns):
            other_id = lk.dst.lower() if lk.src.lower() == self.switch_data.id.lower() else lk.src.lower()
            other_dev = self.model.get_device(other_id)

            if other_id in self.model.hosts:
                dev_type = "Host"
                dev_label = f"{other_id.upper()} ({self.model.hosts[other_id].ip})"
            else:
                dev_type = "Switch"
                dev_label = f"{other_id.upper()} ({self.model.switches.get(other_id, SwitchData(other_id)).name})"

            item_dev = QTableWidgetItem(dev_label)
            item_type = QTableWidgetItem(dev_type)
            item_bw = QTableWidgetItem(f"{lk.bw_mbps:.1f} Mbps")
            item_del = QTableWidgetItem(f"{lk.delay_ms:.1f} ms")

            for item in (item_dev, item_type, item_bw, item_del):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tbl_conns.setItem(row, 0, item_dev)
            self.tbl_conns.setItem(row, 1, item_type)
            self.tbl_conns.setItem(row, 2, item_bw)
            self.tbl_conns.setItem(row, 3, item_del)

    def _validate_and_save(self):
        new_id = self.txt_id.text().strip().lower()
        if not new_id:
            QMessageBox.warning(self, "Validation Error", "Switch ID cannot be empty.")
            self.txt_id.setFocus()
            return

        if new_id != self.switch_data.id.lower():
            if new_id in self.model.switches:
                QMessageBox.warning(self, "Validation Error", f"A Switch with ID '{new_id.upper()}' already exists.")
                self.txt_id.setFocus()
                return
            if new_id in self.model.hosts:
                QMessageBox.warning(self, "Validation Error", f"A Host with ID '{new_id.upper()}' already exists.")
                self.txt_id.setFocus()
                return

        role = self.cmb_role.currentData()
        subtext = role.capitalize() if role != "normal" else "Switch"

        self.updated_switch = SwitchData(
            id=new_id,
            dpid=self.spn_dpid.value(),
            name=self.txt_name.text().strip() or new_id.upper(),
            role=role,
            protocols=self.cmb_proto.currentData(),
            x=self.switch_data.x,
            y=self.switch_data.y,
            subtext=subtext,
            extra=dict(self.switch_data.extra)
        )

        self.accept()
