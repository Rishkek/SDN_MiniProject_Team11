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
    enable_rate_adapt: bool = False,
    total_duration: float = 14.0,
    congestion_start: float = 3.0,
    congestion_duration: float = 7.0,
    ingress_port: int = 9000,
    main_port: int = MAIN_UDP_PORT,
    cross_port: int = CROSS_UDP_PORT,
    feedback_port: int = 9005,
    progress_callback = None
) -> Dict[str, Any]:
    """
    Executes an end-to-end experiment run with real UDP sockets and virtual switches.
    """
    print(f"\n=======================================================")
    print(f"[*] STARTING TEST RUN: {mode_name}")
    print(f"[*] Adaptive SDN Rerouting: {'ENABLED' if adaptive_enabled else 'DISABLED (STATIC)'}")
    print(f"[*] UDP Rate Adaptation   : {'ENABLED' if enable_rate_adapt else 'DISABLED'}")
    print(f"[*] Ports: Ingress={ingress_port} | MainDest={main_port} | CrossDest={cross_port}")
    print(f"=======================================================")

    # 1. Start SDN Controller
    controller = SDNController(
        congestion_threshold_mbps=CONGESTION_THRESHOLD_MBPS,
        adaptive_routing_enabled=adaptive_enabled
    )
    controller.start()

    # 2. Start Network Emulator
    emulator = NetworkEmulator(
        controller=controller,
        ingress_port=ingress_port,
        main_dest_port=main_port,
        cross_dest_port=cross_port
    )
    emulator.start()

    # 3. Start UDP Receiver on H2 with feedback if enabled
    fb_target = ("127.0.0.1", feedback_port) if enable_rate_adapt else None
    receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=main_port, feedback_target=fb_target)
    receiver.start()

    # 4. Start Receiver for Cross Traffic on H4
    cross_receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=cross_port)
    cross_receiver.start()

    time.sleep(0.3)

    # 5. Start Main UDP Sender (H1 -> Emulator ingress port)
    main_sender = UDPSender(
        target_ip="127.0.0.1",
        target_port=ingress_port,
        rate_mbps=MAIN_TRAFFIC_RATE_MBPS,
        duration=total_duration,
        flow_id=FLOW_MAIN,
        enable_rate_adaptation=enable_rate_adapt,
        feedback_port=feedback_port if enable_rate_adapt else None
    )
    main_sender.start()
    print(f"[+] Main flow started: {MAIN_TRAFFIC_RATE_MBPS} Mbps UDP stream on port {ingress_port}.")

    # 6. Schedule Cross-Traffic Congestion Generator
    def run_cross():
        gen = CongestionGenerator(
            target_ip="127.0.0.1",
            target_port=ingress_port,
            rate_mbps=CROSS_TRAFFIC_RATE_MBPS,
            start_delay=congestion_start,
            duration=congestion_duration
        )
        gen.run()

    cross_thread = threading.Thread(target=run_cross, daemon=True)
    cross_thread.start()

    # 7. Monitor experiment timeline
    start_t = time.time()
    peak_q = 0
    while time.time() - start_t < total_duration + 1.2:
        time.sleep(0.5)
        cur_elapsed = time.time() - start_t
        stats = receiver.get_latest_stats()
        ctrl_status = controller.get_controller_status()
        q_now = emulator.link_path_a.packet_queue.qsize()
        peak_q = max(peak_q, q_now)
        if progress_callback:
            try:
                progress_callback(mode_name, cur_elapsed, total_duration)
            except Exception:
                pass
        print(
            f"[{mode_name:<8}] T={cur_elapsed:>4.1f}s | "
            f"Thpt: {stats['throughput_mbps']:>5.2f}M | "
            f"Goodput: {stats['goodput_mbps']:>5.2f}M | "
            f"WinLoss: {stats['window_loss_pct']:>4.1f}% | "
            f"AllLoss: {stats['overall_loss_pct']:>4.1f}% | "
            f"Q: {q_now:>2d} pkts | "
            f"Path: {ctrl_status['active_path']}"
        )

    # Teardown
    main_sender.stop()
    cross_thread.join(timeout=1.0)
    cross_receiver.stop()
    receiver.stop()
    emulator.stop()
    controller.stop()
    time.sleep(0.3)

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
        "rate_adapt_enabled": enable_rate_adapt,
        "congestion_start": congestion_start,
        "congestion_duration": congestion_duration,
        "congestion_end": round(congestion_start + congestion_duration, 2),
        "total_duration": total_duration,
        "avg_throughput_mbps": round(avg_thpt, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "peak_loss_pct": round(peak_loss, 2),
        "avg_latency_ms": round(avg_lat, 2),
        "avg_jitter_ms": round(avg_jit, 2),
        "peak_queue_pkts": peak_q,
        "recovery_time_sec": round(recovery_time, 3),
        "total_packets_sent": main_sender.packets_sent,
        "total_packets_received": receiver.total_packets_received,
        "total_packets_lost": receiver.total_packets_lost,
        "reroute_events": controller.reroute_events,
        "time_series": time_series
    }


def plot_benchmark_results(
    static_res: Dict[str, Any],
    dynamic_res: Dict[str, Any],
    rate_res: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = "evaluation_results.png",
    fig: Optional[Any] = None,
    dark_mode: bool = True,
    run_label: Optional[str] = None
) -> Any:
    """Generates a comprehensive 4-panel comparative evaluation chart with dark/light theme support."""
    if not MATPLOTLIB_AVAILABLE:
        print("[!] Matplotlib not available; skipping plot generation.")
        return None

    if fig is None:
        fig = plt.figure(figsize=(13, 7.8), dpi=110)
    else:
        fig.clear()

    # Theme colors
    if dark_mode:
        bg_fig = "#181825"
        bg_ax = "#1e1e2e"
        col_text = "#cdd6f4"
        col_title = "#89b4fa"
        col_grid = "#313244"
        col_spine = "#45475a"
        col_static = "#f38ba8"  # Catppuccin red/pink
        col_dynamic = "#a6e3a1" # Catppuccin green
        col_rate = "#89b4fa"    # Catppuccin blue
        col_burst = "#fab387"   # Catppuccin peach
        col_nom = "#f9e2af"     # Catppuccin yellow
        legend_bg = "#181825"
    else:
        bg_fig = "#ffffff"
        bg_ax = "#f8f9fa"
        col_text = "#212529"
        col_title = "#0d6efd"
        col_grid = "#dee2e6"
        col_spine = "#ced4da"
        col_static = "#dc3545"
        col_dynamic = "#198754"
        col_rate = "#0d6efd"
        col_burst = "#fd7e14"
        col_nom = "#6c757d"
        legend_bg = "#ffffff"

    fig.patch.set_facecolor(bg_fig)

    axes = fig.subplots(2, 2)
    title_text = "SDN Congestion Detection and Traffic Rerouting - Empirical Performance Evaluation"
    if run_label:
        title_text += f" [{run_label}]"
    fig.suptitle(title_text, fontsize=12.0, fontweight="bold", color=col_title, y=0.985)

    stat_ts = static_res.get("time_series", [])
    dyn_ts = dynamic_res.get("time_series", [])

    stat_times = [p["timestamp"] for p in stat_ts]
    stat_thpt = [p["throughput_mbps"] for p in stat_ts]
    stat_loss = [p["loss_pct"] for p in stat_ts]
    stat_lat = [p["avg_latency_ms"] for p in stat_ts]

    dyn_times = [p["timestamp"] for p in dyn_ts]
    dyn_thpt = [p["throughput_mbps"] for p in dyn_ts]
    dyn_loss = [p["loss_pct"] for p in dyn_ts]
    dyn_lat = [p["avg_latency_ms"] for p in dyn_ts]

    # Detect congestion span dynamically from experiment metadata or time series
    c_start = dynamic_res.get("congestion_start")
    if c_start is None:
        c_start = 3.0 if (dyn_times and dyn_times[-1] <= 18.0) else 6.0
    c_end = dynamic_res.get("congestion_end")
    if c_end is None:
        c_end = (c_start + dynamic_res.get("congestion_duration", 7.0)) if (dyn_times and dyn_times[-1] <= 18.0) else 16.0

    for ax in axes.flat:
        ax.set_facecolor(bg_ax)
        ax.grid(True, linestyle="--", alpha=0.40, color=col_grid)
        ax.tick_params(colors=col_text, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(col_spine)

    # Plot 1: Throughput over Time
    ax1 = axes[0, 0]
    ax1.plot(stat_times, stat_thpt, label="Static Routing (Exp A - Congested)", color=col_static, linestyle="--", linewidth=2.0)
    ax1.plot(dyn_times, dyn_thpt, label="Dynamic SDN (Exp B - Restored)", color=col_dynamic, linewidth=2.5)
    if rate_res:
        r_ts = rate_res.get("time_series", [])
        ax1.plot([p["timestamp"] for p in r_ts], [p["throughput_mbps"] for p in r_ts], label="SDN + Rate Control (Exp C)", color=col_rate, linestyle="-.", linewidth=2.0)
    ax1.axvspan(c_start, c_end, color=col_burst, alpha=0.18, label=f"Congestion Burst ({c_start:.0f}-{c_end:.0f}s)")
    ax1.axhline(6.0, color=col_nom, linestyle=":", linewidth=1.5, label="Nominal Rate (6M)")
    ax1.set_title("UDP Throughput over Time (Mbps)", fontweight="bold", fontsize=9.5, color=col_text, pad=7)
    ax1.set_xlabel("Elapsed Time (s)", fontsize=8.5, color=col_text)
    ax1.set_ylabel("Throughput (Mbps)", fontsize=8.5, color=col_text)
    ax1.set_ylim(0, 8.5)
    ax1.legend(loc="lower right", fontsize=7.5, facecolor=legend_bg, edgecolor=col_spine, labelcolor=col_text)

    # Plot 2: Packet Loss Rate (%) over Time
    ax2 = axes[0, 1]
    ax2.plot(stat_times, stat_loss, label="Static Routing (Sustained Drop)", color=col_static, linestyle="--", linewidth=2.0)
    ax2.plot(dyn_times, dyn_loss, label="Dynamic SDN (Sub-second Recovery)", color=col_dynamic, linewidth=2.5)
    if rate_res:
        r_ts = rate_res.get("time_series", [])
        ax2.plot([p["timestamp"] for p in r_ts], [p["loss_pct"] for p in r_ts], label="SDN + Rate Control", color=col_rate, linestyle="-.", linewidth=2.0)
    ax2.axvspan(c_start, c_end, color=col_burst, alpha=0.18)
    ax2.set_title("Packet Loss Rate (%) over Time", fontweight="bold", fontsize=9.5, color=col_text, pad=7)
    ax2.set_xlabel("Elapsed Time (s)", fontsize=8.5, color=col_text)
    ax2.set_ylabel("Loss Rate (%)", fontsize=8.5, color=col_text)
    ax2.set_ylim(-2, 70)
    ax2.legend(loc="upper right", fontsize=7.5, facecolor=legend_bg, edgecolor=col_spine, labelcolor=col_text)

    # Plot 3: End-to-End One-Way Latency
    ax3 = axes[1, 0]
    ax3.plot(stat_times, stat_lat, label="Static Latency (Bufferbloat Spikes)", color=col_static, linestyle="--", linewidth=2.0)
    ax3.plot(dyn_times, dyn_lat, label="Dynamic Latency (Path B: 15ms)", color=col_dynamic, linewidth=2.5)
    if rate_res:
        r_ts = rate_res.get("time_series", [])
        ax3.plot([p["timestamp"] for p in r_ts], [p["avg_latency_ms"] for p in r_ts], label="SDN + Rate Control Latency", color=col_rate, linestyle="-.", linewidth=2.0)
    ax3.axvspan(c_start, c_end, color=col_burst, alpha=0.18)
    ax3.set_title("End-to-End One-Way Latency (ms)", fontweight="bold", fontsize=9.5, color=col_text, pad=7)
    ax3.set_xlabel("Elapsed Time (s)", fontsize=8.5, color=col_text)
    ax3.set_ylabel("Latency (ms)", fontsize=8.5, color=col_text)
    ax3.legend(loc="upper left", fontsize=7.5, facecolor=legend_bg, edgecolor=col_spine, labelcolor=col_text)

    # Plot 4: Summary Comparison Bar Chart
    ax4 = axes[1, 1]
    metrics = ["Avg Thpt (M)", "Avg Loss (%)", "Peak Loss (%)"]
    static_vals = [static_res["avg_throughput_mbps"], static_res["avg_loss_pct"], static_res["peak_loss_pct"]]
    dyn_vals = [dynamic_res["avg_throughput_mbps"], dynamic_res["avg_loss_pct"], dynamic_res["peak_loss_pct"]]

    x = [0, 1, 2]
    width = 0.26
    b1 = ax4.bar([i - width for i in x], static_vals, width, label="Static Routing", color=col_static)
    b2 = ax4.bar([i for i in x], dyn_vals, width, label="Dynamic SDN", color=col_dynamic)
    if rate_res:
        rate_vals = [rate_res["avg_throughput_mbps"], rate_res["avg_loss_pct"], rate_res["peak_loss_pct"]]
        b3 = ax4.bar([i + width for i in x], rate_vals, width, label="SDN + Rate Adapt", color=col_rate)

    ax4.set_title("Performance Comparison Summary", fontweight="bold", fontsize=9.5, color=col_text, pad=7)
    ax4.set_xticks(x)
    ax4.set_xticklabels(metrics, fontsize=8.5, color=col_text)
    ax4.legend(fontsize=7.5, facecolor=legend_bg, edgecolor=col_spine, labelcolor=col_text)

    fig.subplots_adjust(top=0.92, bottom=0.08, left=0.07, right=0.97, hspace=0.44, wspace=0.20)

    if output_path:
        try:
            fig.savefig(output_path, dpi=180, facecolor=fig.get_facecolor(), bbox_inches="tight")
            print(f"[+] Evaluation graph saved to: {os.path.abspath(output_path)}")
        except Exception as e:
            print(f"[!] Could not save plot image ({e})")

    return fig


def run_benchmark(total_duration: float = 14.0, congestion_start: float = 3.0, congestion_duration: float = 7.0):
    """Runs Experiments A, B, and C, compiles metrics, prints summary table, and generates plot."""
    print("\n=======================================================")
    print("        RUNNING COMPREHENSIVE 3-PHASE BENCHMARK")
    print("=======================================================")
    static_results = run_single_experiment("STATIC", adaptive_enabled=False, enable_rate_adapt=False,
                                           total_duration=total_duration, congestion_start=congestion_start, congestion_duration=congestion_duration)
    time.sleep(1.0)
    dynamic_results = run_single_experiment("DYNAMIC", adaptive_enabled=True, enable_rate_adapt=False,
                                            total_duration=total_duration, congestion_start=congestion_start, congestion_duration=congestion_duration)
    time.sleep(1.0)
    rate_results = run_single_experiment("SDN+RATE", adaptive_enabled=True, enable_rate_adapt=True,
                                         total_duration=total_duration, congestion_start=congestion_start, congestion_duration=congestion_duration)

    summary_data = [
        ["Routing Approach", "Static (Exp A)", "Dynamic SDN (Exp B)", "SDN + Rate Control (Exp C)"],
        ["Average Throughput (Mbps)", f"{static_results['avg_throughput_mbps']} Mbps", f"{dynamic_results['avg_throughput_mbps']} Mbps", f"{rate_results['avg_throughput_mbps']} Mbps"],
        ["Average Packet Loss (%)", f"{static_results['avg_loss_pct']}%", f"{dynamic_results['avg_loss_pct']}%", f"{rate_results['avg_loss_pct']}%"],
        ["Peak Packet Loss (%)", f"{static_results['peak_loss_pct']}%", f"{dynamic_results['peak_loss_pct']}%", f"{rate_results['peak_loss_pct']}%"],
        ["Average Latency (ms)", f"{static_results['avg_latency_ms']} ms", f"{dynamic_results['avg_latency_ms']} ms", f"{rate_results['avg_latency_ms']} ms"],
        ["Average Jitter (ms)", f"{static_results['avg_jitter_ms']} ms", f"{dynamic_results['avg_jitter_ms']} ms", f"{rate_results['avg_jitter_ms']} ms"],
        ["Peak Queue Depth", f"{static_results['peak_queue_pkts']} pkts", f"{dynamic_results['peak_queue_pkts']} pkts", f"{rate_results['peak_queue_pkts']} pkts"],
        ["Congestion Recovery Time", "No Recovery (Sustained)", f"{dynamic_results['recovery_time_sec']}s", f"{rate_results['recovery_time_sec']}s"],
        ["Total Packets Received", f"{static_results['total_packets_received']:,}", f"{dynamic_results['total_packets_received']:,}", f"{rate_results['total_packets_received']:,}"],
        ["Total Packets Lost", f"{static_results['total_packets_lost']:,}", f"{dynamic_results['total_packets_lost']:,}", f"{rate_results['total_packets_lost']:,}"],
        ["SDN Reroute Count", 0, len(dynamic_results["reroute_events"]), len(rate_results["reroute_events"])]
    ]

    print("\n" + "=" * 80)
    print("      FINAL PERFORMANCE EVALUATION AND COMPARISON TABLE (EXPERIMENTS A, B, C)")
    print("=" * 80)
    try:
        if TABULATE_AVAILABLE:
            print(tabulate(summary_data, headers="firstrow", tablefmt="grid"))
        else:
            for row in summary_data:
                print(f"{row[0]:<28} | {row[1]:<20} | {row[2]:<22} | {row[3]}")
    except Exception:
        for row in summary_data:
            print(f"{row[0]:<28} | {row[1]:<20} | {row[2]:<22} | {row[3]}")
    print("=" * 80)

    plot_benchmark_results(static_results, dynamic_results, rate_results, output_path="evaluation_results.png", dark_mode=True)

    # Save summary json
    with open("benchmark_summary.json", "w") as f:
        json.dump({"static": static_results, "dynamic": dynamic_results, "sdn_rate_control": rate_results}, f, indent=2)
    print("[+] Saved benchmark data to benchmark_summary.json")


if __name__ == "__main__":
    run_benchmark()
