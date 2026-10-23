"""
Comprehensive Performance Profiling Suite.
Measures:
- RAM usage (RSS and Private Working Set in MB)
- CPU utilization (%)
- GUI main-thread latency and render duration (Matplotlib redraw, Topology paint)
- Telemetry processing throughput and latency
- Socket processing rate and time-per-packet
- Memory growth rate across extended runs
"""

import os
import sys
import time
import psutil
import threading
from collections import deque

# Run headless Qt for reproducible headless profiling
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from src.gui_app import MasterSDNGUI
from src.udp_sender import UDPSender
from src.udp_receiver import UDPReceiver
from src.network_emulator import NetworkEmulator
from src.sdn_controller import SDNController
from src.protocol import FLOW_MAIN, FLOW_CROSS


def get_mem_mb():
    proc = psutil.Process(os.getpid())
    mem_info = proc.memory_info()
    rss_mb = mem_info.rss / (1024 * 1024)
    # On Windows, private working set is private memory
    private_mb = getattr(mem_info, "private", mem_info.rss) / (1024 * 1024)
    return rss_mb, private_mb


def profile_gui_and_subsystems():
    print("=" * 70)
    print("     SDN CONGESTION DETECTION & REROUTING - PROFILING BASELINE")
    print("=" * 70)

    proc = psutil.Process(os.getpid())
    t0_start = time.perf_counter()

    app = QApplication.instance() or QApplication(sys.argv)
    gui = MasterSDNGUI()
    gui.show()
    t_startup = (time.perf_counter() - t0_start) * 1000.0

    rss_idle, priv_idle = get_mem_mb()
    print(f"[*] Startup Time: {t_startup:.2f} ms")
    print(f"[*] Idle Memory: RSS = {rss_idle:.2f} MB | Private = {priv_idle:.2f} MB")

    # 1. Profile Matplotlib Plot Redraw Duration
    plot_durations = []
    for step in range(50):
        t_plot_start = time.perf_counter()
        gui.plot_canvas.update_plot(step * 0.1, 5.5, 2.0)
        plot_durations.append((time.perf_counter() - t_plot_start) * 1000.0)

    avg_plot_dur = sum(plot_durations) / len(plot_durations)
    max_plot_dur = max(plot_durations)
    print(f"\n[Plot Canvas] Matplotlib update_plot() Duration:")
    print(f"    Average: {avg_plot_dur:.2f} ms | Max: {max_plot_dur:.2f} ms")

    # 2. Profile Topology Canvas Animation / Paint Step
    anim_durations = []
    gui.topo_canvas.flow_main_active = True
    gui.topo_canvas.flow_cross_active = True
    for step in range(100):
        t_anim_start = time.perf_counter()
        gui.topo_canvas._step_animation()
        # Trigger synthetic repaint
        gui.topo_canvas.repaint()
        anim_durations.append((time.perf_counter() - t_anim_start) * 1000.0)

    avg_anim_dur = sum(anim_durations) / len(anim_durations)
    max_anim_dur = max(anim_durations)
    print(f"\n[Topology Canvas] Animation Step + Repaint Duration:")
    print(f"    Average: {avg_anim_dur:.2f} ms | Max: {max_anim_dur:.2f} ms")

    # 3. Profile Telemetry Refresh Loop in GUI
    tel_durations = []
    for step in range(50):
        t_tel_start = time.perf_counter()
        gui._refresh_telemetry()
        tel_durations.append((time.perf_counter() - t_tel_start) * 1000.0)

    avg_tel_dur = sum(tel_durations) / len(tel_durations)
    max_tel_dur = max(tel_durations)
    print(f"\n[GUI Main Thread] _refresh_telemetry() Loop Duration:")
    print(f"    Average: {avg_tel_dur:.2f} ms | Max: {max_tel_dur:.2f} ms")

    # 4. Profile Streaming Memory & CPU
    print(f"\n[*] Starting 5-second streaming workload (Main 6M + Cross 7M)...")
    gui._toggle_main_stream()
    gui._inject_congestion()

    cpu_samples = []
    mem_samples = []
    for _ in range(10):
        time.sleep(0.5)
        cpu_samples.append(proc.cpu_percent(interval=None))
        mem_samples.append(get_mem_mb())

    rss_stream = [m[0] for m in mem_samples]
    priv_stream = [m[1] for m in mem_samples]
    avg_cpu = sum(cpu_samples) / max(1, len(cpu_samples))

    print(f"[Streaming Workload] (6 Mbps main + 7 Mbps cross):")
    print(f"    CPU Utilization: {avg_cpu:.1f}%")
    print(f"    Peak RSS Memory: {max(rss_stream):.2f} MB (Private: {max(priv_stream):.2f} MB)")
    print(f"    Memory Delta: +{max(rss_stream) - rss_idle:.2f} MB")

    # Clean teardown
    gui.close()
    app.processEvents()

    # 5. Profile Unbounded List Allocations in UDPReceiver
    print("\n[Telemetry Storage] Testing packet list growth in UDPReceiver...")
    test_recv = UDPReceiver(bind_ip="127.0.0.1", bind_port=29990)
    test_recv.start()
    test_send = UDPSender(target_ip="127.0.0.1", target_port=29990, rate_mbps=8.0, duration=2.0)
    test_send.start()
    time.sleep(2.5)
    test_send.stop()
    test_recv.stop()

    print(f"    Latencies recorded in list: {len(test_recv.latencies_ms)} items")
    print(f"    History snapshots recorded: {len(test_recv.history)} items")
    print(f"    Note: latencies_ms is currently an unbounded Python list!")

    print("\n" + "=" * 70)
    print("                 BASE PROFILING COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    profile_gui_and_subsystems()
