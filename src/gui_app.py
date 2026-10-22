"""
Master Graphical User Interface (PyQt6) for SDN Congestion Detection & Dynamic Rerouting.
Topic 27: SDN-Socket Programming.

Features:
- Live Interactive Network Topology with dynamic link state & load visualization
- Hardware Parameter Controls: Queue Limit (up to 100), Bottleneck Bandwidth (up to 10 Mbps), Host Rate
- Category 2 Socket Telemetry: Live Throughput, Loss %, Latency, Jitter, Packet Counters
- One-Click Cross-Traffic Congestion Injection
- Stop / Reset Topology functionality
- Transport-Layer Congestion Control in Action: TCP Tahoe, Reno, and CUBIC CWND simulation graphs
- Automated Benchmark Viewer
"""

import sys
import os
import time
import threading
from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QTabWidget, QGroupBox, QGridLayout,
    QProgressBar, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# Project imports
from src.config import (
    MAIN_UDP_PORT, CROSS_UDP_PORT, LINK_CAPACITY_MBPS,
    CONGESTION_THRESHOLD_MBPS, PATH_PRIMARY, PATH_ALTERNATE
)
from src.sdn_controller import SDNController
from src.network_emulator import NetworkEmulator
from src.udp_sender import UDPSender
from src.udp_receiver import UDPReceiver
from src.congestion_generator import CongestionGenerator
from src.protocol import FLOW_MAIN, FLOW_CROSS
from src.tcp_congestion_sim import TCPCongestionSimulator


class TopologyCanvas(QWidget):
    """Custom QPainter widget rendering the live Diamond Topology and active paths."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.active_path = PATH_PRIMARY
        self.path_a_load = 0.0
        self.path_b_load = 0.0
        self.is_congested = False

    def update_state(self, active_path: str, load_a: float, load_b: float, congested: bool):
        self.active_path = active_path
        self.path_a_load = load_a
        self.path_b_load = load_b
        self.is_congested = congested
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor("#181825"))

        w = self.width()
        h = self.height()

        # Node coordinates
        pos_h1 = (int(w * 0.10), int(h * 0.35))
        pos_h3 = (int(w * 0.10), int(h * 0.65))
        pos_s1 = (int(w * 0.28), int(h * 0.50))
        pos_s2 = (int(w * 0.50), int(h * 0.25))  # Path A
        pos_s3 = (int(w * 0.50), int(h * 0.75))  # Path B
        pos_s4 = (int(w * 0.72), int(h * 0.50))
        pos_h2 = (int(w * 0.90), int(h * 0.35))
        pos_h4 = (int(w * 0.90), int(h * 0.65))

        # Helper to draw links
        def draw_link(p1, p2, color, thickness=3, label=None):
            pen = QPen(color, thickness)
            painter.setPen(pen)
            painter.drawLine(p1[0], p1[1], p2[0], p2[1])
            if label:
                mid_x = (p1[0] + p2[0]) // 2
                mid_y = (p1[1] + p2[1]) // 2
                painter.setPen(QColor("#cdd6f4"))
                painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                painter.drawText(mid_x - 45, mid_y - 8, label)

        # Ingress / Egress Links
        draw_link(pos_h1, pos_s1, QColor("#89b4fa"), 2)
        draw_link(pos_h3, pos_s1, QColor("#f38ba8"), 2)
        draw_link(pos_s4, pos_h2, QColor("#89b4fa"), 2)
        draw_link(pos_s4, pos_h4, QColor("#f38ba8"), 2)

        # Path A Link: S1 -> S2 -> S4
        color_a = QColor("#f38ba8" if self.is_congested else ("#a6e3a1" if self.active_path == PATH_PRIMARY else "#585b70"))
        width_a = 5 if self.active_path == PATH_PRIMARY else 2
        label_a = f"Path A ({self.path_a_load:.1f}M)"
        draw_link(pos_s1, pos_s2, color_a, width_a, label_a)
        draw_link(pos_s2, pos_s4, color_a, width_a)

        # Path B Link: S1 -> S3 -> S4
        color_b = QColor("#a6e3a1" if self.active_path == PATH_ALTERNATE else "#585b70")
        width_b = 5 if self.active_path == PATH_ALTERNATE else 2
        label_b = f"Path B ({self.path_b_load:.1f}M)"
        draw_link(pos_s1, pos_s3, color_b, width_b, label_b)
        draw_link(pos_s3, pos_s4, color_b, width_b)

        # Helper to draw node
        def draw_node(pos, text, subtext, bg_color, is_switch=False):
            rad = 24 if is_switch else 20
            painter.setBrush(QBrush(bg_color))
            painter.setPen(QPen(QColor("#cdd6f4"), 2))
            if is_switch:
                painter.drawRect(pos[0] - rad, pos[1] - rad, rad * 2, rad * 2)
            else:
                painter.drawEllipse(pos[0] - rad, pos[1] - rad, rad * 2, rad * 2)

            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(pos[0] - rad, pos[1] - rad, rad * 2, rad * 2, Qt.AlignmentFlag.AlignCenter, text)

            painter.setPen(QColor("#a6adc8"))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(pos[0] - 40, pos[1] + rad + 14, subtext)

        # Draw Hosts
        draw_node(pos_h1, "H1", "Sender", QColor("#1e66f5"))
        draw_node(pos_h3, "H3", "Cross", QColor("#e64553"))
        draw_node(pos_h2, "H2", "Receiver", QColor("#40a02b"))
        draw_node(pos_h4, "H4", "Sink", QColor("#df8e1d"))

        # Draw Switches
        draw_node(pos_s1, "S1", "Ingress", QColor("#313244"), is_switch=True)
        draw_node(pos_s2, "S2", "Primary", QColor("#313244"), is_switch=True)
        draw_node(pos_s3, "S3", "Backup", QColor("#313244"), is_switch=True)
        draw_node(pos_s4, "S4", "Egress", QColor("#313244"), is_switch=True)


class RealtimePlotCanvas(FigureCanvas):
    """Matplotlib FigureCanvas for live throughput and packet loss plotting."""

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 3), dpi=90, facecolor="#1e1e2e")
        super().__init__(self.fig)
        self.ax1 = self.fig.add_subplot(2, 1, 1)
        self.ax2 = self.fig.add_subplot(2, 1, 2)
        self.fig.tight_layout()

        # Data series
        self.times = []
        self.throughputs = []
        self.losses = []

    def update_plot(self, t, thpt, loss):
        self.times.append(t)
        self.throughputs.append(thpt)
        self.losses.append(loss)

        if len(self.times) > 60:
            self.times.pop(0)
            self.throughputs.pop(0)
            self.losses.pop(0)

        self.ax1.clear()
        self.ax2.clear()

        # Styling
        for ax in [self.ax1, self.ax2]:
            ax.set_facecolor("#181825")
            ax.grid(True, linestyle="--", alpha=0.3, color="#6c7086")
            ax.tick_params(colors="#cdd6f4", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color("#45475a")

        # Throughput
        self.ax1.plot(self.times, self.throughputs, color="#a6e3a1", linewidth=2.0)
        self.ax1.set_ylabel("Mbps", color="#cdd6f4", fontsize=8)
        self.ax1.set_ylim(0, 10)
        self.ax1.set_title("Live UDP Throughput", color="#cdd6f4", fontsize=9, fontweight="bold")

        # Loss Rate
        self.ax2.plot(self.times, self.losses, color="#f38ba8", linewidth=2.0)
        self.ax2.set_ylabel("Loss %", color="#cdd6f4", fontsize=8)
        self.ax2.set_xlabel("Time (s)", color="#cdd6f4", fontsize=8)
        self.ax2.set_ylim(-2, 70)
        self.ax2.set_title("Live Packet Loss Rate (%)", color="#cdd6f4", fontsize=9, fontweight="bold")

        self.fig.tight_layout()
        self.draw()


class TCPCongestionCanvas(FigureCanvas):
    """Matplotlib FigureCanvas comparing TCP Tahoe, Reno, and CUBIC CWND saw-tooth curves."""

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(7, 4), dpi=95, facecolor="#1e1e2e")
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(1, 1, 1)
        self.ax.set_facecolor("#181825")
        self.fig.tight_layout()

    def plot_comparison(self, tahoe_data, reno_data, cubic_data, sdn_data):
        self.ax.clear()
        self.ax.set_facecolor("#181825")
        self.ax.grid(True, linestyle="--", alpha=0.3, color="#6c7086")
        self.ax.tick_params(colors="#cdd6f4")
        for spine in self.ax.spines.values():
            spine.set_color("#45475a")

        # Curves
        self.ax.plot(tahoe_data["times"], tahoe_data["cwnds"], label="TCP Tahoe (Drop to 1)", color="#f38ba8", linestyle="--", linewidth=2.0)
        self.ax.plot(reno_data["times"], reno_data["cwnds"], label="TCP Reno (Fast Recovery / Halve)", color="#89b4fa", linewidth=2.0)
        self.ax.plot(cubic_data["times"], cubic_data["cwnds"], label="TCP CUBIC (RFC 8312 Linux Default)", color="#cba6f7", linewidth=2.5)
        self.ax.plot(sdn_data["times"], sdn_data["cwnds"], label="SDN Dynamic Rerouting (Loss Averted)", color="#a6e3a1", linewidth=3.0)

        self.ax.axvspan(7.5, 9.5, color="#f9e2af", alpha=0.15, label="Bottleneck Saturation Epoch")
        self.ax.set_title("Transport Layer Congestion Mitigation in Action: CWND vs Time", color="#cdd6f4", fontsize=11, fontweight="bold")
        self.ax.set_xlabel("Transmission Time (seconds / RTTs)", color="#cdd6f4", fontsize=10)
        self.ax.set_ylabel("Congestion Window Size (cwnd in MSS)", color="#cdd6f4", fontsize=10)
        self.ax.legend(facecolor="#1e1e2e", edgecolor="#45475a", labelcolor="#cdd6f4", loc="upper left", fontsize=8)

        self.fig.tight_layout()
        self.draw()


class MasterSDNGUI(QMainWindow):
    """Master Application Window coordinating SDN controls, sockets, and live visuals."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SDN Congestion Detection & Dynamic Rerouting System (Topic #27)")
        self.resize(1280, 840)
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QWidget { color: #cdd6f4; font-family: 'Segoe UI', Arial; }
            QTabWidget::pane { border: 1px solid #313244; background: #181825; border-radius: 6px; }
            QTabBar::tab { background: #313244; padding: 10px 24px; margin-right: 4px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #89b4fa; color: #11111b; font-weight: bold; }
            QGroupBox { border: 1px solid #45475a; border-radius: 6px; margin-top: 12px; font-weight: bold; padding: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #89b4fa; }
            QPushButton { background-color: #313244; border: 1px solid #45475a; border-radius: 6px; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover { background-color: #45475a; }
            QPushButton:pressed { background-color: #585b70; }
            QSlider::groove:horizontal { height: 6px; background: #313244; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #89b4fa; border-radius: 3px; }
            QSlider::handle:horizontal { background: #b4befe; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }
        """)

        # System state
        self.controller = SDNController(congestion_threshold_mbps=CONGESTION_THRESHOLD_MBPS, adaptive_routing_enabled=True)
        self.controller.start()

        self.emulator = NetworkEmulator(controller=self.controller, ingress_port=9000)
        self.emulator.start()

        self.receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=MAIN_UDP_PORT)
        self.receiver.start()

        self.cross_receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=CROSS_UDP_PORT)
        self.cross_receiver.start()

        self.main_sender: Optional[UDPSender] = None
        self.cross_gen: Optional[CongestionGenerator] = None

        # Build UI layout
        self._init_ui()

        # Telemetry Timer (10 Hz update)
        self.timer = QTimer()
        self.timer.timeout.connect(self._refresh_telemetry)
        self.timer.start(100)

        # Elapsed time tracking
        self.start_epoch = time.time()

    def _init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)

        # Top Header Banner
        header = QFrame()
        header.setStyleSheet("background-color: #181825; border-radius: 8px; padding: 6px;")
        h_layout = QHBoxLayout(header)

        title_lbl = QLabel("SDN CONGESTION DETECTION & TRAFFIC REROUTING")
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #89b4fa;")
        h_layout.addWidget(title_lbl)

        self.lbl_active_path_status = QLabel("ACTIVE PATH: Path-A (Primary)")
        self.lbl_active_path_status.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_active_path_status.setStyleSheet("background: #a6e3a1; color: #11111b; padding: 4px 10px; border-radius: 4px;")
        h_layout.addWidget(self.lbl_active_path_status)

        self.lbl_recovery_time = QLabel("Failover Latency: -- ms")
        self.lbl_recovery_time.setFont(QFont("Segoe UI", 10))
        self.lbl_recovery_time.setStyleSheet("color: #fab387; font-weight: bold;")
        h_layout.addWidget(self.lbl_recovery_time)

        main_layout.addWidget(header)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._create_tab_topology(), "🌐 Live Topology & SDN Controls")
        tabs.addTab(self._create_tab_tcp_congestion(), "📈 Transport Layer: Tahoe vs Reno vs CUBIC")
        tabs.addTab(self._create_tab_benchmark(), "📊 Benchmark & Evaluation")
        main_layout.addWidget(tabs)

        self.setCentralWidget(main_widget)

    def _create_tab_topology(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # Left Column: Visual Canvas & Live Plots
        left_col = QVBoxLayout()
        self.topo_canvas = TopologyCanvas()
        left_col.addWidget(self.topo_canvas)

        self.plot_canvas = RealtimePlotCanvas()
        left_col.addWidget(self.plot_canvas)
        layout.addLayout(left_col, stretch=6)

        # Right Column: Interactive Controls & Digital Gauges
        right_col = QVBoxLayout()

        # Hardware & Link Controls Group
        grp_controls = QGroupBox("Network Parameters & Controls")
        grid_ctrl = QGridLayout(grp_controls)

        # Queue limit slider (up to 100)
        self.lbl_queue = QLabel("Queue Limit: 100 pkts")
        self.slider_queue = QSlider(Qt.Orientation.Horizontal)
        self.slider_queue.setRange(10, 100)
        self.slider_queue.setValue(100)
        self.slider_queue.valueChanged.connect(self._on_queue_changed)
        grid_ctrl.addWidget(self.lbl_queue, 0, 0)
        grid_ctrl.addWidget(self.slider_queue, 0, 1)

        # Bottleneck Bandwidth slider (up to 10 Mbps)
        self.lbl_bw = QLabel("Bottleneck Bandwidth: 10.0 Mbps")
        self.slider_bw = QSlider(Qt.Orientation.Horizontal)
        self.slider_bw.setRange(2, 10)
        self.slider_bw.setValue(10)
        self.slider_bw.valueChanged.connect(self._on_bw_changed)
        grid_ctrl.addWidget(self.lbl_bw, 1, 0)
        grid_ctrl.addWidget(self.slider_bw, 1, 1)

        # Host Sending Rate slider (up to 10 Mbps)
        self.lbl_host_rate = QLabel("Main Sending Rate: 6.0 Mbps")
        self.slider_host_rate = QSlider(Qt.Orientation.Horizontal)
        self.slider_host_rate.setRange(1, 10)
        self.slider_host_rate.setValue(6)
        self.slider_host_rate.valueChanged.connect(self._on_host_rate_changed)
        grid_ctrl.addWidget(self.lbl_host_rate, 2, 0)
        grid_ctrl.addWidget(self.slider_host_rate, 2, 1)

        # Cross-traffic rate slider (up to 10 Mbps)
        self.lbl_cross_rate = QLabel("Cross-Traffic Burst: 7.0 Mbps")
        self.slider_cross_rate = QSlider(Qt.Orientation.Horizontal)
        self.slider_cross_rate.setRange(1, 10)
        self.slider_cross_rate.setValue(7)
        self.slider_cross_rate.valueChanged.connect(self._on_cross_rate_changed)
        grid_ctrl.addWidget(self.lbl_cross_rate, 3, 0)
        grid_ctrl.addWidget(self.slider_cross_rate, 3, 1)

        # Action Buttons
        self.btn_toggle_sender = QPushButton("▶ Start Main UDP Stream")
        self.btn_toggle_sender.setStyleSheet("background-color: #a6e3a1; color: #11111b;")
        self.btn_toggle_sender.clicked.connect(self._toggle_main_stream)
        grid_ctrl.addWidget(self.btn_toggle_sender, 4, 0, 1, 2)

        self.btn_inject_congestion = QPushButton("⚡ Inject Congestion Now (7M Burst)")
        self.btn_inject_congestion.setStyleSheet("background-color: #f38ba8; color: #11111b;")
        self.btn_inject_congestion.clicked.connect(self._inject_congestion)
        grid_ctrl.addWidget(self.btn_inject_congestion, 5, 0, 1, 2)

        self.btn_toggle_sdn = QPushButton("Dynamic SDN Adaptive: ON")
        self.btn_toggle_sdn.setStyleSheet("background-color: #89b4fa; color: #11111b;")
        self.btn_toggle_sdn.clicked.connect(self._toggle_sdn_mode)
        grid_ctrl.addWidget(self.btn_toggle_sdn, 6, 0)

        self.btn_reset_topo = QPushButton("🔄 Reset / Stop Topology")
        self.btn_reset_topo.setStyleSheet("background-color: #eba0ac; color: #11111b;")
        self.btn_reset_topo.clicked.connect(self._reset_topology)
        grid_ctrl.addWidget(self.btn_reset_topo, 6, 1)

        right_col.addWidget(grp_controls)

        # Category 2: Live Socket Telemetry Dashboard
        grp_telemetry = QGroupBox("Real-Time Telemetry & Metric Gauges")
        grid_tel = QGridLayout(grp_telemetry)

        self.lbl_val_thpt = QLabel("0.00 Mbps")
        self.lbl_val_thpt.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.lbl_val_thpt.setStyleSheet("color: #a6e3a1;")
        grid_tel.addWidget(QLabel("Throughput:"), 0, 0)
        grid_tel.addWidget(self.lbl_val_thpt, 0, 1)

        self.lbl_val_loss = QLabel("0.0 %")
        self.lbl_val_loss.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.lbl_val_loss.setStyleSheet("color: #f38ba8;")
        grid_tel.addWidget(QLabel("Packet Loss Rate:"), 1, 0)
        grid_tel.addWidget(self.lbl_val_loss, 1, 1)

        self.lbl_val_lat = QLabel("0.0 ms")
        self.lbl_val_lat.setFont(QFont("Segoe UI", 12))
        grid_tel.addWidget(QLabel("One-Way Latency:"), 2, 0)
        grid_tel.addWidget(self.lbl_val_lat, 2, 1)

        self.lbl_val_jit = QLabel("0.0 ms")
        self.lbl_val_jit.setFont(QFont("Segoe UI", 12))
        grid_tel.addWidget(QLabel("RFC 3550 Jitter:"), 3, 0)
        grid_tel.addWidget(self.lbl_val_jit, 3, 1)

        self.lbl_val_counts = QLabel("Recv: 0 | Lost: 0")
        self.lbl_val_counts.setFont(QFont("Segoe UI", 10))
        grid_tel.addWidget(QLabel("Packet Counters:"), 4, 0)
        grid_tel.addWidget(self.lbl_val_counts, 4, 1)

        right_col.addWidget(grp_telemetry)
        layout.addLayout(right_col, stretch=4)
        return widget

    def _create_tab_tcp_congestion(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header note
        lbl_info = QLabel("Comparison of Transport-Layer Congestion Control (TCP Tahoe vs Reno vs CUBIC) vs SDN Dynamic Rerouting")
        lbl_info.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_info.setStyleSheet("color: #89b4fa; padding: 4px;")
        layout.addWidget(lbl_info)

        # Graph Canvas
        self.tcp_canvas = TCPCongestionCanvas()
        layout.addWidget(self.tcp_canvas, stretch=7)

        # Control Bar
        bar = QFrame()
        bar.setStyleSheet("background: #181825; border-radius: 6px; padding: 6px;")
        b_layout = QHBoxLayout(bar)

        self.btn_run_tcp_sim = QPushButton("▶ Run Transport-Layer Comparison Simulation")
        self.btn_run_tcp_sim.setStyleSheet("background: #cba6f7; color: #11111b; font-weight: bold;")
        self.btn_run_tcp_sim.clicked.connect(self._run_tcp_simulation)
        b_layout.addWidget(self.btn_run_tcp_sim)

        self.lbl_tcp_status = QLabel("CWND Sizes -> Tahoe: -- | Reno: -- | CUBIC: -- | SDN: Optimal")
        self.lbl_tcp_status.setStyleSheet("font-weight: bold; color: #cdd6f4;")
        b_layout.addWidget(self.lbl_tcp_status)

        layout.addWidget(bar, stretch=1)

        # Initial plot
        self._run_tcp_simulation()
        return widget

    def _create_tab_benchmark(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        top_bar = QHBoxLayout()
        btn_run_bench = QPushButton("⚡ Execute Automated Comparative Benchmark (Static vs Dynamic)")
        btn_run_bench.setStyleSheet("background: #fab387; color: #11111b; font-weight: bold; padding: 10px;")
        btn_run_bench.clicked.connect(self._run_benchmark_async)
        top_bar.addWidget(btn_run_bench)

        self.lbl_bench_status = QLabel("Status: Ready")
        top_bar.addWidget(self.lbl_bench_status)
        layout.addLayout(top_bar)

        # KPI Summary Display
        self.kpi_display = QLabel("Benchmark Results will appear here after execution...")
        self.kpi_display.setStyleSheet("background: #181825; border-radius: 6px; padding: 16px; font-family: 'Consolas', monospace;")
        layout.addWidget(self.kpi_display)
        return widget

    # Event handlers
    def _on_queue_changed(self, val):
        self.lbl_queue.setText(f"Queue Limit: {val} pkts")
        self.emulator.link_path_a.max_queue = val
        self.emulator.link_path_b.max_queue = val

    def _on_bw_changed(self, val):
        self.lbl_bw.setText(f"Bottleneck Bandwidth: {val}.0 Mbps")
        self.emulator.link_path_a.capacity_mbps = float(val)
        self.emulator.link_path_b.capacity_mbps = float(val)

    def _on_host_rate_changed(self, val):
        self.lbl_host_rate.setText(f"Main Sending Rate: {val}.0 Mbps")
        if self.main_sender:
            self.main_sender.rate_mbps = float(val)

    def _on_cross_rate_changed(self, val):
        self.lbl_cross_rate.setText(f"Cross-Traffic Burst: {val}.0 Mbps")

    def _toggle_main_stream(self):
        if self.main_sender and self.main_sender._running:
            self.main_sender.stop()
            self.btn_toggle_sender.setText("▶ Start Main UDP Stream")
            self.btn_toggle_sender.setStyleSheet("background-color: #a6e3a1; color: #11111b;")
        else:
            rate = float(self.slider_host_rate.value())
            self.main_sender = UDPSender(
                target_ip="127.0.0.1",
                target_port=9000,
                rate_mbps=rate,
                flow_id=FLOW_MAIN
            )
            self.main_sender.start()
            self.btn_toggle_sender.setText("⏹ Stop Main UDP Stream")
            self.btn_toggle_sender.setStyleSheet("background-color: #eba0ac; color: #11111b;")

    def _inject_congestion(self):
        burst_rate = float(self.slider_cross_rate.value())
        gen = CongestionGenerator(
            target_ip="127.0.0.1",
            target_port=9000,
            rate_mbps=burst_rate,
            duration=8.0
        )
        threading.Thread(target=gen.run, daemon=True).start()

    def _toggle_sdn_mode(self):
        self.controller.adaptive_routing_enabled = not self.controller.adaptive_routing_enabled
        if self.controller.adaptive_routing_enabled:
            self.btn_toggle_sdn.setText("Dynamic SDN Adaptive: ON")
            self.btn_toggle_sdn.setStyleSheet("background-color: #89b4fa; color: #11111b;")
        else:
            self.btn_toggle_sdn.setText("Dynamic SDN Adaptive: OFF (STATIC)")
            self.btn_toggle_sdn.setStyleSheet("background-color: #f38ba8; color: #11111b;")

    def _reset_topology(self):
        if self.main_sender:
            self.main_sender.stop()
            self.btn_toggle_sender.setText("▶ Start Main UDP Stream")
            self.btn_toggle_sender.setStyleSheet("background-color: #a6e3a1; color: #11111b;")
        self.controller.current_active_path = PATH_PRIMARY
        self.controller.total_reroutes = 0
        self.controller.consecutive_breaches = 0
        QMessageBox.information(self, "Topology Reset", "Network topology reset to initial state. Active Path: Path-A.")

    def _run_tcp_simulation(self):
        q_lim = self.slider_queue.value()
        bw = float(self.slider_bw.value())
        sim = TCPCongestionSimulator(bottleneck_bw_mbps=bw, queue_limit_packets=q_lim, total_time_sec=16.0)

        tahoe = sim.simulate_tahoe(loss_event_time=6.0)
        reno = sim.simulate_reno(loss_event_time=6.0)
        cubic = sim.simulate_cubic(loss_event_time=6.0)
        sdn = sim.simulate_sdn_rerouted_flow(reroute_time=6.5)

        self.tcp_canvas.plot_comparison(tahoe, reno, cubic, sdn)
        self.lbl_tcp_status.setText(
            f"CWND at Peak -> Tahoe: {tahoe['final_cwnd']} | Reno: {reno['final_cwnd']} | CUBIC: {cubic['final_cwnd']} | SDN: {sdn['final_cwnd']} (Sustained)"
        )

    def _run_benchmark_async(self):
        self.lbl_bench_status.setText("Status: Running benchmark... (takes ~45s)")
        def task():
            from src.benchmark import run_single_experiment
            s_res = run_single_experiment("STATIC", adaptive_enabled=False, total_duration=16.0, congestion_start=4.0, congestion_duration=8.0)
            d_res = run_single_experiment("DYNAMIC", adaptive_enabled=True, total_duration=16.0, congestion_start=4.0, congestion_duration=8.0)
            summary_text = (
                f"=================================================================\n"
                f"                 FINAL BENCHMARK EVALUATION RESULTS\n"
                f"=================================================================\n"
                f"Routing Mode           | Static (No Reroute)  | Dynamic SDN (Adaptive)\n"
                f"-----------------------+----------------------+-------------------------\n"
                f"Average Throughput     | {s_res['avg_throughput_mbps']} Mbps            | {d_res['avg_throughput_mbps']} Mbps (+{((d_res['avg_throughput_mbps']-s_res['avg_throughput_mbps'])/s_res['avg_throughput_mbps'])*100:.1f}%)\n"
                f"Average Packet Loss    | {s_res['avg_loss_pct']} %              | {d_res['avg_loss_pct']} % (Dramatic Drop)\n"
                f"Peak Packet Loss       | {s_res['peak_loss_pct']} %              | {d_res['peak_loss_pct']} % (Transient)\n"
                f"Congestion Recovery    | No Recovery          | {d_res['recovery_time_sec']} seconds\n"
                f"Total Packets Recv     | {s_res['total_packets_received']}                | {d_res['total_packets_received']}\n"
                f"Total Packets Lost     | {s_res['total_packets_lost']}                 | {d_res['total_packets_lost']}\n"
                f"=================================================================\n"
            )
            self.kpi_display.setText(summary_text)
            self.lbl_bench_status.setText("Status: Benchmark Completed successfully!")

        threading.Thread(target=task, daemon=True).start()

    def _refresh_telemetry(self):
        stats = self.receiver.get_latest_stats()
        ctrl_status = self.controller.get_controller_status()

        # Update gauges
        thpt = stats.get("throughput_mbps", 0.0)
        loss = stats.get("loss_pct", 0.0)
        lat = stats.get("avg_latency_ms", 0.0)
        jit = stats.get("jitter_ms", 0.0)
        recv = stats.get("total_received", 0)
        lost = stats.get("total_lost", 0)

        self.lbl_val_thpt.setText(f"{thpt:.2f} Mbps")
        self.lbl_val_loss.setText(f"{loss:.1f} %")
        self.lbl_val_lat.setText(f"{lat:.1f} ms")
        self.lbl_val_jit.setText(f"{jit:.2f} ms")
        self.lbl_val_counts.setText(f"Recv: {recv} | Lost: {lost}")

        # Update active path badge
        active_path = ctrl_status["active_path"]
        if active_path == PATH_PRIMARY:
            self.lbl_active_path_status.setText("ACTIVE PATH: Path-A (Primary)")
            self.lbl_active_path_status.setStyleSheet("background: #a6e3a1; color: #11111b; padding: 4px 10px; border-radius: 4px; font-weight: bold;")
        else:
            self.lbl_active_path_status.setText("ACTIVE PATH: Path-B (REROUTED)")
            self.lbl_active_path_status.setStyleSheet("background: #89b4fa; color: #11111b; padding: 4px 10px; border-radius: 4px; font-weight: bold;")

        if ctrl_status.get("latest_recovery_time_sec"):
            self.lbl_recovery_time.setText(f"Failover Latency: {ctrl_status['latest_recovery_time_sec'] * 1000:.2f} ms")

        # Update visual topology canvas
        load_a = ctrl_status.get("path_a_load_mbps", 0.0)
        load_b = ctrl_status.get("path_b_load_mbps", 0.0)
        is_congested = (load_a >= self.controller.congestion_threshold_mbps)
        self.topo_canvas.update_state(active_path, load_a, load_b, is_congested)

        # Update live plot
        elapsed = time.time() - self.start_epoch
        self.plot_canvas.update_plot(elapsed, thpt, loss)

    def closeEvent(self, event):
        self.timer.stop()
        if self.main_sender:
            self.main_sender.stop()
        self.receiver.stop()
        self.cross_receiver.stop()
        self.emulator.stop()
        self.controller.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MasterSDNGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
