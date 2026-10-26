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
        MAIN_UDP_PORT, CROSS_UDP_PORT, PATH_PRIMARY, PATH_ALTERNATE,
        TELEMETRY_MONITOR_PORT
    )
    from src.sdn_controller import SDNController
except ImportError:
    from protocol import unpack_packet, InvalidPacketError, FLOW_MAIN, FLOW_CROSS
    from config import (
        LINK_CAPACITY_MBPS, PATH_A_DELAY_MS, PATH_B_DELAY_MS,
        MAIN_UDP_PORT, CROSS_UDP_PORT, PATH_PRIMARY, PATH_ALTERNATE,
        TELEMETRY_MONITOR_PORT
    )
    from sdn_controller import SDNController


class SimulatedLink:
    """
    Models a physical network link with bandwidth limits, queueing, and delay.
    Uses token-bucket rate shaping to avoid OS sleep quantization artifacts.
    """

    def __init__(self, name: str, capacity_mbps: float, delay_ms: float, max_queue: int = 100):
        self.name = name
        self.capacity_mbps = float(capacity_mbps)
        self.delay_sec = delay_ms / 1000.0
        self.max_queue = int(max_queue)

        self.packet_queue = queue.Queue(maxsize=self.max_queue)
        self.tx_bytes = 0
        self.rx_bytes = 0
        self.dropped_packets = 0
        self.forward_handler = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # Precalculate rate-limiter constants
        self._burst_depth_sec = 0.02  # 20ms burst allowance
        self._bytes_per_sec = (self.capacity_mbps * 1_000_000.0) / 8.0
        self._max_tokens = max(16384.0, self._bytes_per_sec * self._burst_depth_sec)

    def set_max_queue(self, new_limit: int):
        """Dynamically adjusts the queue buffer limit."""
        with self._lock:
            self.max_queue = max(10, min(100, int(new_limit)))

    def set_capacity_mbps(self, new_capacity: float):
        """Dynamically adjusts the link bandwidth capacity."""
        with self._lock:
            self.capacity_mbps = max(1.0, min(20.0, float(new_capacity)))
            self._bytes_per_sec = (self.capacity_mbps * 1_000_000.0) / 8.0
            self._max_tokens = max(16384.0, self._bytes_per_sec * self._burst_depth_sec)

    def start(self, forward_handler):
        self.forward_handler = forward_handler
        self._running = True
        self._thread = threading.Thread(target=self._drain_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def enqueue(self, packet_bytes: bytes, destination_addr) -> bool:
        self.rx_bytes += len(packet_bytes)
        # Enforce drop-tail queue buffer limit
        if self.packet_queue.qsize() >= self.max_queue:
            self.dropped_packets += 1
            return False
        try:
            self.packet_queue.put_nowait((packet_bytes, destination_addr, time.time()))
            return True
        except queue.Full:
            self.dropped_packets += 1
            return False

    def _drain_loop(self):
        last_token_time = time.perf_counter()
        tokens = max(16384.0, (self.capacity_mbps * 1_000_000.0 / 8.0) * self._burst_depth_sec)

        while self._running:
            try:
                pkt_data, dest, enq_time = self.packet_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            pkt_len = len(pkt_data)

            # 1. Propagation delay emulation: packet cannot leave before (enq_time + delay_sec)
            target_delivery = enq_time + self.delay_sec
            wait_for_flight = target_delivery - time.time()
            if wait_for_flight > 0.001:
                time.sleep(wait_for_flight)

            # 2. Token-bucket bandwidth limiter (dynamically computed for immediate slider responsiveness)
            with self._lock:
                bps = (self.capacity_mbps * 1_000_000.0) / 8.0
                max_tok = max(16384.0, bps * self._burst_depth_sec)

            now = time.perf_counter()
            delta = now - last_token_time
            last_token_time = now
            tokens = min(max_tok, tokens + delta * bps)

            if tokens < pkt_len:
                needed = (pkt_len - tokens) / bps
                if needed > 0.0005:
                    time.sleep(needed)
                tokens = 0.0
                last_token_time = time.perf_counter()
            else:
                tokens -= pkt_len

            self.tx_bytes += pkt_len

            # Deliver packet to receiver
            if self.forward_handler:
                self.forward_handler(pkt_data, dest)


class NetworkEmulator:
    """
    Simulates the SDN Diamond topology using real UDP sockets and virtual switches.
    Ingress proxy listens on local ports and forwards through simulated links.
    """

    def __init__(
        self,
        controller: SDNController,
        ingress_port: int = 9000,
        main_dest_port: int = MAIN_UDP_PORT,
        cross_dest_port: int = CROSS_UDP_PORT
    ):
        self.controller = controller
        self.ingress_port = ingress_port
        self.main_dest_port = main_dest_port
        self.cross_dest_port = cross_dest_port
        self._running = False
        self._sock = None
        self._out_sock = None
        self._relay_thread = None
        self.packet_callbacks = []
        self._monitor_sock = None

        # Build virtual links for Path A and Path B
        self.link_path_a = SimulatedLink("Path-A (S1->S2->S4)", capacity_mbps=LINK_CAPACITY_MBPS, delay_ms=PATH_A_DELAY_MS)
        self.link_path_b = SimulatedLink("Path-B (S1->S3->S4)", capacity_mbps=LINK_CAPACITY_MBPS, delay_ms=PATH_B_DELAY_MS)

    def apply_topology(self, topo):
        """Applies link and path parameters from a loaded TopologyDefinition."""
        path_a_info = topo.get_path("path_a")
        path_b_info = topo.get_path("path_b")

        if path_a_info:
            cap_a = float(path_a_info.get("capacity_mbps", 10.0))
            delay_a = float(path_a_info.get("delay_ms", 5.0))
            q_a = int(path_a_info.get("queue_limit", 100))
            self.link_path_a.set_capacity_mbps(cap_a)
            self.link_path_a.delay_sec = delay_a / 1000.0
            self.link_path_a.set_max_queue(q_a)

        if path_b_info:
            cap_b = float(path_b_info.get("capacity_mbps", 10.0))
            delay_b = float(path_b_info.get("delay_ms", 15.0))
            q_b = int(path_b_info.get("queue_limit", 100))
            self.link_path_b.set_capacity_mbps(cap_b)
            self.link_path_b.delay_sec = delay_b / 1000.0
            self.link_path_b.set_max_queue(q_b)

    def register_packet_callback(self, cb):
        """Registers a callback function to receive packet transmission events."""
        if cb not in self.packet_callbacks:
            self.packet_callbacks.append(cb)

    def unregister_packet_callback(self, cb):
        """Unregisters a previously registered packet callback function."""
        if cb in self.packet_callbacks:
            self.packet_callbacks.remove(cb)

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self.ingress_port))

        self._out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            self._monitor_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except OSError:
            self._monitor_sock = None

        # Wire link egress directly to the local destination sockets (H2 or H4)
        def forward_to_dest(data, dest):
            try:
                self._out_sock.sendto(data, dest)
            except (ConnectionResetError, ConnectionRefusedError):
                try:
                    self._out_sock.close()
                except OSError:
                    pass
                self._out_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    self._out_sock.sendto(data, dest)
                except OSError:
                    pass
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
        if self._monitor_sock:
            try:
                self._monitor_sock.close()
            except OSError:
                pass
            self._monitor_sock = None

    def _dispatch_packet_event(self, seq: int, flow_id: int, size: int, active_link: SimulatedLink, is_forwarded: bool):
        now_str = time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
        path_name = "Path-A" if active_link == self.link_path_a else "Path-B"
        flow_name = "MAIN" if flow_id == FLOW_MAIN else "CROSS"
        status = "FORWARDED" if is_forwarded else "DROPPED (Queue Overflow)"
        q_cur = self.link_path_a.packet_queue.qsize()
        q_max = self.link_path_a.max_queue
        evt = {
            "time": now_str,
            "flow": flow_name,
            "flow_id": flow_id,
            "seq": seq,
            "size": size,
            "path": path_name,
            "queue": f"{q_cur}/{q_max}",
            "status": status,
            "is_dropped": not is_forwarded,
            "is_rerouted": (flow_id == FLOW_MAIN and active_link == self.link_path_b)
        }
        for cb in self.packet_callbacks:
            try:
                cb(evt)
            except Exception:
                pass

        if self._monitor_sock:
            try:
                line = f"[{now_str}] [{flow_name} #{seq:>5}] {path_name:>6} | Q:{q_cur:>2}/{q_max} | {status}"
                self._monitor_sock.sendto(line.encode(), ("127.0.0.1", TELEMETRY_MONITOR_PORT))
            except OSError:
                pass

    def _switch_relay_loop(self):
        self._sock.settimeout(0.3)
        last_telemetry = time.time()

        while self._running:
            now = time.time()
            if now - last_telemetry >= 0.25:
                # Feed virtual switch port statistics to controller (offered load to switch ports)
                self.controller.record_external_stats("s1", port_no=2, rx_bytes=self.link_path_a.rx_bytes, tx_bytes=self.link_path_a.rx_bytes)
                self.controller.record_external_stats("s1", port_no=3, rx_bytes=self.link_path_b.rx_bytes, tx_bytes=self.link_path_b.rx_bytes)
                last_telemetry = now

            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionRefusedError):
                continue
            except OSError:
                if not self._running:
                    break
                continue

            try:
                seq, ts, flow_id, flags, payload = unpack_packet(data)
            except InvalidPacketError:
                continue

            # Switch routing table logic
            active_link = None
            dest = None
            if flow_id == FLOW_MAIN:
                dest = ("127.0.0.1", self.main_dest_port)
                # Query controller for current active path
                if self.controller.current_active_path == PATH_PRIMARY:
                    active_link = self.link_path_a
                else:
                    active_link = self.link_path_b

            elif flow_id == FLOW_CROSS:
                dest = ("127.0.0.1", self.cross_dest_port)
                # Cross-traffic always flows through Path A to create congestion
                active_link = self.link_path_a

            if active_link and dest:
                is_forwarded = active_link.enqueue(data, dest)
                self._dispatch_packet_event(seq, flow_id, len(data), active_link, is_forwarded)
