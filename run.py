#!/usr/bin/env python3
"""
Main Execution and Orchestration Launcher.
Topic 27: SDN Congestion Detection and Traffic Rerouting.

Usage:
  Interactive Menu:
    python3 run.py
  CLI Fast Flags:
    python3 run.py --demo
    python3 run.py --benchmark
    python3 run.py --test
    python3 run.py --mininet
"""

import sys
import os
import time
import argparse
import platform
import subprocess

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.config import (
    MAIN_UDP_PORT, CROSS_UDP_PORT, MAIN_TRAFFIC_RATE_MBPS,
    CROSS_TRAFFIC_RATE_MBPS, CONGESTION_THRESHOLD_MBPS,
    PATH_PRIMARY, PATH_ALTERNATE
)


def print_banner():
    banner = r"""
=============================================================================
   SDN CONGESTION DETECTION AND TRAFFIC REROUTING SYSTEM (TOPIC #27)
   Low-Level UDP Socket Programming + Dynamic OpenFlow SDN Control
=============================================================================
    """
    print(banner)


def run_interactive_demo():
    """Runs a live end-to-end simulation of traffic flow, congestion, and rerouting."""
    print("\n" + "=" * 65)
    print("      INTERACTIVE SDN DYNAMIC REROUTING DEMO")
    print("=" * 65)
    print("Topology: H1, H3 -> S1 -> [Path A (10M) / Path B (10M)] -> S4 -> H2, H4")
    print("Main Traffic: H1 -> H2 @ 6.0 Mbps UDP")
    print("Cross Traffic Burst: H3 -> H4 @ 7.0 Mbps UDP (Starts at T=5s)")
    print("SDN Controller: Dynamic OpenFlow 1.3 monitoring & rerouting")
    print("-" * 65)

    from src.sdn_controller import SDNController
    from src.network_emulator import NetworkEmulator
    from src.udp_receiver import UDPReceiver
    from src.udp_sender import UDPSender
    from src.congestion_generator import CongestionGenerator
    from src.protocol import FLOW_MAIN

    # Initialize components
    controller = SDNController(congestion_threshold_mbps=CONGESTION_THRESHOLD_MBPS, adaptive_routing_enabled=True)
    controller.start()

    emulator = NetworkEmulator(controller=controller, ingress_port=9000)
    emulator.start()

    receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=MAIN_UDP_PORT)
    receiver.start()

    cross_receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=CROSS_UDP_PORT)
    cross_receiver.start()

    time.sleep(0.5)

    print("[+] Starting Main UDP Stream (H1 -> H2)...")
    sender = UDPSender(
        target_ip="127.0.0.1",
        target_port=9000,
        rate_mbps=MAIN_TRAFFIC_RATE_MBPS,
        duration=22.0,
        flow_id=FLOW_MAIN
    )
    sender.start()

    import threading
    def inject():
        gen = CongestionGenerator(
            target_ip="127.0.0.1",
            target_port=9000,
            rate_mbps=CROSS_TRAFFIC_RATE_MBPS,
            start_delay=5.0,
            duration=9.0
        )
        gen.run()

    inj_thread = threading.Thread(target=inject, daemon=True)
    inj_thread.start()

    start_time = time.time()
    try:
        while time.time() - start_time < 23.0:
            time.sleep(1.0)
            elapsed = time.time() - start_time
            stats = receiver.get_latest_stats()
            status = controller.get_controller_status()

            print(
                f"[LIVE MONITOR] T={elapsed:>4.1f}s | "
                f"Active: {status['active_path']} | "
                f"Path-A Load: {status['path_a_load_mbps']:>4.1f} Mbps | "
                f"Throughput: {stats['throughput_mbps']:>5.2f} Mbps | "
                f"Loss: {stats['loss_pct']:>4.1f}% | "
                f"Jitter: {stats['jitter_ms']:>4.2f}ms"
            )
    except KeyboardInterrupt:
        print("\n[*] Demo interrupted by user.")
    finally:
        sender.stop()
        inj_thread.join(timeout=1.0)
        cross_receiver.stop()
        receiver.stop()
        emulator.stop()
        controller.stop()

    print("\n" + "=" * 65)
    print("                 DEMO SUMMARY & OUTCOME")
    print("=" * 65)
    final_stats = receiver.get_latest_stats()
    ctrl_stats = controller.get_controller_status()
    print(f"Total Packets Sent      : {sender.packets_sent}")
    print(f"Total Packets Received  : {final_stats['total_received']}")
    print(f"Total Packets Lost      : {final_stats['total_lost']} ({final_stats['overall_loss_pct']}%)")
    print(f"Total Reroutes Triggered: {ctrl_stats['total_reroutes']}")
    if ctrl_stats['latest_recovery_time_sec']:
        print(f"Measured Recovery Time  : {ctrl_stats['latest_recovery_time_sec'] * 1000:.2f} ms")
    print("=" * 65)


def run_benchmark_mode():
    """Executes the automated comparison between static and dynamic routing."""
    from src.benchmark import run_benchmark
    run_benchmark()


def run_mininet_mode():
    """Launches the Mininet topology (Linux only)."""
    if platform.system().lower() != "linux":
        print("[!] Mininet requires a Linux environment (Ubuntu VM or WSL2).")
        print("[!] You can run the interactive simulation mode directly on this machine!")
        return

    topo_path = os.path.join(BASE_DIR, "src", "topology_loader.py")
    is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
    cmd = ["python3", topo_path, "--cli"] if is_root else ["sudo", "python3", topo_path, "--cli"]
    subprocess.call(cmd)


def run_test_suite():
    """Runs pytest unit and system integration tests."""
    print("\n[*] Executing Test Suite...")
    subprocess.call([sys.executable, "-m", "pytest", "-v", os.path.join(BASE_DIR, "tests")])


def show_rubric_mapping():
    """Displays project mapping against evaluation criteria."""
    mapping = """
=============================================================================
                 PROJECT RUBRIC & DELIVERABLES MAPPING
=============================================================================
D1: Initial Deliverables (15 Marks)
  [2 Marks] Problem Understanding & Architecture:
            - Multi-path diamond topology (S1->S2->S4 vs S1->S3->S4)
            - Telemetry-driven SDN closed-loop congestion mitigation.
  [4 Marks] TCP/UDP Socket Implementation:
            - src/protocol.py: Custom 22-byte binary datagram protocol.
            - src/udp_sender.py: High-precision rate pacing & sequence tracking.
            - src/udp_receiver.py: Sequence checking, RFC 3550 jitter, latency.
  [4 Marks] Mininet + SDN Implementation:
            - src/topology_loader.py: Custom .toponet loader with Mininet translation.
            - src/sdn_controller.py: OpenFlow 1.3 FlowMod dispatcher.
            - src/ryu_controller.py: Ryu OpenFlow 1.3 controller application.
  [3 Marks] Socket-SDN Integration:
            - End-to-end integration: link saturation triggers dynamic FlowMod.
  [2 Marks] Initial Testing & Demo:
            - tests/test_system.py: automated pytest validation suite.

D2: Advanced Deliverables (25 Marks)
  [4 Marks] Complete Application Functionality:
            - Multiple flows (Main H1->H2, Cross H3->H4, Probes).
  [6 Marks] Dynamic SDN Functionality:
            - Telemetry polling (0.5s), threshold detection (>8.0 Mbps),
              hysteresis recovery (<4.5 Mbps), and automatic failover.
  [4 Marks] Challenging Scenario / Robustness:
            - 13 Mbps burst across 10 Mbps link -> bufferbloat & drop stress.
  [5 Marks] Performance Evaluation & Comparison:
            - src/benchmark.py: Side-by-side Static vs Dynamic comparison.
            - evaluation_results.png: 4-panel publication-quality plots.
  [6 Marks] Documentation, Final Demo & Viva:
            - README.md: Comprehensive setup & reproduction guide.
            - study1.md, study2.md, study3.md: Subsystem architectural guides.
            - viva1.md, viva2.md, viva3.md: Step-by-step demo guides & viva Q&A.
=============================================================================
    """
    print(mapping)


def interactive_menu():
    while True:
        print_banner()
        print("Please select an option:")
        print("  [1] Run Interactive SDN Congestion & Dynamic Rerouting Demo")
        print("  [2] Run Comparative Benchmark (Static vs Dynamic) & Generate Plots")
        print("  [3] Launch Mininet Multi-Path Network Topology (Ubuntu VM / Linux)")
        print("  [4] Run UDP Sender Tool Manually")
        print("  [5] Run UDP Receiver Tool Manually")
        print("  [6] Run Cross-Traffic Congestion Injector Manually")
        print("  [7] Run Automated Unit & System Test Suite")
        print("  [8] View Project Architecture & Rubric Mapping")
        print("  [9] Exit")
        print("-" * 65)

        choice = input("Enter choice [1-9]: ").strip()
        if choice == "1":
            run_interactive_demo()
        elif choice == "2":
            run_benchmark_mode()
        elif choice == "3":
            run_mininet_mode()
        elif choice == "4":
            target = input("Target IP [127.0.0.1]: ").strip() or "127.0.0.1"
            port = int(input("Target Port [9999]: ").strip() or "9999")
            rate = float(input("Transmission Rate in Mbps [6.0]: ").strip() or "6.0")
            dur = float(input("Duration in seconds [10.0]: ").strip() or "10.0")
            subprocess.call([
                sys.executable, os.path.join(BASE_DIR, "src", "udp_sender.py"),
                "--target", target, "--port", str(port), "--rate", str(rate), "--duration", str(dur)
            ])
        elif choice == "5":
            port = int(input("Listen UDP Port [9999]: ").strip() or "9999")
            subprocess.call([
                sys.executable, os.path.join(BASE_DIR, "src", "udp_receiver.py"),
                "--port", str(port)
            ])
        elif choice == "6":
            rate = float(input("Burst rate in Mbps [7.0]: ").strip() or "7.0")
            dur = float(input("Burst duration in seconds [10.0]: ").strip() or "10.0")
            subprocess.call([
                sys.executable, os.path.join(BASE_DIR, "src", "congestion_generator.py"),
                "--rate", str(rate), "--duration", str(dur)
            ])
        elif choice == "7":
            run_test_suite()
        elif choice == "8":
            show_rubric_mapping()
        elif choice == "9":
            print("\nExiting. Thank you!")
            break
        else:
            print("[!] Invalid option. Please select 1-9.")

        input("\nPress Enter to return to main menu...")


def run_packet_monitor():
    """Listens for real-time packet transmissions and displays them live in the terminal."""
    import socket
    from src.config import TELEMETRY_MONITOR_PORT

    print("\n" + "=" * 75)
    print("      REAL-TIME SDN PACKET & DATA TRANSFER TERMINAL MONITOR")
    print("=" * 75)
    print(f"[*] Binding listener to 127.0.0.1:{TELEMETRY_MONITOR_PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", TELEMETRY_MONITOR_PORT))
    except OSError as e:
        print(f"[!] Could not bind to port {TELEMETRY_MONITOR_PORT}: {e}")
        return

    print("[+] Connected! Streaming real-time packet transmissions, queue depths, and SDN reroutes...")
    print("    [Press Ctrl+C to stop monitor]\n" + "-" * 75)
    try:
        while True:
            data, _ = sock.recvfrom(4096)
            line = data.decode(errors="replace")
            # ANSI colored terminal output
            if "DROPPED" in line:
                print(f"\033[91m{line}\033[0m")
            elif "Path-B" in line:
                print(f"\033[96m{line}\033[0m")
            elif "CONGESTION" in line or "FlowMod" in line:
                print(f"\033[93m{line}\033[0m")
            else:
                print(f"\033[92m{line}\033[0m")
    except KeyboardInterrupt:
        print("\n[*] Packet monitor terminated.")
    finally:
        sock.close()


def launch_gui_dashboard():
    """Launches the master PyQt6 Graphical User Interface."""
    try:
        from src.gui_app import main as run_gui
        print("[+] Launching Master PyQt6 GUI Dashboard...")
        run_gui()
    except Exception as e:
        print(f"[!] Could not launch GUI ({e}). Falling back to interactive CLI menu...")
        interactive_menu()


def main():
    parser = argparse.ArgumentParser(description="SDN Congestion Detection and Dynamic Rerouting Launcher")
    parser.add_argument("--gui", action="store_true", help="Launch PyQt6 Graphical User Interface (Default)")
    parser.add_argument("--cli", action="store_true", help="Launch interactive CLI menu instead of GUI")
    parser.add_argument("--demo", action="store_true", help="Run interactive dynamic rerouting terminal demo")
    parser.add_argument("--monitor", action="store_true", help="Launch real-time packet stream terminal monitor")
    parser.add_argument("--benchmark", action="store_true", help="Run comparative benchmark and generate plots")
    parser.add_argument("--mininet", action="store_true", help="Launch Mininet topology (Linux only)")
    parser.add_argument("--test", action="store_true", help="Run test suite")
    args = parser.parse_args()

    if args.cli:
        interactive_menu()
    elif args.monitor:
        run_packet_monitor()
    elif args.demo:
        run_interactive_demo()
    elif args.benchmark:
        run_benchmark_mode()
    elif args.mininet:
        run_mininet_mode()
    elif args.test:
        run_test_suite()
    else:
        # Default behavior: Launch the full Graphical User Interface!
        launch_gui_dashboard()


if __name__ == "__main__":
    main()
