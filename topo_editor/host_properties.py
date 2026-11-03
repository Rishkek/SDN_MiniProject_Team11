"""
TopoEditor — Host Properties Configuration Dialog.
Allows editing Host ID, Name, IP, Role, Traffic rates, and Communication endpoints.
"""

from typing import List, Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox,
    QPushButton, QGroupBox, QMessageBox
)

from topo_editor.topology_manager import HostData, TopologyModel


class HostPropertiesDialog(QDialog):
    """
    Dedicated dialog for editing host device configuration.
    Validates host ID uniqueness, IP formatting, send/receive rates, and communication targets.
    """

    def __init__(self, host_data: HostData, model: TopologyModel, parent=None):
        super().__init__(parent)
        self.host_data = host_data
        self.model = model
        self.setWindowTitle(f"Host Properties — {host_data.id.upper()}")
        self.setMinimumWidth(440)
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
            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 5px 8px;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
                border: 1px solid #89b4fa;
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
        self.txt_id.setPlaceholderText("e.g. h1")
        form_gen.addRow("Host ID:", self.txt_id)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. H1 (Workstation)")
        form_gen.addRow("Display Name:", self.txt_name)

        self.txt_ip = QLineEdit()
        self.txt_ip.setPlaceholderText("e.g. 10.0.0.1")
        form_gen.addRow("IP Address:", self.txt_ip)

        main_layout.addWidget(grp_gen)

        # --- 2. Role Selection ---
        grp_role = QGroupBox("Role")
        form_role = QFormLayout(grp_role)
        form_role.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.cmb_role = QComboBox()
        self.cmb_role.addItem("Sender & Receiver (Both)", "both")
        self.cmb_role.addItem("Sender (Traffic Source)", "sender")
        self.cmb_role.addItem("Receiver (Traffic Sink)", "receiver")
        self.cmb_role.currentIndexChanged.connect(self._on_role_changed)
        form_role.addRow("Operational Role:", self.cmb_role)

        main_layout.addWidget(grp_role)

        # --- 3. Traffic Configuration ---
        grp_traffic = QGroupBox("Traffic Configuration")
        form_traffic = QFormLayout(grp_traffic)
        form_traffic.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.spn_send_rate = QDoubleSpinBox()
        self.spn_send_rate.setRange(0.1, 1000.0)
        self.spn_send_rate.setSingleStep(0.5)
        self.spn_send_rate.setSuffix(" Mbps")
        form_traffic.addRow("Send Rate:", self.spn_send_rate)

        self.spn_recv_rate = QDoubleSpinBox()
        self.spn_recv_rate.setRange(0.1, 1000.0)
        self.spn_recv_rate.setSingleStep(0.5)
        self.spn_recv_rate.setSuffix(" Mbps")
        form_traffic.addRow("Max Receive Rate:", self.spn_recv_rate)

        self.spn_pkt_size = QSpinBox()
        self.spn_pkt_size.setRange(64, 9000)
        self.spn_pkt_size.setSingleStep(64)
        self.spn_pkt_size.setSuffix(" bytes")
        form_traffic.addRow("Packet Size:", self.spn_pkt_size)

        main_layout.addWidget(grp_traffic)

        # --- 4. Communication Configuration ---
        grp_comm = QGroupBox("Communication Endpoints")
        form_comm = QFormLayout(grp_comm)
        form_comm.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.cmb_send_to = QComboBox()
        form_comm.addRow("Send To (Destination):", self.cmb_send_to)

        self.cmb_recv_from = QComboBox()
        form_comm.addRow("Receive From (Source):", self.cmb_recv_from)

        main_layout.addWidget(grp_comm)

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
        self.txt_id.setText(self.host_data.id)
        self.txt_name.setText(self.host_data.name)
        self.txt_ip.setText(self.host_data.ip)

        # Role
        role_map = {"both": 0, "sender": 1, "receiver": 2, "main_sender": 1, "cross_sender": 1, "main_receiver": 2, "cross_receiver": 2}
        idx = role_map.get(self.host_data.role.lower(), 0)
        self.cmb_role.setCurrentIndex(idx)

        # Traffic
        self.spn_send_rate.setValue(self.host_data.send_rate_mbps)
        self.spn_recv_rate.setValue(self.host_data.max_receive_rate_mbps)
        self.spn_pkt_size.setValue(self.host_data.packet_size_bytes)

        # Populate Send To & Receive From combos excluding self
        self._populate_host_combos()

        self._on_role_changed(self.cmb_role.currentIndex())

    def _populate_host_combos(self):
        self.cmb_send_to.clear()
        self.cmb_send_to.addItem("(None)", "")

        self.cmb_recv_from.clear()
        self.cmb_recv_from.addItem("(None)", "")

        current_id = self.host_data.id.lower()
        for hid, h in sorted(self.model.hosts.items()):
            if hid != current_id:
                label = f"{h.id.upper()} ({h.ip}) — {h.name}"
                self.cmb_send_to.addItem(label, h.id)
                self.cmb_recv_from.addItem(label, h.id)

        # Select current values
        for i in range(self.cmb_send_to.count()):
            if self.cmb_send_to.itemData(i) == self.host_data.send_to.lower():
                self.cmb_send_to.setCurrentIndex(i)
                break

        for i in range(self.cmb_recv_from.count()):
            if self.cmb_recv_from.itemData(i) == self.host_data.receive_from.lower():
                self.cmb_recv_from.setCurrentIndex(i)
                break

    def _on_role_changed(self, index):
        role_data = self.cmb_role.currentData()
        if role_data == "sender":
            self.spn_send_rate.setEnabled(True)
            self.spn_recv_rate.setEnabled(False)
            self.cmb_send_to.setEnabled(True)
            self.cmb_recv_from.setEnabled(False)
        elif role_data == "receiver":
            self.spn_send_rate.setEnabled(False)
            self.spn_recv_rate.setEnabled(True)
            self.cmb_send_to.setEnabled(False)
            self.cmb_recv_from.setEnabled(True)
        else:  # both
            self.spn_send_rate.setEnabled(True)
            self.spn_recv_rate.setEnabled(True)
            self.cmb_send_to.setEnabled(True)
            self.cmb_recv_from.setEnabled(True)

    def _validate_and_save(self):
        new_id = self.txt_id.text().strip().lower()
        if not new_id:
            QMessageBox.warning(self, "Validation Error", "Host ID cannot be empty.")
            self.txt_id.setFocus()
            return

        # Check for collision with existing devices (other than this host itself)
        if new_id != self.host_data.id.lower():
            if new_id in self.model.hosts:
                QMessageBox.warning(self, "Validation Error", f"A Host with ID '{new_id.upper()}' already exists.")
                self.txt_id.setFocus()
                return
            if new_id in self.model.switches:
                QMessageBox.warning(self, "Validation Error", f"A Switch with ID '{new_id.upper()}' already exists.")
                self.txt_id.setFocus()
                return

        new_ip = self.txt_ip.text().strip()
        if not new_ip:
            QMessageBox.warning(self, "Validation Error", "IP Address cannot be empty.")
            self.txt_ip.setFocus()
            return

        send_to = self.cmb_send_to.currentData() or ""
        recv_from = self.cmb_recv_from.currentData() or ""

        if send_to and send_to.lower() == new_id:
            QMessageBox.warning(self, "Validation Error", "A host cannot send traffic to itself.")
            return

        if recv_from and recv_from.lower() == new_id:
            QMessageBox.warning(self, "Validation Error", "A host cannot receive traffic from itself.")
            return

        # Build updated HostData
        self.updated_host = HostData(
            id=new_id,
            name=self.txt_name.text().strip() or new_id.upper(),
            ip=new_ip,
            role=self.cmb_role.currentData(),
            x=self.host_data.x,
            y=self.host_data.y,
            subtext=new_ip,
            color=self.host_data.color,
            connected_to=self.host_data.connected_to,
            send_rate_mbps=self.spn_send_rate.value(),
            max_receive_rate_mbps=self.spn_recv_rate.value(),
            packet_size_bytes=self.spn_pkt_size.value(),
            send_to=send_to,
            receive_from=recv_from,
            extra=dict(self.host_data.extra)
        )

        self.accept()
