"""
Unit and System Integration Tests.
Topic 27: SDN Congestion Detection and Dynamic Traffic Rerouting.
"""

import time
import pytest
import socket

from src.protocol import pack_packet, unpack_packet, InvalidPacketError, FLOW_MAIN, FLAG_DATA, make_dummy_payload
from src.udp_sender import UDPSender
from src.udp_receiver import UDPReceiver
from src.sdn_controller import SDNController
from src.config import PATH_PRIMARY, PATH_ALTERNATE


def test_protocol_packing_unpacking():
    seq = 42
    payload = b"Hello SDN OpenFlow"
    pkt = pack_packet(seq_num=seq, flow_id=FLOW_MAIN, flags=FLAG_DATA, payload=payload)
    
    assert len(pkt) > len(payload)
    unpacked_seq, ts, flow, flags, data = unpack_packet(pkt)
    assert unpacked_seq == seq
    assert flow == FLOW_MAIN
    assert flags == FLAG_DATA
    assert data == payload
    assert time.time() - ts < 1.0


def test_invalid_packet_rejection():
    # Less than header size
    with pytest.raises(InvalidPacketError):
        unpack_packet(b"TOO_SHORT")

    # Corrupt magic
    corrupt = b"XXXX" + b"\x00" * 30
    with pytest.raises(InvalidPacketError):
        unpack_packet(corrupt)


def test_udp_socket_direct_communication():
    test_port = 19999
    receiver = UDPReceiver(bind_ip="127.0.0.1", bind_port=test_port)
    receiver.start()
    time.sleep(0.2)

    sender = UDPSender(
        target_ip="127.0.0.1",
        target_port=test_port,
        rate_mbps=5.0,
        packet_size=512,
        duration=1.0
    )
    sender.start()
    time.sleep(1.5)
    sender.stop()
    receiver.stop()

    stats = receiver.get_latest_stats()
    assert stats["total_received"] > 50
    assert stats["total_lost"] == 0
    assert stats["overall_throughput_mbps"] > 1.0


def test_sdn_controller_congestion_detection():
    ctrl = SDNController(congestion_threshold_mbps=8.0, poll_interval=0.1, adaptive_routing_enabled=True)
    ctrl.start()

    assert ctrl.current_active_path == PATH_PRIMARY

    # Inject baseline traffic (5 Mbps - under threshold)
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=0, tx_bytes=0)
    time.sleep(0.12)
    # 5 Mbps = 625,000 bytes/sec -> for 0.12s ~ 75,000 bytes
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=75000, tx_bytes=75000)
    time.sleep(0.15)
    assert ctrl.current_active_path == PATH_PRIMARY

    # Inject congestion burst (12 Mbps - over 8.0 Mbps threshold)
    # 12 Mbps = 1,500,000 bytes/sec -> for 0.15s ~ 225,000 bytes
    prev_tx = 75000
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=prev_tx + 250000, tx_bytes=prev_tx + 250000)
    time.sleep(0.25)
    # Second breach trigger
    prev_tx += 250000
    ctrl.record_external_stats("s1", port_no=2, rx_bytes=prev_tx + 250000, tx_bytes=prev_tx + 250000)
    time.sleep(0.3)

    # Controller should have triggered dynamic reroute to Path B
    assert ctrl.current_active_path == PATH_ALTERNATE
    assert ctrl.total_reroutes >= 1
    assert ctrl.recovery_time_sec is not None

    ctrl.stop()


def test_tcp_congestion_simulation():
    from src.tcp_congestion_sim import TCPCongestionSimulator
    sim = TCPCongestionSimulator(bottleneck_bw_mbps=10.0, queue_limit_packets=50, total_time_sec=10.0)

    tahoe = sim.simulate_tahoe(loss_event_time=4.0)
    reno = sim.simulate_reno(loss_event_time=4.0)
    cubic = sim.simulate_cubic(loss_event_time=4.0)
    sdn = sim.simulate_sdn_rerouted_flow(reroute_time=4.5)

    assert len(tahoe["cwnds"]) > 20
    assert len(reno["cwnds"]) > 20
    assert len(cubic["cwnds"]) > 20
    assert len(sdn["cwnds"]) > 20
    # Tahoe drops to 1 MSS on loss
    assert 1.0 in tahoe["cwnds"]
    # SDN flow sustains high window without collapsing
    assert sdn["final_cwnd"] > tahoe["final_cwnd"]
