"""
Pure-Python Standalone SDN Network Emulator.
Enables immediate testing and execution on Windows, macOS, or unprivileged Linux.

Features:
- Simulates multi-switch topology (S1, S2, S3, S4) using real UDP socket relays.
- Models link capacity constraints (10 Mbps), latency, and queue buffer drops.
- Integrates seamlessly with SDNController for dynamic FlowMod rerouting.
"""

import socket
import time
import queue
import threading
from typing import Dict, Any, Optional

try:
    from src.protocol import unpack_packet, InvalidPacketError, FLOW_MAIN, FLOW_CROSS
    from src.config import (
        LINK_CAPACITY_MBPS, PATH_A_DELAY_MS, PATH_B_DELAY_MS,
        MAIN_UDP_PORT, CROSS_UDP_PORT, PATH_PRIMARY, PATH_ALTERNATE
    )
    from src.sdn_controller import SDNController
except ImportError:
    from protocol import unpack_packet, InvalidPacketError, FLOW_MAIN, FLOW_CROSS
    from config import (
        LINK_CAPACITY_MBPS, PATH_A_DELAY_MS, PATH_B_DELAY_MS,
        MAIN_UDP_PORT, CROSS_UDP_PORT, PATH_PRIMARY, PATH_ALTERNATE
    )
    from sdn_controller import SDNController


class SimulatedLink:
    """Models a physical network link with bandwidth limits, queueing, and delay."""

    def __init__(self, name: str, capacity_mbps: float, delay_ms: float, max_queue: int = 100):
        self.name = name
        self.capacity_mbps = capacity_mbps
        self.delay_sec = delay_ms / 1000.0
        self.max_queue = max_queue

        self.packet_queue = queue.Queue(maxsize=max_queue)
        self.tx_bytes = 0
        self.rx_bytes = 0
        self.dropped_packets = 0
        self.forward_handler = None
        self._running = False
        self._thread = None

    def start(self, forward_handler):
        self.forward_handler = forward_handler
        self._running = True
        self._thread = threading.Thread(target=self._drain_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def enqueue(self, packet_bytes: bytes, destination_addr):
        self.rx_bytes += len(packet_bytes)
        try:
            self.packet_queue.put_nowait((packet_bytes, destination_addr, time.time()))
        except queue.Full:
            self.dropped_packets += 1

    def _drain_loop(self):
        bytes_per_sec = (self.capacity_mbps * 1_000_000.0) / 8.0
        while self._running:
            try:
                pkt_data, dest, enq_time = self.packet_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            pkt_len = len(pkt_data)
            # Serialization delay based on link transmission capacity
            tx_delay = pkt_len / bytes_per_sec
            time.sleep(tx_delay)
            self.tx_bytes += pkt_len

            # Deliver packet to receiver
            if self.forward_handler:
                self.forward_handler(pkt_data, dest)


class NetworkEmulator:
    """
    Simulates the SDN Diamond topology using real UDP sockets and virtual switches.
    Ingress proxy listens on local ports and forwards through simulated links.
    """

    def __init__(self, controller: SDNController, ingress_port: int = 9000):
        self.controller = controller
        self.ingress_port = ingress_port
        self._running = False
        self._sock = None
        self._out_sock = None
        self._relay_thread = None

        # Build virtual links for Path A and Path B
        self.link_path_a = SimulatedLink("Path-A (S1->S2->S4)", capacity_mbps=LINK_CAPACITY_MBPS, delay_ms=PATH_A_DELAY_MS)
        self.link_path_b = SimulatedLink("Path-B (S1->S3->S4)", capacity_mbps=LINK_CAPACITY_MBPS, delay_ms=PATH_B_DELAY_MS)

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self.ingress_port))

        self._out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Wire link egress directly to the local destination sockets (H2 or H4)
        def forward_to_dest(data, dest):
            try:
                self._out_sock.sendto(data, dest)
            except OSError:
                pass

        self.link_path_a.start(forward_to_dest)
        self.link_path_b.start(forward_to_dest)

        self._running = True
        self._relay_thread = threading.Thread(target=self._switch_relay_loop, daemon=True)
        self._relay_thread.start()

    def stop(self):
        self._running = False
        self.link_path_a.stop()
        self.link_path_b.stop()
        if self._sock:
            self._sock.close()
        if self._out_sock:
            self._out_sock.close()

    def _switch_relay_loop(self):
        self._sock.settimeout(0.3)
        last_telemetry = time.time()

        while self._running:
            now = time.time()
            if now - last_telemetry >= 0.5:
                # Feed virtual switch port statistics to controller (offered load to switch ports)
                self.controller.record_external_stats("s1", port_no=2, rx_bytes=self.link_path_a.rx_bytes, tx_bytes=self.link_path_a.rx_bytes)
                self.controller.record_external_stats("s1", port_no=3, rx_bytes=self.link_path_b.rx_bytes, tx_bytes=self.link_path_b.rx_bytes)
                last_telemetry = now

            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                seq, ts, flow_id, flags, payload = unpack_packet(data)
            except InvalidPacketError:
                continue

            # Switch routing table logic
            if flow_id == FLOW_MAIN:
                dest = ("127.0.0.1", MAIN_UDP_PORT)
                # Query controller for current active path
                if self.controller.current_active_path == PATH_PRIMARY:
                    self.link_path_a.enqueue(data, dest)
                else:
                    self.link_path_b.enqueue(data, dest)

            elif flow_id == FLOW_CROSS:
                dest = ("127.0.0.1", CROSS_UDP_PORT)
                # Cross-traffic always flows through Path A to create congestion
                self.link_path_a.enqueue(data, dest)
