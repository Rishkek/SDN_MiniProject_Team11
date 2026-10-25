"""
Global Configuration for Congestion Detection and Traffic Rerouting.
Topic 27: SDN-Socket Programming.
"""

# Host IP Addresses (Mininet defaults)
HOST_H1_IP = "10.0.0.1"  # Main Traffic Sender
HOST_H2_IP = "10.0.0.2"  # Main Traffic Receiver
HOST_H3_IP = "10.0.0.3"  # Cross-Traffic Congestion Sender
HOST_H4_IP = "10.0.0.4"  # Cross-Traffic Receiver

# UDP Ports
MAIN_UDP_PORT = 9999
CROSS_UDP_PORT = 9998
CONTROLLER_PORT = 6653
CONTROLLER_REST_PORT = 8080
TELEMETRY_MONITOR_PORT = 9010  # Live terminal packet monitor stream

# Network Topology Constraints
LINK_CAPACITY_MBPS = 10.0     # Bottleneck link bandwidth
PATH_A_DELAY_MS = 5           # Primary path delay
PATH_B_DELAY_MS = 15          # Secondary/Alternative path delay
QUEUE_LIMIT_PACKETS = 100     # Queue depth on bottleneck switch ports

# Traffic Generation Settings
DEFAULT_PACKET_SIZE = 1024    # Bytes per packet (including header)
MAIN_TRAFFIC_RATE_MBPS = 6.0  # Main high-priority UDP flow
CROSS_TRAFFIC_RATE_MBPS = 7.0 # Cross-traffic flow (6 + 7 = 13 Mbps > 10 Mbps capacity)

# Congestion Detection Parameters
CONGESTION_THRESHOLD_MBPS = 8.0       # Threshold to trigger rerouting (80% link capacity)
CONGESTION_LOSS_THRESHOLD_PCT = 3.0   # Trigger reroute if loss rate exceeds 3%
HYSTERESIS_RECOVERY_MBPS = 4.5        # Load must drop below this to consider path fully recovered
POLL_INTERVAL_SEC = 0.5               # Telemetry polling frequency
CONSECUTIVE_TRIGGERS_REQUIRED = 2     # Number of consecutive breach intervals before rerouting

# Paths
PATH_PRIMARY = "Path-A (S1 -> S2 -> S4)"
PATH_ALTERNATE = "Path-B (S1 -> S3 -> S4)"
