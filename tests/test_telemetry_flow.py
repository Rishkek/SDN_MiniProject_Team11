import time
import pytest
from src.config import MAIN_UDP_PORT, CROSS_UDP_PORT, CONGESTION_THRESHOLD_MBPS
from src.protocol import FLOW_MAIN
from src.sdn_controller import SDNController
from src.network_emulator import NetworkEmulator
from src.udp_sender import UDPSender
from src.udp_receiver import UDPReceiver
from src.congestion_generator import CongestionGenerator
import threading


def test_receiver_thread_and_live_telemetry_pipeline():
    test_ingress = 9150
    test_main_port = 9151
    test_cross_port = 9152
    test_fb_port = 9155

    ctrl = SDNController(congestion_threshold_mbps=CONGESTION_THRESHOLD_MBPS, adaptive_routing_enabled=True)
    ctrl.start()

    em = NetworkEmulator(ctrl, ingress_port=test_ingress)
    # Configure emulator routing for this test
    recv = UDPReceiver(bind_ip="127.0.0.1", bind_port=test_main_port, feedback_target=("127.0.0.1", test_fb_port))
    recv.start()

    cross_recv = UDPReceiver(bind_ip="127.0.0.1", bind_port=test_cross_port)
    cross_recv.start()

    # Wire emulator destination mapping to test ports
    orig_relay = em._switch_relay_loop
    def custom_relay():
        em._sock.settimeout(0.3)
        last_telemetry = time.time()
        while em._running:
            now = time.time()
            if now - last_telemetry >= 0.25:
                em.controller.record_external_stats("s1", port_no=2, rx_bytes=em.link_path_a.rx_bytes, tx_bytes=em.link_path_a.rx_bytes)
                em.controller.record_external_stats("s1", port_no=3, rx_bytes=em.link_path_b.rx_bytes, tx_bytes=em.link_path_b.rx_bytes)
                last_telemetry = now
            try:
                data, addr = em._sock.recvfrom(65535)
            except Exception:
                continue
            from src.protocol import unpack_packet, InvalidPacketError, FLOW_MAIN, FLOW_CROSS
            from src.config import PATH_PRIMARY
            try:
                seq, ts, flow_id, flags, payload = unpack_packet(data)
            except InvalidPacketError:
                continue
            dest = None
            active_link = None
            if flow_id == FLOW_MAIN:
                dest = ("127.0.0.1", test_main_port)
                if em.controller.current_active_path == PATH_PRIMARY:
                    active_link = em.link_path_a
                else:
                    active_link = em.link_path_b
            elif flow_id == FLOW_CROSS:
                dest = ("127.0.0.1", test_cross_port)
                active_link = em.link_path_a
            if active_link and dest:
                is_forwarded = active_link.enqueue(data, dest)
                em._dispatch_packet_event(seq, flow_id, len(data), active_link, is_forwarded)

    em._switch_relay_loop = custom_relay
    em.start()

    try:
        # Step 1: Wait 2.0s with no sender to confirm receiver thread stays alive
        time.sleep(2.0)
        assert recv._thread.is_alive(), "Receiver thread prematurely died from ICMP feedback error!"

        # Step 2: Start sender
        sender = UDPSender(target_ip="127.0.0.1", target_port=test_ingress, rate_mbps=6.0, flow_id=FLOW_MAIN, feedback_port=test_fb_port)
        sender.start()

        time.sleep(2.0)
        st = recv.get_latest_stats()
        ctrl_st = ctrl.get_controller_status()

        assert recv._thread.is_alive(), "Receiver thread died after sender started!"
        assert st["total_received"] > 200, f"Receiver received 0 or too few packets: {st}"
        assert st["throughput_mbps"] > 3.0, f"Receiver throughput is 0 or too low: {st}"
        assert st["avg_latency_ms"] > 0.0, f"Receiver latency is 0: {st}"

        # Step 3: Trigger congestion burst
        gen = CongestionGenerator(target_ip="127.0.0.1", target_port=test_ingress, rate_mbps=7.5, duration=4.0)
        t = threading.Thread(target=gen.run, daemon=True)
        t.start()

        time.sleep(3.0)
        ctrl_st2 = ctrl.get_controller_status()
        st2 = recv.get_latest_stats()

        assert ctrl_st2["total_reroutes"] > 0, "SDN controller failed to trigger dynamic reroute on congestion!"
        assert "Path-B" in ctrl_st2["active_path"], f"Active path was not updated to Path-B: {ctrl_st2}"
        assert st2["total_received"] > st["total_received"], "Packets stopped arriving after reroute!"

    finally:
        sender.stop()
        recv.stop()
        cross_recv.stop()
        em.stop()
        ctrl.stop()
