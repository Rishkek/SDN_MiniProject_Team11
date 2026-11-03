"""
TopoEditor — Link Properties Configuration Dialog.
Allows configuring link endpoints, bandwidth capacity, delay, queue buffer, and loss.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QDoubleSpinBox, QSpinBox, QCheckBox,
    QPushButton, QGroupBox, QMessageBox
)

from topo_editor.topology_manager import LinkData, TopologyModel


class LinkPropertiesDialog(QDialog):
    """
    Dialog for configuring network connection links between devices.
    Enforces positive link bandwidth and numeric parameter validation.
    """

    def __init__(self, link_data: LinkData, model: TopologyModel, parent=None):
        super().__init__(parent)
        self.link_data = link_data
        self.model = model
        self.setWindowTitle(f"Link Properties — {link_data.src.upper()} ↔ {link_data.dst.upper()}")
        self.setMinimumWidth(400)
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
            QLineEdit, QDoubleSpinBox, QSpinBox {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 5px 8px;
            }
            QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {
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

        # --- 1. Endpoints Overview ---
        grp_endpoints = QGroupBox("Connected Endpoints")
        form_end = QFormLayout(grp_endpoints)
        form_end.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.lbl_src = QLabel(self.link_data.src.upper())
        self.lbl_src.setStyleSheet("font-weight: bold; color: #a6e3a1;")
        form_end.addRow("Source Device:", self.lbl_src)

        self.lbl_dst = QLabel(self.link_data.dst.upper())
        self.lbl_dst.setStyleSheet("font-weight: bold; color: #a6e3a1;")
        form_end.addRow("Destination Device:", self.lbl_dst)

        main_layout.addWidget(grp_endpoints)

        # --- 2. Bandwidth & Latency Parameters ---
        grp_params = QGroupBox("Transmission & Queue Constraints")
        form_params = QFormLayout(grp_params)
        form_params.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Maximum Link Rate / Bandwidth
        self.spn_bw = QDoubleSpinBox()
        self.spn_bw.setRange(0.1, 10000.0)
        self.spn_bw.setSingleStep(1.0)
        self.spn_bw.setSuffix(" Mbps")
        form_params.addRow("Maximum Bandwidth (BW):", self.spn_bw)

        # Link Delay
        self.spn_delay = QDoubleSpinBox()
        self.spn_delay.setRange(0.0, 1000.0)
        self.spn_delay.setSingleStep(1.0)
        self.spn_delay.setSuffix(" ms")
        form_params.addRow("Propagation Delay:", self.spn_delay)

        # Queue Buffer Limit
        self.spn_queue = QSpinBox()
        self.spn_queue.setRange(1, 50000)
        self.spn_queue.setSingleStep(10)
        self.spn_queue.setSuffix(" pkts")
        form_params.addRow("Queue Buffer Limit:", self.spn_queue)

        # Packet Loss
        self.spn_loss = QDoubleSpinBox()
        self.spn_loss.setRange(0.0, 100.0)
        self.spn_loss.setSingleStep(0.1)
        self.spn_loss.setSuffix(" %")
        form_params.addRow("Packet Loss Rate:", self.spn_loss)

        main_layout.addWidget(grp_params)

        # --- 3. Topology & SDN Classification ---
        grp_sdn = QGroupBox("Topology Classification")
        form_sdn = QFormLayout(grp_sdn)
        form_sdn.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.chk_bottleneck = QCheckBox("Mark as Critical Bottleneck Link")
        form_sdn.addRow("Bottleneck Link:", self.chk_bottleneck)

        self.txt_segment = QLineEdit()
        self.txt_segment.setPlaceholderText("e.g. path_a, path_b (optional)")
        form_sdn.addRow("Path Segment Tag:", self.txt_segment)

        self.txt_label = QLineEdit()
        self.txt_label.setPlaceholderText("e.g. Path A (optional)")
        form_sdn.addRow("Custom Label:", self.txt_label)

        main_layout.addWidget(grp_sdn)

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
        self.spn_bw.setValue(self.link_data.bw_mbps)
        self.spn_delay.setValue(self.link_data.delay_ms)
        self.spn_queue.setValue(self.link_data.max_queue)
        self.spn_loss.setValue(self.link_data.loss_pct)
        self.chk_bottleneck.setChecked(self.link_data.is_bottleneck)
        self.txt_segment.setText(self.link_data.path_segment)
        self.txt_label.setText(self.link_data.label)

    def _validate_and_save(self):
        bw = self.spn_bw.value()
        if bw <= 0:
            QMessageBox.warning(self, "Validation Error", "Bandwidth capacity must be greater than 0 Mbps.")
            self.spn_bw.setFocus()
            return

        label = self.txt_label.text().strip()
        if not label:
            label = f"{bw:.1f} Mbps"

        self.updated_link = LinkData(
            id=self.link_data.id,
            src=self.link_data.src,
            dst=self.link_data.dst,
            bw_mbps=bw,
            delay_ms=self.spn_delay.value(),
            max_queue=self.spn_queue.value(),
            loss_pct=self.spn_loss.value(),
            label=label,
            type=self.link_data.type,
            pen_color="#f38ba8" if self.chk_bottleneck.isChecked() else self.link_data.pen_color,
            path_segment=self.txt_segment.text().strip(),
            is_bottleneck=self.chk_bottleneck.isChecked(),
            extra=dict(self.link_data.extra)
        )

        self.accept()
