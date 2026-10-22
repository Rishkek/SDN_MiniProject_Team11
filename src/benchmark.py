"""
Automated Performance Evaluation and Comparison Engine.
Compares Static Routing (Baseline) vs Dynamic SDN Adaptive Routing.
Measures Recovery Time, Throughput, Packet Loss, Latency, and Jitter.
Topic 27: Congestion Detection and Traffic Rerouting.
"""

import time
import json
import os
import threading
from typing import Dict, Any, List

try:
    import matplotlib
    matplotlib.use("Agg")  # Headless rendering for VM/server
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    from tabulate import tabulate
    TABULATE_AVAILABLE = True
except ImportError:
    TABULATE_AVAILABLE = False

try:
    from src.udp_sender import UDPSender
    from src.udp_receiver import UDPReceiver
    from src.congestion_generator import CongestionGenerator
    from src.sdn_controller import SDNController
    from src.network_emulator import NetworkEmulator
    from src.protocol import FLOW_MAIN
    from src.config import (
        MAIN_UDP_PORT, CROSS_UDP_PORT, MAIN_TRAFFIC_RATE_MBPS,
        CROSS_TRAFFIC_RATE_MBPS, CONGESTION_THRESHOLD_MBPS
    )
except ImportError:
    from udp_sender import UDPSender
    from udp_receiver import UDPReceiver
    from congestion_generator import CongestionGenerator
    from sdn_controller import SDNController
    from network_emulator import NetworkEmulator
    from protocol import FLOW_MAIN
    from config import (
        MAIN_UDP_PORT, CROSS_UDP_PORT, MAIN_TRAFFIC_RATE_MBPS,
        CROSS_TRAFFIC_RATE_MBPS, CONGESTION_THRESHOLD_MBPS
    )


def run_single_experiment(
    mode_name: str,
    adaptive_enabled: bool,
    total_duration: float = 24.0,
    congestion_start: float = 7.0,
    congestion_duration: float = 10.0
) -> Dict[str, Any]:
    """
    Executes an end-to-end experiment run with real UDP sockets and virtual switches.
    """
    print(f"\n=======================================================")
    print(f"[*] STARTING TEST RUN: {mode_name}")
    print(f"[*] Adaptive SDN Rerouting: {'ENABLED' if adaptive_enabled else 'DISABLED (STATIC)'}")
    print(f"=======================================================")

    # 1. Start SDN Controller
    controller = SDNController(
        congestion_threshold_mbps=CONGESTION_THRESHOLD_MBPS,
        adaptive_routing_enabled=adaptive_enabled
    )
    controller.start()

    # 2. Start Network Emulator (Ingress proxy port 9000)
    emulator = NetworkEmulator(controller=controller, ingress_port=9000)
    emulator.start()

    # 3. Start UDP Receiver on H2 (Port 9999)
    receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=MAIN_UDP_PORT)
    receiver.start()

    # 4. Start Receiver for Cross Traffic on H4 (Port 9998)
    cross_receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=CROSS_UDP_PORT)
    cross_receiver.start()

    time.sleep(0.5)

    # 5. Start Main UDP Sender (H1 -> Emulator port 9000)
    main_sender = UDPSender(
        target_ip="127.0.0.1",
        target_port=9000,
        rate_mbps=MAIN_TRAFFIC_RATE_MBPS,
        duration=total_duration,
        flow_id=FLOW_MAIN
    )
    main_sender.start()
    print(f"[+] Main flow started: {MAIN_TRAFFIC_RATE_MBPS} Mbps UDP stream.")

    # 6. Schedule Cross-Traffic Congestion Generator
    def run_cross():
        gen = CongestionGenerator(
            target_ip="127.0.0.1",
            target_port=9000,
            rate_mbps=CROSS_TRAFFIC_RATE_MBPS,
            start_delay=congestion_start,
            duration=congestion_duration
        )
        gen.run()

    cross_thread = threading.Thread(target=run_cross, daemon=True)
    cross_thread.start()

    # 7. Monitor experiment timeline
    start_t = time.time()
    while time.time() - start_t < total_duration + 2.0:
        time.sleep(1.0)
        cur_elapsed = time.time() - start_t
        stats = receiver.get_latest_stats()
        ctrl_status = controller.get_controller_status()
        print(
            f"[{mode_name:<8}] T={cur_elapsed:>4.1f}s | "
            f"Thpt: {stats['throughput_mbps']:>5.2f} Mbps | "
            f"Loss: {stats['loss_pct']:>5.1f}% | "
            f"Path: {ctrl_status['active_path']} | "
            f"Path-A Load: {ctrl_status['path_a_load_mbps']:>4.1f}M"
        )

    # Teardown
    main_sender.stop()
    cross_thread.join(timeout=1.0)
    cross_receiver.stop()
    receiver.stop()
    emulator.stop()
    controller.stop()

    time_series = list(receiver.history)
    recovery_time = controller.recovery_time_sec or 0.0

    # Aggregate summaries
    thpts = [p["throughput_mbps"] for p in time_series if p.get("throughput_mbps") is not None]
    losses = [p["loss_pct"] for p in time_series if p.get("loss_pct") is not None]
    latencies = [p["avg_latency_ms"] for p in time_series if p.get("avg_latency_ms", 0) > 0]
    jitters = [p["jitter_ms"] for p in time_series if p.get("jitter_ms") is not None]

    avg_thpt = sum(thpts) / len(thpts) if thpts else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    peak_loss = max(losses) if losses else 0.0
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    avg_jit = sum(jitters) / len(jitters) if jitters else 0.0

    print(f"\n[+] {mode_name} Run Completed.")
    print(f"    Avg Throughput : {avg_thpt:.2f} Mbps")
    print(f"    Avg Loss Rate  : {avg_loss:.2f}% (Peak: {peak_loss:.2f}%)")
    print(f"    Recovery Time  : {recovery_time:.3f} s")

    return {
        "mode": mode_name,
        "adaptive_enabled": adaptive_enabled,
        "avg_throughput_mbps": round(avg_thpt, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "peak_loss_pct": round(peak_loss, 2),
        "avg_latency_ms": round(avg_lat, 2),
        "avg_jitter_ms": round(avg_jit, 2),
        "recovery_time_sec": round(recovery_time, 3),
        "total_packets_sent": main_sender.packets_sent,
        "total_packets_received": receiver.total_packets_received,
        "total_packets_lost": receiver.total_packets_lost,
        "reroute_events": controller.reroute_events,
        "time_series": time_series
    }


def plot_benchmark_results(static_res: Dict[str, Any], dynamic_res: Dict[str, Any], output_path: str = "evaluation_results.png"):
    """Generates a 4-panel comparative evaluation chart."""
    if not MATPLOTLIB_AVAILABLE:
        print("[!] Matplotlib not available; skipping plot generation.")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("SDN Congestion Detection and Traffic Rerouting - Evaluation", fontsize=15, fontweight="bold")

    stat_ts = static_res["time_series"]
    dyn_ts = dynamic_res["time_series"]

    stat_times = [p["timestamp"] for p in stat_ts]
    stat_thpt = [p["throughput_mbps"] for p in stat_ts]
    stat_loss = [p["loss_pct"] for p in stat_ts]
    stat_lat = [p["avg_latency_ms"] for p in stat_ts]

    dyn_times = [p["timestamp"] for p in dyn_ts]
    dyn_thpt = [p["throughput_mbps"] for p in dyn_ts]
    dyn_loss = [p["loss_pct"] for p in dyn_ts]
    dyn_lat = [p["avg_latency_ms"] for p in dyn_ts]

    # Plot 1: Throughput over Time
    ax1 = axes[0, 0]
    ax1.plot(stat_times, stat_thpt, label="Static Routing (Baseline)", color="#d9534f", linestyle="--", linewidth=2.0)
    ax1.plot(dyn_times, dyn_thpt, label="Dynamic SDN Rerouting", color="#28a745", linewidth=2.5)
    ax1.axvspan(7.0, 17.0, color="#ffeeba", alpha=0.5, label="Congestion Burst (7-17s)")
    ax1.axhline(6.0, color="#6c757d", linestyle=":", label="Nominal Rate (6 Mbps)")
    ax1.set_title("UDP Throughput over Time (Mbps)", fontweight="bold")
    ax1.set_xlabel("Time (seconds)")
    ax1.set_ylabel("Throughput (Mbps)")
    ax1.set_ylim(0, 8.0)
    ax1.grid(True, linestyle="--", alpha=0.6)
    ax1.legend(loc="lower right")

    # Plot 2: Packet Loss Rate (%) over Time
    ax2 = axes[0, 1]
    ax2.plot(stat_times, stat_loss, label="Static Routing (Congested)", color="#d9534f", linestyle="--", linewidth=2.0)
    ax2.plot(dyn_times, dyn_loss, label="Dynamic SDN (Rerouted)", color="#28a745", linewidth=2.5)
    ax2.axvspan(7.0, 17.0, color="#ffeeba", alpha=0.5)
    ax2.set_title("Packet Loss Rate (%)", fontweight="bold")
    ax2.set_xlabel("Time (seconds)")
    ax2.set_ylabel("Loss Rate (%)")
    ax2.set_ylim(-2, 60)
    ax2.grid(True, linestyle="--", alpha=0.6)
    ax2.legend(loc="upper right")

    # Plot 3: End-to-End Latency
    ax3 = axes[1, 0]
    ax3.plot(stat_times, stat_lat, label="Static Latency (Bufferbloat Spike)", color="#d9534f", linestyle="--", linewidth=2.0)
    ax3.plot(dyn_times, dyn_lat, label="Dynamic Latency (Path B: 15ms)", color="#007bff", linewidth=2.5)
    ax3.axvspan(7.0, 17.0, color="#ffeeba", alpha=0.5)
    ax3.set_title("One-Way Latency (ms)", fontweight="bold")
    ax3.set_xlabel("Time (seconds)")
    ax3.set_ylabel("Latency (ms)")
    ax3.grid(True, linestyle="--", alpha=0.6)
    ax3.legend(loc="upper left")

    # Plot 4: Summary Comparison Bar Chart
    ax4 = axes[1, 1]
    metrics = ["Avg Throughput (Mbps)", "Packet Loss (%)", "Recovery Time (s)"]
    static_vals = [static_res["avg_throughput_mbps"], static_res["avg_loss_pct"], total_duration := 10.0]
    dyn_vals = [dynamic_res["avg_throughput_mbps"], dynamic_res["avg_loss_pct"], dynamic_res["recovery_time_sec"]]

    x = range(len(metrics))
    width = 0.35
    ax4.bar([i - width/2 for i in x], static_vals, width, label="Static Routing", color="#d9534f")
    ax4.bar([i + width/2 for i in x], dyn_vals, width, label="Dynamic SDN", color="#28a745")
    ax4.set_title("Key Performance Indicator Comparison", fontweight="bold")
    ax4.set_xticks(x)
    ax4.set_xticklabels(metrics)
    ax4.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax4.legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    print(f"\n[+] High-resolution evaluation graph saved to: {os.path.abspath(output_path)}")


def run_benchmark():
    """Runs both tests, compiles metrics, prints summary table, and generates plot."""
    static_results = run_single_experiment("STATIC", adaptive_enabled=False)
    time.sleep(2.0)
    dynamic_results = run_single_experiment("DYNAMIC", adaptive_enabled=True)

    summary_data = [
        ["Routing Approach", "Static (No Reroute)", "Dynamic SDN (Adaptive)"],
        ["Average Throughput (Mbps)", f"{static_results['avg_throughput_mbps']} Mbps", f"{dynamic_results['avg_throughput_mbps']} Mbps"],
        ["Average Packet Loss (%)", f"{static_results['avg_loss_pct']}%", f"{dynamic_results['avg_loss_pct']}%"],
        ["Peak Packet Loss (%)", f"{static_results['peak_loss_pct']}%", f"{dynamic_results['peak_loss_pct']}%"],
        ["Average Latency (ms)", f"{static_results['avg_latency_ms']} ms", f"{dynamic_results['avg_latency_ms']} ms"],
        ["Average Jitter (ms)", f"{static_results['avg_jitter_ms']} ms", f"{dynamic_results['avg_jitter_ms']} ms"],
        ["Congestion Recovery Time", "No Recovery (Sustained Loss)", f"{dynamic_results['recovery_time_sec']} seconds"],
        ["Total Packets Received", static_results["total_packets_received"], dynamic_results["total_packets_received"]],
        ["Total Packets Lost", static_results["total_packets_lost"], dynamic_results["total_packets_lost"]],
        ["SDN Reroute Count", 0, len(dynamic_results["reroute_events"])]
    ]

    print("\n" + "=" * 65)
    print("      FINAL PERFORMANCE EVALUATION AND COMPARISON TABLE")
    print("=" * 65)
    try:
        if TABULATE_AVAILABLE:
            print(tabulate(summary_data, headers="firstrow", tablefmt="grid"))
        else:
            for row in summary_data:
                print(f"{row[0]:<28} | {row[1]:<25} | {row[2]}")
    except Exception:
        for row in summary_data:
            print(f"{row[0]:<28} | {row[1]:<25} | {row[2]}")
    print("=" * 65)

    plot_benchmark_results(static_results, dynamic_results)

    # Save summary json
    with open("benchmark_summary.json", "w") as f:
        json.dump({"static": static_results, "dynamic": dynamic_results}, f, indent=2)
    print("[+] Saved benchmark data to benchmark_summary.json")


if __name__ == "__main__":
    run_benchmark()
