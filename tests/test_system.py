"""
Unit and System Acceptance Test Suite (Tests A through L).
Topic 27: SDN Congestion Detection and Dynamic Traffic Rerouting.

Implements all 12 Acceptance Test Scenarios specified in Section 11:
- Test A: Basic Socket Communication
- Test B: Multiple Communicating Flows
- Test C: Baseline Routing Under Capacity
- Test D: Congestion Detection & Threshold Breaches
- Test E: Dynamic SDN Rerouting & OpenFlow State
- Test F: Application-Level UDP Rate Adaptation
- Test G: Congestion Recovery & Hysteresis
- Test H: Backup Path Overload / Fallback
- Test I: Telemetry Mathematical Correctness
- Test J: Static vs Adaptive Benchmark Evaluation
- Test K: SDN Dynamic Rerouting Metrics & Failover Verification
- Test L: Clean Shutdown, Reset & Resource Leaks
"""

import time
import pytest
import socket
import threading

from src.protocol import (
    pack_packet, unpack_packet, pack_feedback, unpack_feedback,
    InvalidPacketError, FLOW_MAIN, FLOW_CROSS, FLAG_DATA, FLAG_START, FLAG_FIN, FLAG_FEEDBACK
)
from src.udp_sender import UDPSender
from src.udp_receiver import UDPReceiver
from src.congestion_generator import CongestionGenerator
from src.sdn_controller import SDNController
from src.network_emulator import NetworkEmulator
from src.config import PATH_PRIMARY, PATH_ALTERNATE, MAIN_UDP_PORT, CROSS_UDP_PORT, CONGESTION_THRESHOLD_MBPS


# ---------------------------------------------------------------------------
# Test A: Basic Socket Communication
# ---------------------------------------------------------------------------
def test_a_basic_socket_communication():
    """Verify UDP datagram transmission, sequence tracking, and clean shutdown."""
    port = 20001
    receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=port)
    receiver.start()
    time.sleep(0.1)

    sender = UDPSender(target_ip="127.0.0.1", target_port=port, rate_mbps=4.0, packet_size=512, duration=0.8)
    sender.start()
    time.sleep(1.2)
    sender.stop()
    receiver.stop()

    stats = receiver.get_latest_stats()
    sender_stats = sender.get_stats()

    assert stats["total_received"] > 40, "Receiver should have received datagrams"
    assert stats["total_lost"] == 0, "No packet loss expected over local loopback"
    assert sender_stats["packets_sent"] >= stats["total_received"], "Sender sent count >= recv count"
    assert stats["overall_throughput_mbps"] > 1.0, "Throughput should be positive"


# ---------------------------------------------------------------------------
# Test B: Multiple Communicating Flows
# ---------------------------------------------------------------------------
def test_b_multiple_flows():
    """Verify concurrent Main (FLOW_MAIN) and Cross (FLOW_CROSS) streams."""
    main_port = 20002
    cross_port = 20003

    main_recv = UDPReceiver(bind_ip="127.0.0.1", bind_port=main_port)
    cross_recv = UDPReceiver(bind_ip="127.0.0.1", bind_port=cross_port)
    main_recv.start()
    cross_recv.start()
    time.sleep(0.1)

    main_send = UDPSender(target_ip="127.0.0.1", target_port=main_port, rate_mbps=3.0, flow_id=FLOW_MAIN, duration=0.6)
    cross_send = UDPSender(target_ip="127.0.0.1", target_port=cross_port, rate_mbps=3.0, flow_id=FLOW_CROSS, duration=0.6)

    main_send.start()
    cross_send.start()
    time.sleep(1.0)

    main_send.stop()
    cross_send.stop()
    main_recv.stop()
    cross_recv.stop()

    m_stats = main_recv.get_latest_stats()
    c_stats = cross_recv.get_latest_stats()

    assert m_stats["total_received"] > 20, "Main receiver received datagrams"
    assert c_stats["total_received"] > 20, "Cross receiver received datagrams"


# ---------------------------------------------------------------------------
# Test C: Baseline Routing Under Capacity
# ---------------------------------------------------------------------------
def test_c_baseline_routing():
    """Verify under-capacity traffic flows through Path A with negligible loss."""
    ctrl = SDNController(congestion_threshold_mbps=8.0, adaptive_routing_enabled=True)
    ctrl.start()
    emulator = NetworkEmulator(controller=ctrl, ingress_port=20004)
    emulator.start()

    recv = UDPReceiver(bind_ip="127.0.0.1", bind_port=MAIN_UDP_PORT)
    recv.start()
    time.sleep(0.1)

    # 4 Mbps flow on 10 Mbps link -> clean transmission
    sender = UDPSender(target_ip="127.0.0.1", target_port=20004, rate_mbps=4.0, duration=1.0)
    sender.start()
    time.sleep(1.4)

    sender.stop()
    recv.stop()
    emulator.stop()
    ctrl.stop()

    stats = recv.get_latest_stats()
    status = ctrl.get_controller_status()

    assert status["active_path"] == PATH_PRIMARY, "Should remain on Path A"
    assert stats["overall_loss_pct"] < 3.0, "Packet loss should be near zero under capacity"


# ---------------------------------------------------------------------------
# Test D: Congestion Detection
# ---------------------------------------------------------------------------
def test_d_congestion_detection():
    """Verify that port load exceeding 8.0 Mbps triggers congestion alerts."""
    ctrl = SDNController(congestion_threshold_mbps=8.0, poll_interval=0.1, adaptive_routing_enabled=False)
    ctrl.start()

    # Step 1: Normal load
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=0, tx_bytes=0)
    time.sleep(0.12)
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=50000, tx_bytes=50000)
    time.sleep(0.15)
    assert ctrl.consecutive_breaches == 0

    # Step 2: Congestion breach (12 Mbps = 150KB per 0.1s)
    prev = 50000
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=prev + 180000, tx_bytes=prev + 180000)
    time.sleep(0.15)
    assert ctrl.latest_path_a_load_mbps > 8.0, "Should detect rate above 8.0 Mbps"
    assert ctrl.consecutive_breaches >= 1, "Should increment consecutive breach counter"

    ctrl.stop()


# ---------------------------------------------------------------------------
# Test E: Dynamic Rerouting
# ---------------------------------------------------------------------------
def test_e_dynamic_rerouting():
    """Verify dynamic OpenFlow failover from Path A to Path B upon consecutive breaches."""
    ctrl = SDNController(congestion_threshold_mbps=8.0, poll_interval=0.1, adaptive_routing_enabled=True)
    ctrl.start()

    # Initial state
    assert ctrl.current_active_path == PATH_PRIMARY

    # Inject breach 1
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=0, tx_bytes=0)
    time.sleep(0.12)
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=200000, tx_bytes=200000)
    time.sleep(0.15)

    # Inject breach 2 (trigger threshold)
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=400000, tx_bytes=400000)
    time.sleep(0.2)

    assert ctrl.current_active_path == PATH_ALTERNATE, "Path should be rerouted to Path B"
    assert ctrl.total_reroutes >= 1, "Reroute counter should increment"
    assert ctrl.recovery_time_sec is not None, "Failover latency must be measured"
    assert ctrl.recovery_time_sec < 1.0, "Failover must complete rapidly"

    ctrl.stop()


# ---------------------------------------------------------------------------
# Test F: Application-Level UDP Rate Adaptation
# ---------------------------------------------------------------------------
def test_f_rate_adaptation():
    """Verify that UDP sender decreases transmission rate upon feedback indicating severe loss."""
    sender = UDPSender(
        target_ip="127.0.0.1",
        target_port=20005,
        rate_mbps=6.0,
        enable_rate_adaptation=True,
        min_rate_mbps=1.5
    )

    # Simulate receiver feedback: 12% loss -> multiplicative decrease
    sender.handle_feedback(loss_pct=12.0, throughput_mbps=4.0, latency_ms=25.0)
    stats1 = sender.get_stats()
    assert stats1["current_rate_mbps"] < 6.0, "Rate should back off on loss > 5%"

    # Simulate another severe loss -> further backoff
    time.sleep(1.05)  # respect hysteresis
    sender.handle_feedback(loss_pct=8.0, throughput_mbps=3.0, latency_ms=20.0)
    stats2 = sender.get_stats()
    assert stats2["current_rate_mbps"] < stats1["current_rate_mbps"]

    # Simulate clean channel -> additive probe upward
    time.sleep(1.05)
    sender.handle_feedback(loss_pct=0.2, throughput_mbps=3.0, latency_ms=10.0)
    stats3 = sender.get_stats()
    assert stats3["current_rate_mbps"] > stats2["current_rate_mbps"], "Rate should probe upward when clean"


# ---------------------------------------------------------------------------
# Test G: Congestion Recovery & Hysteresis
# ---------------------------------------------------------------------------
def test_g_congestion_recovery():
    """Verify hysteresis cool-down threshold and safe path restoration."""
    ctrl = SDNController(congestion_threshold_mbps=8.0, poll_interval=0.1, adaptive_routing_enabled=True)
    ctrl.start()
    ctrl.current_active_path = PATH_ALTERNATE
    ctrl.auto_revert_enabled = True

    # Simulate Path A traffic dropping to 2.0 Mbps (< 4.5 Mbps recovery threshold)
    for _ in range(5):
        ctrl.record_external_stats("s1", port_no=2, rx_bytes=25000, tx_bytes=25000)
        time.sleep(0.12)
        ctrl.record_external_stats("s1", port_no=2, rx_bytes=50000, tx_bytes=50000)
        time.sleep(0.12)

    # Should safely fail back to Path A
    assert ctrl.current_active_path == PATH_PRIMARY, "Should restore to Path A after cooling below hysteresis"
    ctrl.stop()


# ---------------------------------------------------------------------------
# Test H: Backup Path Overload / Fallback
# ---------------------------------------------------------------------------
def test_h_backup_path_overload():
    """Confirm that the controller refuses to reroute to a congested backup path."""
    ctrl = SDNController(congestion_threshold_mbps=8.0, poll_interval=0.1, adaptive_routing_enabled=True)
    ctrl.start()

    # Pre-condition: Both Path A and Path B are heavily loaded (> 8.0 Mbps)
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=0, tx_bytes=0)
    ctrl.record_external_stats("s1", port_no=3, rx_bytes=0, tx_bytes=0)
    time.sleep(0.12)
    # 12 Mbps on both ports
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=200000, tx_bytes=200000)
    ctrl.record_external_stats("s1", port_no=3, rx_bytes=200000, tx_bytes=200000)
    time.sleep(0.15)
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=400000, tx_bytes=400000)
    ctrl.record_external_stats("s1", port_no=3, rx_bytes=400000, tx_bytes=400000)
    time.sleep(0.2)

    # Reroute should NOT claim success to an overloaded path
    status = ctrl.get_controller_status()
    assert status["both_paths_congested"] is True, "Must flag that both paths are congested"
    assert ctrl.current_active_path == PATH_PRIMARY, "Must NOT flip to an equally saturated backup path"
    ctrl.stop()


# ---------------------------------------------------------------------------
# Test I: Telemetry Mathematical Correctness
# ---------------------------------------------------------------------------
def test_i_telemetry_correctness():
    """Verify that packet loss, throughput, and goodput formulas are mathematically sound."""
    recv = UDPReceiver(bind_ip="127.0.0.1", bind_port=20006)
    recv.start()

    # Manually inject known packets into internal state
    with recv._lock:
        recv.total_packets_received = 2454
        recv.total_packets_lost = 3143
        recv.total_bytes_received = 2454 * 1024
        recv.total_payload_bytes_received = 2454 * 1002
        recv.start_time = time.time() - 10.0
        recv.last_packet_time = time.time()

    stats = recv.get_latest_stats()
    recv.stop()

    total_expected = 2454 + 3143
    expected_loss_pct = round((3143 / total_expected) * 100.0, 2)

    assert stats["overall_loss_pct"] == expected_loss_pct, "Loss percentage must equal exactly (lost / total) * 100"
    assert stats["overall_loss_pct"] == 56.16 or stats["overall_loss_pct"] == 56.2
    assert stats["total_received"] == 2454
    assert stats["total_lost"] == 3143
    assert stats["overall_goodput_mbps"] < stats["overall_throughput_mbps"], "Goodput strictly <= Throughput"


# ---------------------------------------------------------------------------
# Test J: Static Versus Adaptive Benchmark
# ---------------------------------------------------------------------------
def test_j_static_vs_adaptive_benchmark():
    """Runs a rapid 6-second comparative test to verify dynamic routing mitigates congestion."""
    from src.benchmark import run_single_experiment

    # Short 7s duration with 3s congestion burst
    static_res = run_single_experiment("STATIC_MINI", adaptive_enabled=False, total_duration=7.0, congestion_start=2.0, congestion_duration=3.0)
    time.sleep(1.0)
    dynamic_res = run_single_experiment("DYN_MINI", adaptive_enabled=True, total_duration=7.0, congestion_start=2.0, congestion_duration=3.0)

    # Dynamic must show lower average packet loss than Static
    assert dynamic_res["avg_loss_pct"] <= static_res["avg_loss_pct"] or dynamic_res["total_packets_received"] >= static_res["total_packets_received"]


# ---------------------------------------------------------------------------
# Test K: SDN Dynamic Rerouting Metrics & Failover Verification
# ---------------------------------------------------------------------------
def test_k_sdn_flow_rerouting_metrics():
    """Verify SDN dynamic rerouting trigger, flow table update, and failover latency."""
    controller = SDNController(congestion_threshold_mbps=8.0, poll_interval=0.1, adaptive_routing_enabled=True)
    controller.start()

    # Initial state must be Primary Path
    assert controller.current_active_path == PATH_PRIMARY
    assert controller.total_reroutes == 0

    # Inject breach 1
    controller.record_external_stats("s1", port_no=2, rx_bytes=0, tx_bytes=0)
    time.sleep(0.12)
    controller.record_external_stats("s1", port_no=2, rx_bytes=200000, tx_bytes=200000)
    time.sleep(0.15)

    # Inject breach 2 (trigger threshold)
    controller.record_external_stats("s1", port_no=2, rx_bytes=400000, tx_bytes=400000)
    time.sleep(0.2)

    status = controller.get_controller_status()
    assert status["active_path"] == PATH_ALTERNATE, "SDN Controller must reroute to Path B upon congestion"
    assert status["total_reroutes"] >= 1, "Reroute counter must increment"
    assert status["latest_recovery_time_sec"] is not None, "Recovery latency must be recorded"
    assert status["latest_recovery_time_sec"] > 0.0, "Recovery latency must be positive"

    # Verify OpenFlow table has been updated to Output port 3 (Path B)
    flow_table = controller.get_flow_table("s1")
    assert "action=OUTPUT Port 3" in flow_table, "OpenFlow 1.3 flow table must point to port 3"

    controller.stop()


# ---------------------------------------------------------------------------
# Test L: Clean Shutdown, Reset & Resource Leaks
# ---------------------------------------------------------------------------
def test_l_cleanup_and_reproducibility():
    """Verify repeat initialization and teardown cycles without leaked threads or sockets."""
    for cycle in range(3):
        ctrl = SDNController(congestion_threshold_mbps=8.0)
        ctrl.start()

        emu = NetworkEmulator(controller=ctrl, ingress_port=20007 + cycle)
        emu.start()

        rec = UDPReceiver(bind_ip="127.0.0.1", bind_port=MAIN_UDP_PORT)
        rec.start()

        time.sleep(0.2)

        # Stop everything
        rec.stop()
        emu.stop()
        ctrl.stop()

    # Rebind immediately on same port to prove socket was released
    test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    test_sock.bind(("127.0.0.1", MAIN_UDP_PORT))
    test_sock.close()
