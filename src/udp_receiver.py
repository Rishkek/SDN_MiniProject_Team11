"""
High-Performance UDP Socket Receiver with Real-Time Telemetry.
Measures Throughput, Packet Loss, End-to-End Latency, and Jitter.
Topic 27: Congestion Detection and Traffic Rerouting.
"""

import socket
import time
import json
import argparse
import threading
import sys
from collections import deque
from typing import Optional, List, Dict, Any, Deque

try:
    from src.protocol import unpack_packet, pack_feedback, InvalidPacketError, FLAG_START, FLAG_FIN, FLAG_DATA
    from src.config import MAIN_UDP_PORT
except ImportError:
    from protocol import unpack_packet, pack_feedback, InvalidPacketError, FLAG_START, FLAG_FIN, FLAG_DATA
    from config import MAIN_UDP_PORT


class UDPReceiver:
    """
    Multithreaded UDP socket server.
    Captures datagrams, calculates network performance metrics,
    and exposes live telemetry for congestion monitoring.
    """

    def __init__(
        self,
        bind_ip: str = "0.0.0.0",
        bind_port: int = MAIN_UDP_PORT,
        log_file: Optional[str] = None,
        feedback_target: Optional[tuple] = None
    ):
        self.bind_ip = bind_ip
        self.bind_port = bind_port
        self.log_file = log_file
        self.feedback_target = feedback_target  # (ip, port) to send feedback datagrams

        self._sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Cumulative metrics
        self.total_packets_received = 0
        self.total_bytes_received = 0
        self.total_payload_bytes_received = 0
        self.total_packets_lost = 0
        self.out_of_order_packets = 0
        self.expected_seq = 0
        self.start_time = 0.0
        self.last_packet_time = 0.0

        # Jitter calculation state (RFC 3550)
        self.jitter_ms = 0.0
        self.prev_transit_ms = None

        # Latency statistics (Bounded circular ring buffer prevents memory leaks)
        self.latencies_ms: Deque[float] = deque(maxlen=2000)

        # Rolling window telemetry (Bounded circular history prevents memory growth)
        self.history: Deque[Dict[str, Any]] = deque(maxlen=500)
        self._window_bytes = 0
        self._window_payload_bytes = 0
        self._window_lost = 0
        self._window_received = 0
        self._window_latencies: List[float] = []
        self._last_window_time = 0.0
        self._lock = threading.Lock()

    def _setup_socket(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
        except OSError:
            pass
        self._sock.bind((self.bind_ip, self.bind_port))
        self._sock.settimeout(0.5)

    def start(self):
        """Starts the receiver loop in a background thread."""
        self._setup_socket()
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stops the receiver and closes the socket."""
        if not self._running:
            return
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        if self.log_file:
            self.export_history_to_file(self.log_file)

    def _listen_loop(self):
        self.start_time = time.time()
        self._last_window_time = time.time()

        while self._running:
            try:
                data, addr = self._sock.recvfrom(65535)
                recv_time = time.time()
            except socket.timeout:
                self._check_window(time.time())
                continue
            except OSError:
                break

            try:
                seq_num, send_time, flow_id, flags, payload = unpack_packet(data)
            except InvalidPacketError:
                # Ignore non-protocol packets
                continue

            with self._lock:
                pkt_len = len(data)
                payload_len = len(payload)
                self.total_packets_received += 1
                self.total_bytes_received += pkt_len
                self.total_payload_bytes_received += payload_len
                self._window_bytes += pkt_len
                self._window_payload_bytes += payload_len
                self._window_received += 1
                self.last_packet_time = recv_time

                # Latency in milliseconds (sender timestamp vs receiver arrival)
                delay_ms = max(0.0, (recv_time - send_time) * 1000.0)
                # Filter out absurd clock-skew artifacts if clocks are wildly out of sync (> 60s)
                if delay_ms < 60000.0:
                    self.latencies_ms.append(delay_ms)
                    self._window_latencies.append(delay_ms)

                # RFC 3550 Jitter calculation: D(i,j) = (Rj - Sj) - (Ri - Si)
                transit_ms = (recv_time - send_time) * 1000.0
                if self.prev_transit_ms is not None:
                    d = abs(transit_ms - self.prev_transit_ms)
                    self.jitter_ms += (d - self.jitter_ms) / 16.0
                self.prev_transit_ms = transit_ms

                # Sequence checking and loss detection
                if flags == FLAG_START:
                    self.expected_seq = seq_num + 1
                else:
                    if seq_num > self.expected_seq:
                        gap = seq_num - self.expected_seq
                        self.total_packets_lost += gap
                        self._window_lost += gap
                        self.expected_seq = seq_num + 1
                    elif seq_num < self.expected_seq:
                        self.out_of_order_packets += 1
                    else:
                        self.expected_seq += 1

                self._check_window(recv_time)

    def _check_window(self, current_time: float):
        """Flushes rolling interval metrics for graphing and monitoring."""
        delta = current_time - self._last_window_time
        if delta >= 0.5:  # 500ms sliding telemetry window
            total_expected_in_win = self._window_received + self._window_lost
            window_loss_pct = (self._window_lost / total_expected_in_win * 100.0) if total_expected_in_win > 0 else 0.0
            throughput_mbps = (self._window_bytes * 8.0) / (delta * 1_000_000.0)
            goodput_mbps = (self._window_payload_bytes * 8.0) / (delta * 1_000_000.0)
            avg_lat = sum(self._window_latencies) / len(self._window_latencies) if self._window_latencies else 0.0

            total_pkts = self.total_packets_received + self.total_packets_lost
            overall_loss_pct = (self.total_packets_lost / total_pkts * 100.0) if total_pkts > 0 else 0.0

            snapshot = {
                "timestamp": round(current_time - (self.start_time or current_time), 2),
                "throughput_mbps": round(throughput_mbps, 3),
                "goodput_mbps": round(goodput_mbps, 3),
                "loss_pct": round(window_loss_pct, 2),
                "window_loss_pct": round(window_loss_pct, 2),
                "overall_loss_pct": round(overall_loss_pct, 2),
                "avg_latency_ms": round(avg_lat, 2),
                "jitter_ms": round(self.jitter_ms, 2),
                "packets_recv": self.total_packets_received,
                "packets_lost": self.total_packets_lost
            }
            self.history.append(snapshot)

            # Send feedback datagram if feedback channel is active
            if self.feedback_target and self._sock:
                try:
                    suggested_rate = max(1.5, throughput_mbps * (0.75 if window_loss_pct > 3.0 else 1.05))
                    fb = pack_feedback(window_loss_pct, throughput_mbps, avg_lat, suggested_rate)
                    self._sock.sendto(fb, self.feedback_target)
                except OSError:
                    pass

            # Reset window
            self._window_bytes = 0
            self._window_payload_bytes = 0
            self._window_lost = 0
            self._window_received = 0
            self._window_latencies = []
            self._last_window_time = current_time

    def get_latest_stats(self) -> Dict[str, Any]:
        """Thread-safe retrieval of current statistics."""
        with self._lock:
            if self.history:
                latest = dict(self.history[-1])
            else:
                latest = {
                    "timestamp": 0.0,
                    "throughput_mbps": 0.0,
                    "goodput_mbps": 0.0,
                    "loss_pct": 0.0,
                    "window_loss_pct": 0.0,
                    "overall_loss_pct": 0.0,
                    "avg_latency_ms": 0.0,
                    "jitter_ms": 0.0,
                    "packets_recv": self.total_packets_received,
                    "packets_lost": self.total_packets_lost
                }
            latest["total_received"] = self.total_packets_received
            latest["total_lost"] = self.total_packets_lost
            latest["out_of_order"] = self.out_of_order_packets
            total_pkts = self.total_packets_received + self.total_packets_lost
            latest["overall_loss_pct"] = round((self.total_packets_lost / total_pkts * 100.0) if total_pkts > 0 else 0.0, 2)
            latest["window_loss_pct"] = latest.get("loss_pct", 0.0)

            # Cumulative overall throughput & goodput across entire active duration
            now = self.last_packet_time if self.last_packet_time > self.start_time else time.time()
            active_duration = max(0.001, now - (self.start_time or now))
            overall_mbps = (self.total_bytes_received * 8.0) / (active_duration * 1_000_000.0)
            overall_goodput = (self.total_payload_bytes_received * 8.0) / (active_duration * 1_000_000.0)
            latest["overall_throughput_mbps"] = round(overall_mbps, 3)
            latest["overall_goodput_mbps"] = round(overall_goodput, 3)

            return latest

    def export_history_to_file(self, filepath: str):
        """Dumps collected telemetry history into a JSON file."""
        with open(filepath, "w") as f:
            json.dump(list(self.history), f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="High-Performance UDP Socket Receiver")
    parser.add_argument("--ip", default="0.0.0.0", help="IP address to bind")
    parser.add_argument("--port", type=int, default=MAIN_UDP_PORT, help="UDP port to listen on")
    parser.add_argument("--log", default=None, help="Path to save metrics log JSON")

    args = parser.parse_args()

    print(f"[*] Starting UDP Receiver on {args.ip}:{args.port}")
    receiver = UDPReceiver(bind_ip=args.ip, bind_port=args.port, log_file=args.log)
    receiver.start()

    try:
        while True:
            time.sleep(1.0)
            stats = receiver.get_latest_stats()
            print(
                f"[Receiver] T={stats['timestamp']:>4.1f}s | "
                f"Rate: {stats['throughput_mbps']:>5.2f} Mbps | "
                f"Loss: {stats['loss_pct']:>5.1f}% | "
                f"Latency: {stats['avg_latency_ms']:>5.1f}ms | "
                f"Jitter: {stats['jitter_ms']:>4.2f}ms | "
                f"Total Recv: {stats['total_received']}"
            )
    except KeyboardInterrupt:
        print("\n[*] Stopping receiver on user interrupt...")
    finally:
        receiver.stop()

    summary = receiver.get_latest_stats()
    print("\n=== Final Receiver Statistics ===")
    print(f"Total Packets Received : {summary['total_received']}")
    print(f"Total Packets Lost     : {summary['total_lost']}")
    print(f"Overall Packet Loss    : {summary['overall_loss_pct']}%")
    print(f"Out of Order Packets   : {summary['out_of_order']}")


if __name__ == "__main__":
    main()
