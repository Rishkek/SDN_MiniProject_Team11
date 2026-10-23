"""
Master Interactive Presentation Dashboard (PyQt6) for SDN Congestion Detection & Dynamic Rerouting.
Topic 27: SDN-Socket Programming.

Key Capabilities:
1. Animated Visual Topology with moving packet streams, queue buffer meter, and active path highlights.
2. Live OpenFlow 1.3 Flow Table Inspector on Switch S1 showing dynamic rule injection.
3. Category 2 Controls: Queue limit (10-100), Bottleneck Bandwidth (2-10M), Host Rate, Burst Rate.
4. Manual and Automatic Rerouting Controls (Force Path A, Force Path B, Auto-SDN).
5. Live Category 2 Telemetry: Throughput (Mbps), Packet Loss Rate (%), Latency, Jitter, Packet Counters.
6. Real-Time Interactive Transport Layer Congestion Simulation (TCP Tahoe, Reno, CUBIC & SDN Dynamic Rerouting)
   with live tick-by-tick animated saw-tooth graph, digital CWND readouts, and instant loss injection.
"""

import sys
import os
import time
import math
import random
import threading
from collections import deque
from typing import Optional, List, Dict, Any, Deque

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QTabWidget, QGroupBox, QGridLayout,
    QProgressBar, QFrame, QMessageBox, QComboBox, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer, QPointF
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


class PacketDot:
    """Represents an animated packet moving along a link."""
    def __init__(self, path: str, color: QColor, speed: float = 0.015):
        self.path = path  # 'main_a', 'main_b', 'cross_a'
        self.color = color
        self.progress = 0.0  # 0.0 to 1.0
        self.speed = speed


class AnimatedTopologyCanvas(QWidget):
    """
    Renders the live Diamond Topology with:
    - Moving animated packet dots on active paths (60 FPS smooth rendering)
    - Link queue buffer fill gauges (0 to 100%)
    - Active path highlighting
    - Real-time Switch S1 OpenFlow 1.3 Flow Table inspector
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(320)
        self.active_path = PATH_PRIMARY
        self.path_a_load = 0.0
        self.path_b_load = 0.0
        self.is_congested = False
        self.queue_occupancy = 0.0  # 0 to 100%
        self.queue_limit = 100
        self.flow_main_active = False
        self.flow_cross_active = False

        self.packets: List[PacketDot] = []
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._step_animation)
        self.anim_timer.start(16)  # ~60 FPS smooth rendering

        # Pre-allocated visual assets to eliminate GC churn and Qt font lookups in paintEvent
        self._font_regular_7 = QFont("Segoe UI", 7)
        self._font_bold_7 = QFont("Segoe UI", 7, QFont.Weight.Bold)
        self._font_bold_8 = QFont("Segoe UI", 8, QFont.Weight.Bold)
        self._font_bold_9 = QFont("Segoe UI", 9, QFont.Weight.Bold)
        self._pen_node = QPen(QColor("#cdd6f4"), 2)
        self._pen_q_border = QPen(QColor("#585b70"), 1)
        self._pen_wm = QPen(QColor(205, 214, 244, 75))
        self._brush_q_bg = QBrush(QColor("#313244"))
        self._brush_q_pink = QBrush(QColor("#f38ba8"))
        self._brush_q_yellow = QBrush(QColor("#f9e2af"))
        self._brush_q_green = QBrush(QColor("#a6e3a1"))
        self._color_bg = QColor("#181825")
        self._color_text_white = QColor("#ffffff")
        self._color_text_dim = QColor("#a6adc8")
        self._color_text_alert = QColor("#f38ba8")
        self._color_text_normal = QColor("#cdd6f4")
        self._color_h1 = QColor("#1e66f5")
        self._color_h3 = QColor("#e64553")
        self._color_h2 = QColor("#40a02b")
        self._color_h4 = QColor("#df8e1d")
        self._color_switch = QColor("#313244")
        self._color_path_idle = QColor("#45475a")
        self._color_path_green = QColor("#a6e3a1")
        self._color_path_red = QColor("#f38ba8")
        self._pen_link_h1 = QPen(QColor("#89b4fa"), 2)
        self._pen_link_h3 = QPen(QColor("#f38ba8"), 2)
        self._pen_link_h2 = QPen(QColor("#89b4fa"), 2)
        self._pen_link_h4 = QPen(QColor("#f38ba8"), 2)
        self._dot_color_main = QColor("#89b4fa")
        self._dot_color_cross = QColor("#f38ba8")

    def update_state(self, active_path: str, load_a: float, load_b: float, congested: bool,
                     q_occupancy: float, q_limit: int, main_active: bool, cross_active: bool):
        self.active_path = active_path
        self.path_a_load = load_a
        self.path_b_load = load_b
        self.is_congested = congested
        self.queue_occupancy = min(100.0, max(0.0, q_occupancy))
        self.queue_limit = q_limit
        self.flow_main_active = main_active
        self.flow_cross_active = cross_active

    def _step_animation(self):
        # Spawn new packets if streams are running (adjusted for ~60 FPS rate)
        if self.flow_main_active and random.random() < 0.22:
            p_type = 'main_b' if self.active_path == PATH_ALTERNATE else 'main_a'
            self.packets.append(PacketDot(p_type, self._dot_color_main, speed=0.015))

        if self.flow_cross_active and random.random() < 0.25:
            self.packets.append(PacketDot('cross_a', self._dot_color_cross, speed=0.015))

        # Advance packets
        surviving = []
        for p in self.packets:
            p.progress += p.speed
            if p.progress < 1.0:
                surviving.append(p)
        self.packets = surviving
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), self._color_bg)

        w = self.width()
        h = self.height()

        # Node coordinates
        pos_h1 = (int(w * 0.08), int(h * 0.28))
        pos_h3 = (int(w * 0.08), int(h * 0.72))
        pos_s1 = (int(w * 0.26), int(h * 0.50))
        pos_s2 = (int(w * 0.50), int(h * 0.22))  # Path A
        pos_s3 = (int(w * 0.50), int(h * 0.78))  # Path B
        pos_s4 = (int(w * 0.74), int(h * 0.50))
        pos_h2 = (int(w * 0.92), int(h * 0.28))
        pos_h4 = (int(w * 0.92), int(h * 0.72))

        # Helper to draw link
        def draw_link(p1, p2, pen_or_color, thickness=3, label=None, alert=False):
            if isinstance(pen_or_color, QPen):
                painter.setPen(pen_or_color)
            else:
                painter.setPen(QPen(pen_or_color, thickness))
            painter.drawLine(p1[0], p1[1], p2[0], p2[1])
            if label:
                mid_x = (p1[0] + p2[0]) // 2
                mid_y = (p1[1] + p2[1]) // 2
                painter.setPen(self._color_text_alert if alert else self._color_text_normal)
                painter.setFont(self._font_bold_8)
                painter.drawText(mid_x - 45, mid_y - 8, label)

        # Draw base links
        draw_link(pos_h1, pos_s1, self._pen_link_h1, 2, "H1->S1")
        draw_link(pos_h3, pos_s1, self._pen_link_h3, 2, "H3->S1")
        draw_link(pos_s4, pos_h2, self._pen_link_h2, 2, "S4->H2")
        draw_link(pos_s4, pos_h4, self._pen_link_h4, 2, "S4->H4")

        # Path A links (S1->S2->S4)
        is_path_a_active = (self.active_path == PATH_PRIMARY)
        color_a = self._color_path_red if self.is_congested else (self._color_path_green if is_path_a_active else self._color_path_idle)
        thick_a = 5 if is_path_a_active or self.flow_cross_active else 2
        label_a = f"Path A: {self.path_a_load:.1f}M " + ("[CONGESTED]" if self.is_congested else "")
        draw_link(pos_s1, pos_s2, color_a, thick_a, label_a, alert=self.is_congested)
        draw_link(pos_s2, pos_s4, color_a, thick_a)

        # Path B links (S1->S3->S4)
        is_path_b_active = (self.active_path == PATH_ALTERNATE)
        color_b = self._color_path_green if is_path_b_active else self._color_path_idle
        thick_b = 5 if is_path_b_active else 2
        label_b = f"Path B: {self.path_b_load:.1f}M " + ("[REROUTED]" if is_path_b_active else "[IDLE]")
        draw_link(pos_s1, pos_s3, color_b, thick_b, label_b)
        draw_link(pos_s3, pos_s4, color_b, thick_b)

        # Draw Queue Meter on Path A
        q_box_x = int(w * 0.38)
        q_box_y = int(h * 0.12)
        painter.setBrush(self._brush_q_bg)
        painter.setPen(self._pen_q_border)
        painter.drawRect(q_box_x, q_box_y, 110, 14)
        fill_w = int(110 * (self.queue_occupancy / 100.0))
        q_brush = self._brush_q_pink if self.queue_occupancy > 80 else (self._brush_q_yellow if self.queue_occupancy > 50 else self._brush_q_green)
        painter.fillRect(q_box_x, q_box_y, fill_w, 14, q_brush)
        painter.setPen(self._color_text_white)
        painter.setFont(self._font_bold_7)
        painter.drawText(q_box_x + 6, q_box_y + 11, f"Queue: {int(self.queue_occupancy * self.queue_limit / 100)}/{self.queue_limit} pkts")

        # Draw Animated Packets moving along links
        def get_pos_on_segment(p1, p2, prog):
            return (p1[0] + (p2[0] - p1[0]) * prog, p1[1] + (p2[1] - p1[1]) * prog)

        painter.setPen(Qt.PenStyle.NoPen)
        for p in self.packets:
            painter.setBrush(QBrush(p.color))
            if p.path == 'main_a':
                # S1 -> S2 (0.0 - 0.5), S2 -> S4 (0.5 - 1.0)
                if p.progress < 0.5:
                    pt = get_pos_on_segment(pos_s1, pos_s2, p.progress * 2.0)
                else:
                    pt = get_pos_on_segment(pos_s2, pos_s4, (p.progress - 0.5) * 2.0)
            elif p.path == 'main_b':
                # S1 -> S3 (0.0 - 0.5), S3 -> S4 (0.5 - 1.0)
                if p.progress < 0.5:
                    pt = get_pos_on_segment(pos_s1, pos_s3, p.progress * 2.0)
                else:
                    pt = get_pos_on_segment(pos_s3, pos_s4, (p.progress - 0.5) * 2.0)
            else:  # cross_a (Path A)
                if p.progress < 0.5:
                    pt = get_pos_on_segment(pos_s1, pos_s2, p.progress * 2.0)
                else:
                    pt = get_pos_on_segment(pos_s2, pos_s4, (p.progress - 0.5) * 2.0)
            painter.drawEllipse(int(pt[0]) - 4, int(pt[1]) - 4, 8, 8)

        # Helper to draw node
        def draw_node(pos, text, subtext, bg_color, is_switch=False):
            rad = 22 if is_switch else 18
            painter.setBrush(QBrush(bg_color))
            painter.setPen(self._pen_node)
            if is_switch:
                painter.drawRect(pos[0] - rad, pos[1] - rad, rad * 2, rad * 2)
            else:
                painter.drawEllipse(pos[0] - rad, pos[1] - rad, rad * 2, rad * 2)

            painter.setPen(self._color_text_white)
            painter.setFont(self._font_bold_9)
            painter.drawText(pos[0] - rad, pos[1] - rad, rad * 2, rad * 2, Qt.AlignmentFlag.AlignCenter, text)

            painter.setPen(self._color_text_dim)
            painter.setFont(self._font_regular_7)
            painter.drawText(pos[0] - 30, pos[1] + rad + 12, subtext)

        # Draw Hosts
        draw_node(pos_h1, "H1", "10.0.0.1", self._color_h1)
        draw_node(pos_h3, "H3", "10.0.0.3", self._color_h3)
        draw_node(pos_h2, "H2", "10.0.0.2", self._color_h2)
        draw_node(pos_h4, "H4", "10.0.0.4", self._color_h4)

        # Draw Switches
        draw_node(pos_s1, "S1", "Ingress", self._color_switch, is_switch=True)
        draw_node(pos_s2, "S2", "Primary", self._color_switch, is_switch=True)
        draw_node(pos_s3, "S3", "Backup", self._color_switch, is_switch=True)
        draw_node(pos_s4, "S4", "Egress", self._color_switch, is_switch=True)

        # Translucent Watermark: *D1 (Problem Understanding & Mininet/SDN Topology)
        painter.setPen(self._pen_wm)
        painter.setFont(self._font_bold_8)
        painter.drawText(w - 38, h - 8, "*D1")


class RealtimePlotCanvas(FigureCanvas):
    """Matplotlib FigureCanvas for live throughput and packet loss plotting (Optimized)."""

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 3), dpi=85, facecolor="#1e1e2e")
        super().__init__(self.fig)
        self.ax1 = self.fig.add_subplot(2, 1, 1)
        self.ax2 = self.fig.add_subplot(2, 1, 2)

        self.times: Deque[float] = deque(maxlen=70)
        self.throughputs: Deque[float] = deque(maxlen=70)
        self.losses: Deque[float] = deque(maxlen=70)

        # Pre-configure axes once to eliminate costly re-initialization on every tick
        for ax in [self.ax1, self.ax2]:
            ax.set_facecolor("#181825")
            ax.grid(True, linestyle="--", alpha=0.3, color="#6c7086")
            ax.tick_params(colors="#cdd6f4", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color("#45475a")

        self.ax1.set_ylabel("Mbps", color="#cdd6f4", fontsize=8)
        self.ax1.set_ylim(0, 10)
        self.ax1.set_title("Live UDP Throughput (Mbps)", color="#cdd6f4", fontsize=9, fontweight="bold")
        self.line_thpt, = self.ax1.plot([], [], color="#a6e3a1", linewidth=2.0)

        self.ax2.set_ylabel("Loss %", color="#cdd6f4", fontsize=8)
        self.ax2.set_xlabel("Time (s)", color="#cdd6f4", fontsize=8)
        self.ax2.set_ylim(-2, 70)
        self.ax2.set_title("Live Packet Loss Rate (%)", color="#cdd6f4", fontsize=9, fontweight="bold")
        self.line_loss, = self.ax2.plot([], [], color="#f38ba8", linewidth=2.0)

        # Translucent Watermark: *D2 (Dynamic SDN Performance Telemetry)
        self.ax2.text(0.98, 0.08, "*D2", transform=self.ax2.transAxes, color="#6c7086", alpha=0.45, fontsize=8, fontweight="bold", ha="right")

        self.fig.tight_layout()

    def update_plot(self, t: float, thpt: float, loss: float):
        self.times.append(t)
        self.throughputs.append(thpt)
        self.losses.append(loss)

        # High-performance in-place line data updates (avoids rebuilding axes/spines/labels)
        self.line_thpt.set_data(self.times, self.throughputs)
        self.line_loss.set_data(self.times, self.losses)

        if self.times:
            xmin = self.times[0]
            xmax = max(self.times[-1], xmin + 1.0)
            self.ax1.set_xlim(xmin, xmax)
            self.ax2.set_xlim(xmin, xmax)

        # Asynchronous non-blocking canvas update
        self.draw_idle()


class LiveTCPCongestionWidget(QWidget):
    """
    Live Interactive Transport Layer Congestion Simulation.
    Shows CWND dynamics for TCP Tahoe, Reno, CUBIC and SDN Dynamic Rerouting tick-by-tick!
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Educational Scope Banner
        scope_banner = QLabel("📌 [Interactive Educational Model] Demonstrates transport-layer host backoff (Tahoe drop-to-1, Reno halving, CUBIC cubic growth) versus infrastructure-level SDN dynamic traffic rerouting (loss averted before CWND collapse).")
        scope_banner.setStyleSheet("color: #fab387; font-size: 10px; font-style: italic; padding: 2px 6px; background: #181825; border-radius: 4px;")
        layout.addWidget(scope_banner)

        # Top Control Bar
        top_bar = QFrame()
        top_bar.setStyleSheet("background: #181825; border-radius: 6px; padding: 6px;")
        t_layout = QHBoxLayout(top_bar)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "All-in-One Comparison (Tahoe vs Reno vs CUBIC vs SDN)",
            "Solo Focus: TCP Tahoe (Drop to 1 on loss)",
            "Solo Focus: TCP Reno (Fast Recovery / Halve cwnd)",
            "Solo Focus: TCP CUBIC (RFC 8312 Linux Default)",
            "Solo Focus: SDN Dynamic Rerouting (Zero CWND Collapse)"
        ])
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        t_layout.addWidget(QLabel("Simulation Mode:"))
        t_layout.addWidget(self.combo_mode)

        self.btn_start = QPushButton("▶ Run Live Simulation")
        self.btn_start.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold;")
        self.btn_start.clicked.connect(self._toggle_sim)
        t_layout.addWidget(self.btn_start)

        self.btn_inject_loss = QPushButton("💥 Trigger Packet Loss Event")
        self.btn_inject_loss.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold;")
        self.btn_inject_loss.clicked.connect(self._trigger_manual_loss)
        t_layout.addWidget(self.btn_inject_loss)

        self.btn_reset = QPushButton("🔄 Reset Simulation")
        self.btn_reset.setStyleSheet("background-color: #eba0ac; color: #11111b; font-weight: bold;")
        self.btn_reset.clicked.connect(self._reset_sim)
        t_layout.addWidget(self.btn_reset)

        layout.addWidget(top_bar)

        # Digital Readouts
        readouts = QFrame()
        readouts.setStyleSheet("background: #252538; border-radius: 6px; padding: 6px;")
        r_layout = QHBoxLayout(readouts)

        self.lbl_tahoe_val = QLabel("Tahoe CWND: 1.0 MSS")
        self.lbl_tahoe_val.setStyleSheet("color: #f38ba8; font-weight: bold; font-size: 13px;")
        r_layout.addWidget(self.lbl_tahoe_val)

        self.lbl_reno_val = QLabel("Reno CWND: 1.0 MSS")
        self.lbl_reno_val.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 13px;")
        r_layout.addWidget(self.lbl_reno_val)

        self.lbl_cubic_val = QLabel("CUBIC CWND: 1.0 MSS")
        self.lbl_cubic_val.setStyleSheet("color: #cba6f7; font-weight: bold; font-size: 13px;")
        r_layout.addWidget(self.lbl_cubic_val)

        self.lbl_sdn_val = QLabel("SDN CWND: 1.0 MSS (Optimal)")
        self.lbl_sdn_val.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 13px;")
        r_layout.addWidget(self.lbl_sdn_val)

        # Translucent Watermark: *D2 (Challenging Scenario & Performance Comparison)
        lbl_wm_tcp = QLabel("*D2")
        lbl_wm_tcp.setStyleSheet("color: rgba(205, 214, 244, 0.4); font-weight: bold; font-size: 10px; padding: 2px;")
        r_layout.addWidget(lbl_wm_tcp)

        layout.addWidget(readouts)

        # Matplotlib Live Saw-Tooth Plot (Optimized for instant non-blocking render)
        self.fig = Figure(figsize=(8, 4), dpi=95, facecolor="#1e1e2e")
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(1, 1, 1)
        self.ax.set_facecolor("#181825")
        self.ax.grid(True, linestyle="--", alpha=0.3, color="#6c7086")
        self.ax.tick_params(colors="#cdd6f4")
        for spine in self.ax.spines.values():
            spine.set_color("#45475a")

        self.ax.set_title("Live Transport-Layer CWND Saw-Tooth Dynamics", color="#cdd6f4", fontsize=11, fontweight="bold")
        self.ax.set_xlabel("Transmission Time (seconds / RTTs)", color="#cdd6f4", fontsize=10)
        self.ax.set_ylabel("Congestion Window (cwnd in MSS)", color="#cdd6f4", fontsize=10)
        self.ax.set_ylim(0, 55)

        layout.addWidget(self.canvas, stretch=6)

        # Scrolling Event Log
        self.event_log = QTextEdit()
        self.event_log.setReadOnly(True)
        self.event_log.setMaximumHeight(85)
        self.event_log.setStyleSheet("background: #181825; color: #cdd6f4; font-family: 'Consolas', monospace; font-size: 10px;")
        layout.addWidget(self.event_log, stretch=2)

        # Simulation Internal State
        self.sim_timer = QTimer(self)
        self.sim_timer.timeout.connect(self._sim_tick)
        self.sim_running = False

        self.t_sim = 0.0
        self.rtt = 0.05  # 50ms RTT
        self.pipe_capacity = 36.0  # Buffer ceiling

        # Capacity line
        self.line_capacity = self.ax.axhline(self.pipe_capacity, color="#f9e2af", linestyle=":", label=f"Bottleneck Capacity ({int(self.pipe_capacity)} pkts)")

        # Pre-allocate line artists
        self.line_tahoe, = self.ax.plot([], [], label="TCP Tahoe (Drop to 1)", color="#f38ba8", linestyle="--", linewidth=2.0)
        self.line_reno, = self.ax.plot([], [], label="TCP Reno (Fast Recovery)", color="#89b4fa", linewidth=2.0)
        self.line_cubic, = self.ax.plot([], [], label="TCP CUBIC (Linux Default)", color="#cba6f7", linewidth=2.5)
        self.line_sdn, = self.ax.plot([], [], label="SDN Dynamic Rerouting", color="#a6e3a1", linewidth=3.0)

        self.legend = self.ax.legend(facecolor="#1e1e2e", edgecolor="#45475a", labelcolor="#cdd6f4", loc="upper left", fontsize=8)
        self.fig.tight_layout()

        # States for Tahoe, Reno, Cubic, SDN
        self.cwnd_tahoe = 1.0
        self.ssthresh_tahoe = 24.0

        self.cwnd_reno = 1.0
        self.ssthresh_reno = 24.0

        self.cwnd_cubic = 1.0
        self.ssthresh_cubic = 24.0
        self.w_max_cubic = 24.0
        self.t_epoch_cubic = 0.0

        self.cwnd_sdn = 1.0
        self.ssthresh_sdn = 40.0

        # Bounded deques for plot data history
        self.hist_time: Deque[float] = deque(maxlen=120)
        self.hist_tahoe: Deque[float] = deque(maxlen=120)
        self.hist_reno: Deque[float] = deque(maxlen=120)
        self.hist_cubic: Deque[float] = deque(maxlen=120)
        self.hist_sdn: Deque[float] = deque(maxlen=120)

        self._reset_sim()

    def _on_mode_changed(self, idx: int):
        self._redraw_plot()

    def _toggle_sim(self):
        if self.sim_running:
            self.sim_timer.stop()
            self.sim_running = False
            self.btn_start.setText("▶ Resume Live Simulation")
            self.btn_start.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold;")
        else:
            self.sim_timer.start(50)  # 20 ticks per second
            self.sim_running = True
            self.btn_start.setText("⏸ Pause Live Simulation")
            self.btn_start.setStyleSheet("background-color: #f9e2af; color: #11111b; font-weight: bold;")

    def _reset_sim(self):
        self.sim_timer.stop()
        self.sim_running = False
        self.btn_start.setText("▶ Run Live Simulation")
        self.btn_start.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold;")

        self.t_sim = 0.0
        self.cwnd_tahoe = 1.0
        self.ssthresh_tahoe = 24.0

        self.cwnd_reno = 1.0
        self.ssthresh_reno = 24.0

        self.cwnd_cubic = 1.0
        self.ssthresh_cubic = 24.0
        self.w_max_cubic = 24.0
        self.t_epoch_cubic = 0.0

        self.cwnd_sdn = 1.0
        self.ssthresh_sdn = 40.0

        self.hist_time.clear()
        self.hist_tahoe.clear()
        self.hist_reno.clear()
        self.hist_cubic.clear()
        self.hist_sdn.clear()

        self.hist_time.append(0.0)
        self.hist_tahoe.append(1.0)
        self.hist_reno.append(1.0)
        self.hist_cubic.append(1.0)
        self.hist_sdn.append(1.0)

        self.event_log.clear()
        self.event_log.append("[SYSTEM] Simulation initialized. Pipe capacity: 36 MSS. Press Start.")
        self._redraw_plot()

    def _trigger_manual_loss(self):
        self.event_log.append(f"[EVENT T={self.t_sim:.2f}s] 💥 MANUAL PACKET LOSS TRIGGERED AT BOTTLENECK BUFFER!")
        self._apply_loss()

    def _apply_loss(self):
        # 1. Tahoe: drops to 1 MSS
        self.ssthresh_tahoe = max(2.0, self.cwnd_tahoe / 2.0)
        self.cwnd_tahoe = 1.0
        self.event_log.append(f"  -> [TCP Tahoe] Loss Detected! ssthresh={self.ssthresh_tahoe:.1f}, CWND DROPPED TO 1.0 MSS!")

        # 2. Reno: Fast Recovery (halves)
        self.ssthresh_reno = max(2.0, self.cwnd_reno / 2.0)
        self.cwnd_reno = self.ssthresh_reno
        self.event_log.append(f"  -> [TCP Reno] 3 Dup ACKs! Fast Recovery: ssthresh={self.ssthresh_reno:.1f}, CWND HALVED to {self.cwnd_reno:.1f} MSS.")

        # 3. CUBIC: 30% reduction, begins cubic curve
        self.w_max_cubic = self.cwnd_cubic
        self.ssthresh_cubic = max(2.0, self.cwnd_cubic * 0.7)
        self.cwnd_cubic = self.ssthresh_cubic
        self.t_epoch_cubic = self.t_sim
        self.event_log.append(f"  -> [TCP CUBIC] Congestion Event! W_max={self.w_max_cubic:.1f}, CWND set to {self.cwnd_cubic:.1f} MSS (retains 70%).")

        # 4. SDN: Avoids drop!
        self.event_log.append(f"  -> [SDN Reroute] SDN Controller dynamically steered flow to Path B before buffer drop! Zero loss sustained.")

    def _sim_tick(self):
        self.t_sim += self.rtt

        # Check if natural pipe capacity exceeded
        if self.cwnd_reno >= self.pipe_capacity or self.cwnd_tahoe >= self.pipe_capacity:
            self.event_log.append(f"[BUFFER OVERFLOW T={self.t_sim:.2f}s] Bottleneck link queue full (36 pkts)! Dropping packets.")
            self._apply_loss()
        else:
            # Advance Tahoe
            if self.cwnd_tahoe < self.ssthresh_tahoe:
                self.cwnd_tahoe += 1.0
            else:
                self.cwnd_tahoe += (1.0 / self.cwnd_tahoe)

            # Advance Reno
            if self.cwnd_reno < self.ssthresh_reno:
                self.cwnd_reno += 1.0
            else:
                self.cwnd_reno += (1.0 / self.cwnd_reno)

            # Advance CUBIC
            if self.cwnd_cubic < self.ssthresh_cubic:
                self.cwnd_cubic += 1.0
            else:
                # W_cubic(t) = C*(t - K)^3 + W_max
                C = 0.4
                beta = 0.3
                k_time = math.pow((self.w_max_cubic * beta) / C, 1.0 / 3.0)
                t_since = self.t_sim - self.t_epoch_cubic
                w_target = C * math.pow(t_since - k_time, 3.0) + self.w_max_cubic
                incr = max(0.05, (w_target - self.cwnd_cubic) / max(1.0, self.cwnd_cubic))
                self.cwnd_cubic += min(2.0, incr)

            # Advance SDN (Sustains growth, moves to alternate clean path)
            if self.cwnd_sdn < self.ssthresh_sdn:
                self.cwnd_sdn += 1.0
            else:
                self.cwnd_sdn += (1.0 / self.cwnd_sdn)
            self.cwnd_sdn = min(50.0, self.cwnd_sdn)

        # Record history in bounded circular buffers
        self.hist_time.append(round(self.t_sim, 2))
        self.hist_tahoe.append(round(self.cwnd_tahoe, 2))
        self.hist_reno.append(round(self.cwnd_reno, 2))
        self.hist_cubic.append(round(self.cwnd_cubic, 2))
        self.hist_sdn.append(round(self.cwnd_sdn, 2))

        # Update labels
        self.lbl_tahoe_val.setText(f"Tahoe CWND: {self.cwnd_tahoe:.1f} MSS")
        self.lbl_reno_val.setText(f"Reno CWND: {self.cwnd_reno:.1f} MSS")
        self.lbl_cubic_val.setText(f"CUBIC CWND: {self.cwnd_cubic:.1f} MSS")
        self.lbl_sdn_val.setText(f"SDN CWND: {self.cwnd_sdn:.1f} MSS (Optimal)")

        self._redraw_plot()

    def _redraw_plot(self):
        mode = self.combo_mode.currentIndex()
        self.line_tahoe.set_visible(mode in (0, 1))
        self.line_reno.set_visible(mode in (0, 2))
        self.line_cubic.set_visible(mode in (0, 3))
        self.line_sdn.set_visible(mode in (0, 4))

        if self.hist_time:
            self.line_tahoe.set_data(self.hist_time, self.hist_tahoe)
            self.line_reno.set_data(self.hist_time, self.hist_reno)
            self.line_cubic.set_data(self.hist_time, self.hist_cubic)
            self.line_sdn.set_data(self.hist_time, self.hist_sdn)
            self.ax.set_xlim(self.hist_time[0], max(self.hist_time[-1], self.hist_time[0] + 1.0))

        self.canvas.draw_idle()


class MasterSDNGUI(QMainWindow):
    """
    Master Application Window coordinating Animated Topology,
    OpenFlow Flow Table Inspector, Category 2 controls, and live TCP simulation.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SDN Congestion Detection & Dynamic Rerouting System (Topic #27)")
        self.resize(1300, 880)
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; }
            QWidget { color: #cdd6f4; font-family: 'Segoe UI', Arial; }
            QTabWidget::pane { border: 1px solid #313244; background: #181825; border-radius: 6px; }
            QTabBar::tab { background: #313244; padding: 10px 24px; margin-right: 4px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #89b4fa; color: #11111b; font-weight: bold; }
            QGroupBox { border: 1px solid #45475a; border-radius: 6px; margin-top: 10px; font-weight: bold; padding: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #89b4fa; }
            QPushButton { background-color: #313244; border: 1px solid #45475a; border-radius: 6px; padding: 7px 14px; font-weight: bold; }
            QPushButton:hover { background-color: #45475a; }
            QSlider::groove:horizontal { height: 6px; background: #313244; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #89b4fa; border-radius: 3px; }
            QSlider::handle:horizontal { background: #b4befe; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }
        """)

        # Start background core modules
        self.controller = SDNController(congestion_threshold_mbps=CONGESTION_THRESHOLD_MBPS, adaptive_routing_enabled=True)
        self.controller.start()

        self.emulator = NetworkEmulator(controller=self.controller, ingress_port=9000)
        self.emulator.start()

        self.receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=MAIN_UDP_PORT, feedback_target=("127.0.0.1", 9005))
        self.receiver.start()

        self.cross_receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=CROSS_UDP_PORT)
        self.cross_receiver.start()

        self.main_sender: Optional[UDPSender] = None
        self.is_cross_burst_active = False

        # Dirty-check cache to prevent redundant UI relayouts
        self._last_flow_text = ""
        self._last_active_path_status = ""
        self._last_recovery_time_sec = None

        # Build UI
        self._init_ui()

        # Telemetry Timer (4 Hz / 250ms interval - optimal responsiveness without CPU churn)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_telemetry)
        self.timer.start(250)

        self.start_epoch = time.time()

    def _init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)

        # Top Alert & State Header
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
        tabs.addTab(self._create_tab_topology(), "🌐 Live Visual Topology & SDN Controls")
        tabs.addTab(LiveTCPCongestionWidget(), "📈 Live TCP Congestion: Tahoe vs Reno vs CUBIC")
        tabs.addTab(self._create_tab_benchmark(), "📊 Benchmark & Evaluation")
        main_layout.addWidget(tabs)

        self.setCentralWidget(main_widget)

    def _create_tab_topology(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # Left Column: Animated Topology Canvas + Live Flow Table + Live Plots
        left_col = QVBoxLayout()
        self.topo_canvas = AnimatedTopologyCanvas()
        left_col.addWidget(self.topo_canvas, stretch=5)

        # OpenFlow 1.3 Flow Table Inspector Box
        grp_flow_table = QGroupBox("Switch S1 Live OpenFlow 1.3 Flow Table")
        ft_layout = QVBoxLayout(grp_flow_table)
        self.lbl_flow_table = QLabel()
        self.lbl_flow_table.setFont(QFont("Consolas", 9))
        self.lbl_flow_table.setStyleSheet("background: #11111b; color: #a6e3a1; padding: 8px; border-radius: 4px;")
        ft_layout.addWidget(self.lbl_flow_table)

        # Translucent Watermark: *D2 (Dynamic SDN Functionality)
        lbl_wm_ft = QLabel("*D2")
        lbl_wm_ft.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_wm_ft.setStyleSheet("color: rgba(205, 214, 244, 0.4); font-size: 8px; font-weight: bold; margin-top: -6px;")
        ft_layout.addWidget(lbl_wm_ft)

        left_col.addWidget(grp_flow_table, stretch=2)

        self.plot_canvas = RealtimePlotCanvas()
        left_col.addWidget(self.plot_canvas, stretch=4)
        layout.addLayout(left_col, stretch=6)

        # Right Column: Controls & Digital Gauges
        right_col = QVBoxLayout()

        # Hardware & Link Controls
        grp_ctrl = QGroupBox("Network Parameters & Controls")
        grid_ctrl = QGridLayout(grp_ctrl)

        # Queue limit slider (10 to 100)
        self.lbl_queue = QLabel("Queue Limit: 100 pkts")
        self.slider_queue = QSlider(Qt.Orientation.Horizontal)
        self.slider_queue.setRange(10, 100)
        self.slider_queue.setValue(100)
        self.slider_queue.valueChanged.connect(self._on_queue_changed)
        grid_ctrl.addWidget(self.lbl_queue, 0, 0)
        grid_ctrl.addWidget(self.slider_queue, 0, 1)

        # Bottleneck Bandwidth slider (2 to 10)
        self.lbl_bw = QLabel("Bottleneck Bandwidth: 10.0 Mbps")
        self.slider_bw = QSlider(Qt.Orientation.Horizontal)
        self.slider_bw.setRange(2, 10)
        self.slider_bw.setValue(10)
        self.slider_bw.valueChanged.connect(self._on_bw_changed)
        grid_ctrl.addWidget(self.lbl_bw, 1, 0)
        grid_ctrl.addWidget(self.slider_bw, 1, 1)

        # Host Sending Rate slider (1 to 10)
        self.lbl_host_rate = QLabel("Main Sending Rate: 6.0 Mbps")
        self.slider_host_rate = QSlider(Qt.Orientation.Horizontal)
        self.slider_host_rate.setRange(1, 10)
        self.slider_host_rate.setValue(6)
        self.slider_host_rate.valueChanged.connect(self._on_host_rate_changed)
        grid_ctrl.addWidget(self.lbl_host_rate, 2, 0)
        grid_ctrl.addWidget(self.slider_host_rate, 2, 1)

        # Cross-traffic burst rate slider (1 to 10)
        self.lbl_cross_rate = QLabel("Cross-Traffic Burst: 7.0 Mbps")
        self.slider_cross_rate = QSlider(Qt.Orientation.Horizontal)
        self.slider_cross_rate.setRange(1, 10)
        self.slider_cross_rate.setValue(7)
        self.slider_cross_rate.valueChanged.connect(self._on_cross_rate_changed)
        grid_ctrl.addWidget(self.lbl_cross_rate, 3, 0)
        grid_ctrl.addWidget(self.slider_cross_rate, 3, 1)

        # Stream Control Buttons
        self.btn_toggle_sender = QPushButton("▶ Start Main UDP Stream")
        self.btn_toggle_sender.setStyleSheet("background-color: #a6e3a1; color: #11111b;")
        self.btn_toggle_sender.clicked.connect(self._toggle_main_stream)
        grid_ctrl.addWidget(self.btn_toggle_sender, 4, 0, 1, 2)

        self.btn_inject_congestion = QPushButton("⚡ Inject Congestion (7M Burst on Path A)")
        self.btn_inject_congestion.setStyleSheet("background-color: #f38ba8; color: #11111b;")
        self.btn_inject_congestion.clicked.connect(self._inject_congestion)
        grid_ctrl.addWidget(self.btn_inject_congestion, 5, 0, 1, 2)

        # Manual / Auto Rerouting Override Controls
        btn_force_b = QPushButton("🔀 Force Reroute to Path B")
        btn_force_b.clicked.connect(lambda: self._manual_reroute(PATH_ALTERNATE))
        grid_ctrl.addWidget(btn_force_b, 6, 0)

        btn_force_a = QPushButton("⏮ Revert to Path A")
        btn_force_a.clicked.connect(lambda: self._manual_reroute(PATH_PRIMARY))
        grid_ctrl.addWidget(btn_force_a, 6, 1)

        self.btn_toggle_sdn = QPushButton("Auto-SDN Dynamic Rerouting: ON")
        self.btn_toggle_sdn.setStyleSheet("background-color: #89b4fa; color: #11111b;")
        self.btn_toggle_sdn.clicked.connect(self._toggle_sdn_mode)
        grid_ctrl.addWidget(self.btn_toggle_sdn, 7, 0)

        self.btn_reset_topo = QPushButton("🔄 Reset / Stop Topology")
        self.btn_reset_topo.setStyleSheet("background-color: #eba0ac; color: #11111b;")
        self.btn_reset_topo.clicked.connect(self._reset_topology)
        grid_ctrl.addWidget(self.btn_reset_topo, 7, 1)

        self.rate_adaptation_enabled = False
        self.btn_toggle_rate_adapt = QPushButton("UDP Rate Adaptation: OFF")
        self.btn_toggle_rate_adapt.setStyleSheet("background-color: #313244; color: #cdd6f4;")
        self.btn_toggle_rate_adapt.clicked.connect(self._toggle_rate_adapt)
        grid_ctrl.addWidget(self.btn_toggle_rate_adapt, 8, 0, 1, 2)

        # Translucent Watermark: *D1 (Mininet + SDN Integration)
        lbl_wm_ctrl = QLabel("*D1")
        lbl_wm_ctrl.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_wm_ctrl.setStyleSheet("color: rgba(205, 214, 244, 0.4); font-size: 8px; font-weight: bold;")
        grid_ctrl.addWidget(lbl_wm_ctrl, 9, 1)

        right_col.addWidget(grp_ctrl)

        # Category 2 Telemetry Digital Readouts
        grp_tel = QGroupBox("Category 2: Real-Time Socket Telemetry")
        grid_tel = QGridLayout(grp_tel)

        self.lbl_val_thpt = QLabel("0.00 Mbps")
        self.lbl_val_thpt.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.lbl_val_thpt.setStyleSheet("color: #a6e3a1;")
        grid_tel.addWidget(QLabel("Live Throughput:"), 0, 0)
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

        # Translucent Watermark: *D1 (TCP/UDP Socket Implementation)
        lbl_wm_tel = QLabel("*D1")
        lbl_wm_tel.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_wm_tel.setStyleSheet("color: rgba(205, 214, 244, 0.4); font-size: 8px; font-weight: bold;")
        grid_tel.addWidget(lbl_wm_tel, 5, 1)

        right_col.addWidget(grp_tel)
        layout.addLayout(right_col, stretch=4)

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

        self.kpi_display = QLabel("Click the button above to run the 30-second automated benchmark comparison.")
        self.kpi_display.setStyleSheet("background: #181825; border-radius: 6px; padding: 16px; font-family: 'Consolas', monospace;")
        layout.addWidget(self.kpi_display)

        # Translucent Watermark: *D2 (Performance Evaluation & Comparison)
        lbl_wm_bm = QLabel("*D2")
        lbl_wm_bm.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_wm_bm.setStyleSheet("color: rgba(205, 214, 244, 0.4); font-size: 9px; font-weight: bold; padding: 4px;")
        layout.addWidget(lbl_wm_bm)

        return widget

    # Event handlers
    def _on_queue_changed(self, val):
        self.lbl_queue.setText(f"Queue Limit: {val} pkts")
        self.emulator.link_path_a.set_max_queue(val)
        self.emulator.link_path_b.set_max_queue(val)
        self.topo_canvas.queue_limit = val

    def _on_bw_changed(self, val):
        self.lbl_bw.setText(f"Bottleneck Bandwidth: {val}.0 Mbps")
        self.emulator.link_path_a.capacity_mbps = float(val)
        self.emulator.link_path_b.capacity_mbps = float(val)

    def _on_host_rate_changed(self, val):
        self.lbl_host_rate.setText(f"Main Sending Rate: {val}.0 Mbps")
        if self.main_sender:
            self.main_sender.set_rate(float(val))

    def _on_cross_rate_changed(self, val):
        self.lbl_cross_rate.setText(f"Cross-Traffic Burst: {val}.0 Mbps")

    def _toggle_rate_adapt(self):
        self.rate_adaptation_enabled = not self.rate_adaptation_enabled
        if self.rate_adaptation_enabled:
            self.btn_toggle_rate_adapt.setText("UDP Rate Adaptation: ON (Feedback Active)")
            self.btn_toggle_rate_adapt.setStyleSheet("background-color: #a6e3a1; color: #11111b;")
        else:
            self.btn_toggle_rate_adapt.setText("UDP Rate Adaptation: OFF")
            self.btn_toggle_rate_adapt.setStyleSheet("background-color: #313244; color: #cdd6f4;")
        if self.main_sender:
            self.main_sender.enable_rate_adaptation = self.rate_adaptation_enabled

    def _toggle_main_stream(self):
        if self.main_sender and self.main_sender._running:
            self.main_sender.stop()
            self.main_sender = None
            self.btn_toggle_sender.setText("▶ Start Main UDP Stream")
            self.btn_toggle_sender.setStyleSheet("background-color: #a6e3a1; color: #11111b;")
        else:
            rate = float(self.slider_host_rate.value())
            self.main_sender = UDPSender(
                target_ip="127.0.0.1",
                target_port=9000,
                rate_mbps=rate,
                flow_id=FLOW_MAIN,
                enable_rate_adaptation=self.rate_adaptation_enabled,
                feedback_port=9005
            )
            self.main_sender.start()
            self.btn_toggle_sender.setText("⏹ Stop Main UDP Stream")
            self.btn_toggle_sender.setStyleSheet("background-color: #eba0ac; color: #11111b;")

    def _inject_congestion(self):
        burst_rate = float(self.slider_cross_rate.value())
        self.is_cross_burst_active = True
        def burst():
            gen = CongestionGenerator(target_ip="127.0.0.1", target_port=9000, rate_mbps=burst_rate, duration=9.0)
            gen.run()
            self.is_cross_burst_active = False

        threading.Thread(target=burst, daemon=True).start()

    def _manual_reroute(self, to_path: str):
        self.controller._trigger_reroute(to_path=to_path, reason="Manual GUI operator override")

    def _toggle_sdn_mode(self):
        self.controller.adaptive_routing_enabled = not self.controller.adaptive_routing_enabled
        if self.controller.adaptive_routing_enabled:
            self.btn_toggle_sdn.setText("Auto-SDN Dynamic Rerouting: ON")
            self.btn_toggle_sdn.setStyleSheet("background-color: #89b4fa; color: #11111b;")
        else:
            self.btn_toggle_sdn.setText("Auto-SDN Dynamic Rerouting: OFF (STATIC)")
            self.btn_toggle_sdn.setStyleSheet("background-color: #f38ba8; color: #11111b;")

    def _reset_topology(self):
        if self.main_sender:
            self.main_sender.stop()
            self.main_sender = None
            self.btn_toggle_sender.setText("▶ Start Main UDP Stream")
            self.btn_toggle_sender.setStyleSheet("background-color: #a6e3a1; color: #11111b;")
        self.controller.current_active_path = PATH_PRIMARY
        self.controller.total_reroutes = 0
        self.controller.consecutive_breaches = 0
        self.controller.both_paths_congested = False
        QMessageBox.information(self, "Topology Reset", "Network topology reset to initial state. Active Path: Path-A.")

    def _run_benchmark_async(self):
        self.lbl_bench_status.setText("Status: Running benchmark... (takes ~35s)")
        def task():
            from src.benchmark import run_single_experiment
            s_res = run_single_experiment("STATIC", adaptive_enabled=False, total_duration=14.0, congestion_start=3.0, congestion_duration=7.0)
            d_res = run_single_experiment("DYNAMIC", adaptive_enabled=True, total_duration=14.0, congestion_start=3.0, congestion_duration=7.0)
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

        thpt = stats.get("throughput_mbps", 0.0)
        goodput = stats.get("goodput_mbps", 0.0)
        win_loss = stats.get("window_loss_pct", stats.get("loss_pct", 0.0))
        all_loss = stats.get("overall_loss_pct", 0.0)
        loss = win_loss
        lat = stats.get("avg_latency_ms", 0.0)
        jit = stats.get("jitter_ms", 0.0)
        recv = stats.get("total_received", 0)
        lost = stats.get("total_lost", 0)
        total_pkts = recv + lost

        self.lbl_val_thpt.setText(f"{thpt:.2f} Mbps (Goodput: {goodput:.2f}M)")
        self.lbl_val_loss.setText(f"{win_loss:.1f}% (Overall: {all_loss:.1f}%)")
        self.lbl_val_lat.setText(f"{lat:.1f} ms")
        self.lbl_val_jit.setText(f"{jit:.2f} ms")
        self.lbl_val_counts.setText(f"Recv: {recv:,} | Lost: {lost:,} (Total: {total_pkts:,})")

        # Active path status with dirty-checking
        active_path = ctrl_status["active_path"]
        both_congested = bool(ctrl_status.get("both_paths_congested"))
        status_key = f"{active_path}_{both_congested}"
        if status_key != self._last_active_path_status:
            self._last_active_path_status = status_key
            if both_congested:
                self.lbl_active_path_status.setText("CRITICAL: BOTH PATHS CONGESTED")
                self.lbl_active_path_status.setStyleSheet("background: #f38ba8; color: #11111b; padding: 4px 10px; border-radius: 4px; font-weight: bold;")
            elif active_path == PATH_PRIMARY:
                self.lbl_active_path_status.setText("ACTIVE PATH: Path-A (Primary)")
                self.lbl_active_path_status.setStyleSheet("background: #a6e3a1; color: #11111b; padding: 4px 10px; border-radius: 4px; font-weight: bold;")
            else:
                self.lbl_active_path_status.setText("ACTIVE PATH: Path-B (DYNAMICALLY REROUTED)")
                self.lbl_active_path_status.setStyleSheet("background: #89b4fa; color: #11111b; padding: 4px 10px; border-radius: 4px; font-weight: bold;")

        rec_sec = ctrl_status.get("latest_recovery_time_sec")
        if rec_sec != self._last_recovery_time_sec and rec_sec is not None:
            self._last_recovery_time_sec = rec_sec
            self.lbl_recovery_time.setText(f"Failover Latency: {rec_sec * 1000:.2f} ms")

        # Query live OpenFlow Flow Table Display with dirty checking
        flow_text = self.controller.get_flow_table("s1")
        if flow_text != self._last_flow_text:
            self.lbl_flow_table.setText(flow_text)
            self._last_flow_text = flow_text

        # Update visual topology
        load_a = ctrl_status.get("path_a_load_mbps", 0.0)
        load_b = ctrl_status.get("path_b_load_mbps", 0.0)
        is_congested = (load_a >= self.controller.congestion_threshold_mbps)

        # Compute virtual queue occupancy
        q_cur = self.emulator.link_path_a.packet_queue.qsize()
        q_max = self.emulator.link_path_a.max_queue
        q_pct = (q_cur / max(1, q_max)) * 100.0

        is_main_active = bool(self.main_sender and self.main_sender._running)
        self.topo_canvas.update_state(
            active_path, load_a, load_b, is_congested,
            q_pct, q_max, is_main_active, self.is_cross_burst_active
        )

        # Update real-time plot
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
