"""
Cross-Traffic UDP Congestion Injector.
Creates controlled congestion on shared network links to trigger SDN rerouting.
Topic 27: Congestion Detection and Traffic Rerouting.
"""

import time
import argparse
import sys
from typing import Optional

try:
    from src.udp_sender import UDPSender
    from src.protocol import FLOW_CROSS
    from src.config import CROSS_UDP_PORT, CROSS_TRAFFIC_RATE_MBPS, HOST_H4_IP
except ImportError:
    from udp_sender import UDPSender
    from protocol import FLOW_CROSS
    from config import CROSS_UDP_PORT, CROSS_TRAFFIC_RATE_MBPS, HOST_H4_IP


class CongestionGenerator:
    """
    Manages controlled background cross-traffic generation.
    Can inject scheduled traffic bursts to induce network bottleneck saturation.
    """

    def __init__(
        self,
        target_ip: str = HOST_H4_IP,
        target_port: int = CROSS_UDP_PORT,
        rate_mbps: float = CROSS_TRAFFIC_RATE_MBPS,
        start_delay: float = 0.0,
        duration: float = 10.0
    ):
        self.target_ip = target_ip
        self.target_port = target_port
        self.rate_mbps = rate_mbps
        self.start_delay = start_delay
        self.duration = duration
        self.sender: Optional[UDPSender] = None

    def run(self):
        """Waits for start_delay then bursts cross-traffic for duration."""
        if self.start_delay > 0:
            print(f"[Cross-Traffic] Waiting {self.start_delay}s before starting congestion burst...")
            time.sleep(self.start_delay)

        print(f"[!] INJECTING CONGESTION: {self.rate_mbps} Mbps cross-traffic to {self.target_ip}:{self.target_port} for {self.duration}s")
        self.sender = UDPSender(
            target_ip=self.target_ip,
            target_port=self.target_port,
            rate_mbps=self.rate_mbps,
            flow_id=FLOW_CROSS,
            duration=self.duration
        )
        self.sender.start()

        # Wait until finished
        while self.sender._running:
            time.sleep(0.5)

        self.sender.stop()
        stats = self.sender.get_stats()
        print(f"[*] Congestion burst completed. Injected {stats['packets_sent']} packets ({stats['bytes_sent']:,} bytes) at {stats['throughput_mbps']} Mbps.")


def main():
    parser = argparse.ArgumentParser(description="Cross-Traffic Congestion Generator")
    parser.add_argument("--target", default="127.0.0.1", help="Target IP address (H4)")
    parser.add_argument("--port", type=int, default=CROSS_UDP_PORT, help="Target UDP port")
    parser.add_argument("--rate", type=float, default=CROSS_TRAFFIC_RATE_MBPS, help="Burst rate in Mbps")
    parser.add_argument("--delay", type=float, default=0.0, help="Initial delay in seconds")
    parser.add_argument("--duration", type=float, default=10.0, help="Burst duration in seconds")

    args = parser.parse_args()
    gen = CongestionGenerator(
        target_ip=args.target,
        target_port=args.port,
        rate_mbps=args.rate,
        start_delay=args.delay,
        duration=args.duration
    )
    gen.run()


if __name__ == "__main__":
    main()
