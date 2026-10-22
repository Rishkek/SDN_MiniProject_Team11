"""
Mininet Multi-Path Diamond Topology with OpenFlow 1.3.
Topic 27: Congestion Detection and Dynamic Traffic Rerouting.

Topology Diagram:
         [h1: 10.0.0.1] (Sender)
         [h3: 10.0.0.3] (Cross-Traffic)
                \   /
                [s1] (Ingress Switch)
               /    \
 (Path A) 10M /      \ 10M (Path B)
    5ms delay/        \ 15ms delay
           [s2]      [s3]
             \        /
              \      /
                [s4] (Egress Switch)
                /   \
         [h2: 10.0.0.2] (Receiver)
         [h4: 10.0.0.4] (Cross-Traffic Sink)
"""

import sys
import time
import argparse
import subprocess

try:
    from mininet.topo import Topo
    from mininet.net import Mininet
    from mininet.node import RemoteController, OVSKernelSwitch
    from mininet.link import TCLink
    from mininet.cli import CLI
    from mininet.log import setLogLevel, info
    MININET_AVAILABLE = True
except ImportError:
    MININET_AVAILABLE = False

try:
    from src.config import (
        HOST_H1_IP, HOST_H2_IP, HOST_H3_IP, HOST_H4_IP,
        LINK_CAPACITY_MBPS, PATH_A_DELAY_MS, PATH_B_DELAY_MS,
        QUEUE_LIMIT_PACKETS, MAIN_UDP_PORT, CROSS_UDP_PORT
    )
    from src.sdn_controller import SDNController
except ImportError:
    from config import (
        HOST_H1_IP, HOST_H2_IP, HOST_H3_IP, HOST_H4_IP,
        LINK_CAPACITY_MBPS, PATH_A_DELAY_MS, PATH_B_DELAY_MS,
        QUEUE_LIMIT_PACKETS, MAIN_UDP_PORT, CROSS_UDP_PORT
    )
    from sdn_controller import SDNController


if MININET_AVAILABLE:
    class DiamondTopo(Topo):
        """Builds multi-path network topology with bottleneck links."""

        def build(self):
            # Add switches with OpenFlow 1.3 support
            s1 = self.addSwitch("s1", protocols="OpenFlow13")
            s2 = self.addSwitch("s2", protocols="OpenFlow13")
            s3 = self.addSwitch("s3", protocols="OpenFlow13")
            s4 = self.addSwitch("s4", protocols="OpenFlow13")

            # Add hosts
            h1 = self.addHost("h1", ip=f"{HOST_H1_IP}/24", defaultRoute="via 10.0.0.254")
            h2 = self.addHost("h2", ip=f"{HOST_H2_IP}/24", defaultRoute="via 10.0.0.254")
            h3 = self.addHost("h3", ip=f"{HOST_H3_IP}/24", defaultRoute="via 10.0.0.254")
            h4 = self.addHost("h4", ip=f"{HOST_H4_IP}/24", defaultRoute="via 10.0.0.254")

            # Host links (high bandwidth, low delay)
            self.addLink(h1, s1, bw=100, delay="1ms")
            self.addLink(h3, s1, bw=100, delay="1ms")
            self.addLink(s4, h2, bw=100, delay="1ms")
            self.addLink(s4, h4, bw=100, delay="1ms")

            # Bottleneck links: Path A (Primary)
            # Port allocation on s1:
            # Port 1: h1, Port 4: h3, Port 2: s2, Port 3: s3
            self.addLink(
                s1, s2,
                bw=LINK_CAPACITY_MBPS,
                delay=f"{PATH_A_DELAY_MS}ms",
                max_queue_size=QUEUE_LIMIT_PACKETS
            )
            self.addLink(
                s2, s4,
                bw=LINK_CAPACITY_MBPS,
                delay=f"{PATH_A_DELAY_MS}ms",
                max_queue_size=QUEUE_LIMIT_PACKETS
            )

            # Bottleneck links: Path B (Alternative)
            self.addLink(
                s1, s3,
                bw=LINK_CAPACITY_MBPS,
                delay=f"{PATH_B_DELAY_MS}ms",
                max_queue_size=QUEUE_LIMIT_PACKETS
            )
            self.addLink(
                s3, s4,
                bw=LINK_CAPACITY_MBPS,
                delay=f"{PATH_B_DELAY_MS}ms",
                max_queue_size=QUEUE_LIMIT_PACKETS
            )


def setup_ovs_flows():
    """Configures baseline OpenFlow 1.3 rules on OVS switches."""
    info("[*] Configuring baseline OpenFlow 1.3 flow rules on switches...\n")
    # Base forwarding for ARP and IP
    commands = [
        # Normal forwarding for S2, S3, S4
        "ovs-ofctl -O OpenFlow13 add-flow s2 actions=NORMAL",
        "ovs-ofctl -O OpenFlow13 add-flow s3 actions=NORMAL",
        "ovs-ofctl -O OpenFlow13 add-flow s4 actions=NORMAL",

        # Ingress S1 baseline:
        # ARP -> flood
        "ovs-ofctl -O OpenFlow13 add-flow s1 priority=10,dl_type=0x0806,actions=FLOOD",

        # Default UDP traffic h1->h2 routed to Path A (s1-s2: Port 2)
        f"ovs-ofctl -O OpenFlow13 add-flow s1 priority=50,udp,nw_src={HOST_H1_IP},nw_dst={HOST_H2_IP},tp_dst={MAIN_UDP_PORT},actions=output:2",

        # Default UDP cross-traffic h3->h4 routed to Path A (Port 2)
        f"ovs-ofctl -O OpenFlow13 add-flow s1 priority=50,udp,nw_src={HOST_H3_IP},nw_dst={HOST_H4_IP},tp_dst={CROSS_UDP_PORT},actions=output:2",

        # Return traffic & general IP
        "ovs-ofctl -O OpenFlow13 add-flow s1 priority=1,actions=NORMAL"
    ]
    for cmd in commands:
        subprocess.run(cmd.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_mininet_environment(cli_mode: bool = False, run_demo: bool = True):
    """Initializes and runs the Mininet network."""
    if not MININET_AVAILABLE:
        print("[!] Mininet is not available in this environment. Please run inside an Ubuntu VM.")
        return

    setLogLevel("info")
    topo = DiamondTopo()
    net = Mininet(topo=topo, switch=OVSKernelSwitch, link=TCLink, controller=None)
    net.start()

    setup_ovs_flows()

    info("[+] Mininet topology online with 4 switches and 4 hosts.\n")
    info(f"[+] H1: {HOST_H1_IP} | H2: {HOST_H2_IP} | H3: {HOST_H3_IP} | H4: {HOST_H4_IP}\n")

    # Start SDN telemetry monitor
    controller = SDNController()
    controller.start()

    try:
        if cli_mode:
            info("[*] Starting interactive Mininet CLI...\n")
            CLI(net)
        elif run_demo:
            info("[*] Executing automated SDN congestion detection demo in Mininet...\n")
            h1 = net.get("h1")
            h2 = net.get("h2")
            h3 = net.get("h3")
            h4 = net.get("h4")

            # Start receiver on h2
            h2.cmd("python3 src/udp_receiver.py --port 9999 --log /tmp/receiver_metrics.json &")
            time.sleep(1.0)

            # Start main flow on h1
            info("[*] Starting main UDP flow from H1 to H2 (6 Mbps)...\n")
            h1.cmd("python3 src/udp_sender.py --target 10.0.0.2 --port 9999 --rate 6.0 --duration 25 &")

            # Inject cross traffic at t=8s
            time.sleep(8.0)
            info("[!] Saturation cross-traffic injected on Path A (H3 -> H4 at 7 Mbps)...\n")
            h3.cmd("python3 src/congestion_generator.py --target 10.0.0.4 --port 9998 --rate 7.0 --duration 10 &")

            # Wait for completion
            time.sleep(20.0)
            info("[+] Demo run finished.\n")
    finally:
        controller.stop()
        net.stop()
        info("[*] Mininet environment cleaned up successfully.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mininet Topology Launcher")
    parser.add_argument("--cli", action="store_true", help="Launch interactive Mininet CLI")
    parser.add_argument("--demo", action="store_true", help="Run automated Mininet demo")
    args = parser.parse_args()

    if not MININET_AVAILABLE:
        print("Mininet module not found. This script is intended to run inside Ubuntu/Mininet VM.")
        sys.exit(1)

    run_mininet_environment(cli_mode=args.cli, run_demo=args.demo or not args.cli)
