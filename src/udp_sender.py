"""
Low-Level UDP Socket Sender with Rate Control and Sequence Tracking.
Topic 27: Congestion Detection and Traffic Rerouting.
"""

import socket
import time
import argparse
import threading
import sys
from collections import deque
from typing import Optional, Deque

try:
    from src.protocol import (
        pack_packet, make_dummy_payload, unpack_packet, unpack_feedback,
        FLOW_MAIN, FLAG_DATA, FLAG_START, FLAG_FIN, FLAG_FEEDBACK
    )
    from src.config import DEFAULT_PACKET_SIZE, MAIN_TRAFFIC_RATE_MBPS
except ImportError:
    from protocol import (
        pack_packet, make_dummy_payload, unpack_packet, unpack_feedback,
        FLOW_MAIN, FLAG_DATA, FLAG_START, FLAG_FIN, FLAG_FEEDBACK
    )
    from config import DEFAULT_PACKET_SIZE, MAIN_TRAFFIC_RATE_MBPS


class UDPSender:
    """
    High-precision rate-controlled UDP socket sender.
    Encapsulates sequence numbers, timestamps, and flow IDs.
    """

    def __init__(
        self,
        target_ip: str,
        target_port: int,
        rate_mbps: float = MAIN_TRAFFIC_RATE_MBPS,
        packet_size: int = DEFAULT_PACKET_SIZE,
        flow_id: int = FLOW_MAIN,
        duration: Optional[float] = None,
        enable_rate_adaptation: bool = False,
        min_rate_mbps: float = 1.5,
        feedback_port: Optional[int] = None
    ):
        self.target_ip = target_ip
        self.target_port = target_port
        self.rate_mbps = float(rate_mbps)
        self.configured_rate_mbps = float(rate_mbps)
        self.min_rate_mbps = float(min_rate_mbps)
        self.packet_size = int(packet_size)
        self.flow_id = int(flow_id)
        self.duration = duration
        self.enable_rate_adaptation = enable_rate_adaptation
        self.feedback_port = feedback_port

        # Internal state
        self._sock: Optional[socket.socket] = None
        self._feedback_sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._feedback_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.packets_sent = 0
        self.bytes_sent = 0
        self.start_time = 0.0
        self.stop_time = 0.0
        self.rate_adaptation_events: Deque = deque(maxlen=200)
        self._last_adaptation_time = 0.0
        self._packet_interval = (self.packet_size * 8.0) / (max(0.5, self.rate_mbps) * 1_000_000.0)

        # Precompute payload to avoid allocation overhead in tight loop
        self._payload = make_dummy_payload(self.packet_size)

    def set_rate(self, new_rate_mbps: float):
        """Dynamically adjusts target transmission rate in Mbps."""
        with self._lock:
            old_rate = self.rate_mbps
            self.rate_mbps = max(self.min_rate_mbps, min(12.0, float(new_rate_mbps)))
            self._packet_interval = (self.packet_size * 8.0) / (max(0.5, self.rate_mbps) * 1_000_000.0)
            if abs(old_rate - self.rate_mbps) > 0.05:
                self.rate_adaptation_events.append({
                    "timestamp": time.time(),
                    "old_rate": old_rate,
                    "new_rate": self.rate_mbps,
                    "reason": "Operator / Adaptation adjustment"
                })

    def handle_feedback(self, loss_pct: float, throughput_mbps: float, latency_ms: float):
        """
        Applies application-level rate adaptation policy:
        - Severe congestion (loss > 5%): Multiplicative decrease (-30%)
        - Mild congestion (loss between 2-5%): Cautious decrease (-15%)
        - Clean network (loss < 1%): Additive increase (+0.5 Mbps up to configured limit)
        Hysteresis hold interval: 1.0 second.
        """
        if not self.enable_rate_adaptation:
            return

        now = time.time()
        with self._lock:
            if now - self._last_adaptation_time < 1.0:
                return  # Prevent rapid oscillation

            old_rate = self.rate_mbps
            if loss_pct > 5.0:
                # Multiplicative decrease
                new_rate = max(self.min_rate_mbps, self.rate_mbps * 0.70)
                reason = f"Severe loss ({loss_pct:.1f}%) -> Multiplicative decrease (-30%)"
            elif loss_pct > 2.0:
                new_rate = max(self.min_rate_mbps, self.rate_mbps * 0.85)
                reason = f"Moderate loss ({loss_pct:.1f}%) -> Cautious decrease (-15%)"
            elif loss_pct < 1.0 and self.rate_mbps < self.configured_rate_mbps:
                # Additive increase
                new_rate = min(self.configured_rate_mbps, self.rate_mbps + 0.50)
                reason = f"Clean channel (loss {loss_pct:.1f}%) -> Additive probe (+0.5 Mbps)"
            else:
                return

            if abs(new_rate - old_rate) > 0.1:
                self.rate_mbps = round(new_rate, 2)
                self._packet_interval = (self.packet_size * 8.0) / (max(0.5, self.rate_mbps) * 1_000_000.0)
                self._last_adaptation_time = now
                self.rate_adaptation_events.append({
                    "timestamp": round(now - (self.start_time or now), 2),
                    "old_rate": round(old_rate, 2),
                    "new_rate": round(self.rate_mbps, 2),
                    "loss_pct": round(loss_pct, 1),
                    "reason": reason
                })

    def _setup_socket(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Increase send buffer to prevent OS-level drop before transmission
        try:
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
        except OSError:
            pass

        if self.feedback_port:
            try:
                self._feedback_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._feedback_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._feedback_sock.bind(("0.0.0.0", self.feedback_port))
                self._feedback_sock.settimeout(0.5)
            except OSError:
                self._feedback_sock = None

    def start(self):
        """Starts the sender thread and optional feedback listener."""
        self._setup_socket()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        if self._feedback_sock:
            self._feedback_thread = threading.Thread(target=self._feedback_loop, daemon=True)
            self._feedback_thread.start()

    def stop(self):
        """Signals the sender to stop and sends FIN packet."""
        if not self._running:
            return
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        if self._feedback_thread and self._feedback_thread.is_alive():
            self._feedback_thread.join(timeout=1.0)
        
        # Send FIN packet if socket still open
        if self._sock:
            try:
                fin_pkt = pack_packet(
                    seq_num=self.packets_sent,
                    flow_id=self.flow_id,
                    flags=FLAG_FIN,
                    payload=b"FIN"
                )
                self._sock.sendto(fin_pkt, (self.target_ip, self.target_port))
                self._sock.close()
            except OSError:
                pass
            self._sock = None

        if self._feedback_sock:
            try:
                self._feedback_sock.close()
            except OSError:
                pass
            self._feedback_sock = None

    def _feedback_loop(self):
        """Receives feedback control datagrams from receiver or controller."""
        while self._running:
            if not self._feedback_sock:
                break
            try:
                data, _ = self._feedback_sock.recvfrom(2048)
                seq_num, send_time, flow_id, flags, payload = unpack_packet(data)
                if flags == FLAG_FEEDBACK:
                    loss_pct, thpt, lat, _ = unpack_feedback(payload)
                    self.handle_feedback(loss_pct, thpt, lat)
            except (socket.timeout, OSError):
                continue

    def _run_loop(self):
        self.packets_sent = 0
        self.bytes_sent = 0
        self.start_time = time.time()

        # Send START packet
        start_pkt = pack_packet(
            seq_num=0,
            flow_id=self.flow_id,
            flags=FLAG_START,
            payload=b"START"
        )
        try:
            self._sock.sendto(start_pkt, (self.target_ip, self.target_port))
            self.packets_sent += 1
            self.bytes_sent += len(start_pkt)
        except OSError as e:
            print(f"[Sender Error] Failed sending START: {e}", file=sys.stderr)
            return

        next_send_time = time.perf_counter()

        while self._running:
            current_clock = time.time()
            if self.duration and (current_clock - self.start_time) >= self.duration:
                break

            data_pkt = pack_packet(
                seq_num=self.packets_sent,
                flow_id=self.flow_id,
                flags=FLAG_DATA,
                payload=self._payload
            )

            try:
                self._sock.sendto(data_pkt, (self.target_ip, self.target_port))
                self.packets_sent += 1
                self.bytes_sent += len(data_pkt)
            except (ConnectionResetError, ConnectionRefusedError):
                continue
            except OSError as e:
                if not self._running:
                    break
                continue

            # Precise rate pacing interval (cached, updated only on rate changes)
            next_send_time += self._packet_interval
            sleep_duration = next_send_time - time.perf_counter()
            if sleep_duration > 0.0005:
                time.sleep(sleep_duration)
            elif sleep_duration < -0.05:
                # We are lagging behind by >50ms, resync clock
                next_send_time = time.perf_counter()

        self.stop_time = time.time()
        self._running = False

    def get_stats(self):
        """Returns instantaneous sender statistics."""
        now = self.stop_time if not self._running and self.stop_time > 0 else time.time()
        elapsed = max(0.001, now - (self.start_time or now))
        throughput_mbps = (self.bytes_sent * 8.0) / (elapsed * 1_000_000.0)
        with self._lock:
            cur_rate = self.rate_mbps
            events = list(self.rate_adaptation_events)
        return {
            "flow_id": self.flow_id,
            "packets_sent": self.packets_sent,
            "bytes_sent": self.bytes_sent,
            "elapsed_sec": round(elapsed, 2),
            "throughput_mbps": round(throughput_mbps, 3),
            "current_rate_mbps": round(cur_rate, 2),
            "adaptation_events": events,
            "is_running": self._running
        }


def main():
    parser = argparse.ArgumentParser(description="Low-Level UDP Socket Traffic Generator")
    parser.add_argument("--target", default="127.0.0.1", help="Target IP address")
    parser.add_argument("--port", type=int, default=9999, help="Target UDP port")
    parser.add_argument("--rate", type=float, default=6.0, help="Target rate in Mbps")
    parser.add_argument("--size", type=int, default=1024, help="Packet size in bytes")
    parser.add_argument("--duration", type=float, default=10.0, help="Duration in seconds")
    parser.add_argument("--flow-id", type=int, default=FLOW_MAIN, help="Flow ID (1=Main, 2=Cross)")

    args = parser.parse_args()

    print(f"[*] Starting UDP Sender -> {args.target}:{args.port} | Rate: {args.rate} Mbps | Duration: {args.duration}s")
    sender = UDPSender(
        target_ip=args.target,
        target_port=args.port,
        rate_mbps=args.rate,
        packet_size=args.size,
        flow_id=args.flow_id,
        duration=args.duration
    )
    sender.start()

    try:
        while sender._running:
            time.sleep(1.0)
            stats = sender.get_stats()
            print(f"[Sender] Elapsed: {stats['elapsed_sec']}s | Sent: {stats['packets_sent']} pkts | Speed: {stats['throughput_mbps']} Mbps")
    except KeyboardInterrupt:
        print("\n[*] Stopping sender on user interrupt...")
    finally:
        sender.stop()

    final_stats = sender.get_stats()
    print("\n=== Final Sender Statistics ===")
    print(f"Total Packets Sent : {final_stats['packets_sent']}")
    print(f"Total Bytes Sent   : {final_stats['bytes_sent']:,} bytes")
    print(f"Total Duration     : {final_stats['elapsed_sec']} s")
    print(f"Average Throughput : {final_stats['throughput_mbps']} Mbps")


if __name__ == "__main__":
    main()
