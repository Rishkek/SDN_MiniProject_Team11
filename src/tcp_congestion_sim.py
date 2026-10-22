"""
Transport-Layer Congestion Control Simulator (TCP Tahoe, Reno, Cubic).
Topic 27: SDN Congestion Mitigation & Transport Layer Comparison.

Implements standard algorithmic models:
1. TCP Tahoe: Slow Start, Congestion Avoidance, Drop to 1 on loss.
2. TCP Reno: Slow Start, Congestion Avoidance, Fast Retransmit / Fast Recovery (halving cwnd).
3. TCP CUBIC (RFC 8312): Cubic growth function W_cubic(t) = C*(t - K)^3 + W_max.
4. SDN-Assisted Flow: Shows how SDN dynamic rerouting prevents cwnd collapse!
"""

import math
from typing import Dict, List, Tuple, Any


class TCPCongestionSimulator:
    """
    Simulates CWND dynamics over time (in RTTs / seconds)
    under bottleneck buffer constraints.
    """

    def __init__(
        self,
        bottleneck_bw_mbps: float = 10.0,
        rtt_sec: float = 0.05,            # 50 ms RTT
        mss_bytes: int = 1460,             # Standard Ethernet MSS
        queue_limit_packets: int = 50,     # Buffer depth
        total_time_sec: float = 20.0
    ):
        self.bottleneck_bw_mbps = bottleneck_bw_mbps
        self.rtt_sec = rtt_sec
        self.mss_bytes = mss_bytes
        self.queue_limit_packets = queue_limit_packets
        self.total_time_sec = total_time_sec

        # Bandwidth-Delay Product (BDP) in packets:
        # BDP = (Bandwidth * RTT) / MSS
        bdp_bits = (bottleneck_bw_mbps * 1_000_000.0) * rtt_sec
        self.bdp_packets = max(2, int(bdp_bits / (mss_bytes * 8)))
        # Total link capacity before drop = BDP + Queue limit
        self.pipe_capacity = self.bdp_packets + self.queue_limit_packets

    def simulate_tahoe(self, loss_event_time: float = 8.0) -> Dict[str, Any]:
        """
        Simulates TCP Tahoe:
        - Exponential slow start
        - Linear congestion avoidance
        - On loss: ssthresh = cwnd / 2; cwnd = 1 MSS (Full reset)
        """
        times = []
        cwnds = []
        states = []
        ssthresh_list = []

        cwnd = 1.0
        ssthresh = 32.0
        state = "Slow Start"
        t = 0.0
        dt = self.rtt_sec

        while t <= self.total_time_sec:
            times.append(round(t, 3))
            cwnds.append(round(cwnd, 2))
            ssthresh_list.append(round(ssthresh, 2))
            states.append(state)

            # Check if pipe capacity exceeded or scheduled loss event
            is_congested = (cwnd >= self.pipe_capacity) or (loss_event_time <= t < loss_event_time + 0.1)

            if is_congested:
                # Tahoe packet loss reaction
                ssthresh = max(2.0, cwnd / 2.0)
                cwnd = 1.0  # Reset to 1 MSS
                state = "Slow Start (Drop to 1)"
            else:
                if cwnd < ssthresh:
                    # Slow start: exponential doubling per RTT
                    cwnd = cwnd + 1.0
                    state = "Slow Start"
                else:
                    # Congestion avoidance: additive increase (+1 per RTT)
                    cwnd = cwnd + (1.0 / cwnd)
                    state = "Congestion Avoidance"

            t += dt

        return {
            "protocol": "TCP Tahoe",
            "times": times,
            "cwnds": cwnds,
            "ssthresh": ssthresh_list,
            "states": states,
            "final_cwnd": cwnds[-1]
        }

    def simulate_reno(self, loss_event_time: float = 8.0) -> Dict[str, Any]:
        """
        Simulates TCP Reno:
        - Exponential slow start
        - Linear congestion avoidance
        - On 3 Duplicate ACKs (Fast Retransmit / Fast Recovery):
          ssthresh = cwnd / 2; cwnd = ssthresh (Halves window instead of 1)
        """
        times = []
        cwnds = []
        states = []
        ssthresh_list = []

        cwnd = 1.0
        ssthresh = 32.0
        state = "Slow Start"
        t = 0.0
        dt = self.rtt_sec

        while t <= self.total_time_sec:
            times.append(round(t, 3))
            cwnds.append(round(cwnd, 2))
            ssthresh_list.append(round(ssthresh, 2))
            states.append(state)

            is_congested = (cwnd >= self.pipe_capacity) or (loss_event_time <= t < loss_event_time + 0.1)

            if is_congested:
                # Reno Fast Recovery: cut to half
                ssthresh = max(2.0, cwnd / 2.0)
                cwnd = ssthresh  # Fast Recovery
                state = "Fast Recovery (Halved)"
            else:
                if cwnd < ssthresh:
                    cwnd = cwnd + 1.0
                    state = "Slow Start"
                else:
                    cwnd = cwnd + (1.0 / cwnd)
                    state = "Congestion Avoidance"

            t += dt

        return {
            "protocol": "TCP Reno",
            "times": times,
            "cwnds": cwnds,
            "ssthresh": ssthresh_list,
            "states": states,
            "final_cwnd": cwnds[-1]
        }

    def simulate_cubic(self, loss_event_time: float = 8.0) -> Dict[str, Any]:
        """
        Simulates TCP CUBIC (RFC 8312 - Linux default):
        - Multiplicative decrease factor beta = 0.7
        - Scaling factor C = 0.4
        - W_cubic(t) = C * (t - K)^3 + W_max
        - Where K = cuberoot(W_max * beta / C)
        """
        times = []
        cwnds = []
        states = []
        ssthresh_list = []

        C = 0.4
        beta = 0.3  # Multiplicative decrease of 30% (retains 70%)
        w_max = 32.0
        k_time = math.pow((w_max * beta) / C, 1.0 / 3.0)
        t_epoch = 0.0

        cwnd = 1.0
        ssthresh = 32.0
        state = "Slow Start"
        t = 0.0
        dt = self.rtt_sec

        while t <= self.total_time_sec:
            times.append(round(t, 3))
            cwnds.append(round(cwnd, 2))
            ssthresh_list.append(round(ssthresh, 2))
            states.append(state)

            is_congested = (cwnd >= self.pipe_capacity) or (loss_event_time <= t < loss_event_time + 0.1)

            if is_congested:
                w_max = cwnd
                ssthresh = max(2.0, cwnd * 0.7)
                cwnd = ssthresh
                t_epoch = t
                k_time = math.pow((w_max * beta) / C, 1.0 / 3.0)
                state = "CUBIC Backoff (30% drop)"
            else:
                if cwnd < ssthresh:
                    cwnd = cwnd + 1.0
                    state = "Slow Start"
                else:
                    # Cubic growth function
                    time_since_epoch = t - t_epoch
                    w_target = C * math.pow(time_since_epoch - k_time, 3.0) + w_max
                    increment = max(0.05, (w_target - cwnd) / max(1.0, cwnd))
                    cwnd += min(2.0, increment)
                    if time_since_epoch < k_time:
                        state = "CUBIC Convex Probing"
                    else:
                        state = "CUBIC Aggressive Growth"

            t += dt

        return {
            "protocol": "TCP CUBIC",
            "times": times,
            "cwnds": cwnds,
            "ssthresh": ssthresh_list,
            "states": states,
            "final_cwnd": cwnds[-1]
        }

    def simulate_sdn_rerouted_flow(self, reroute_time: float = 8.5) -> Dict[str, Any]:
        """
        Simulates an intelligent SDN-managed flow:
        Before packet loss occurs at the bottleneck, the SDN controller detects
        port queue growth and switches to Path B.
        Result: CWND DOES NOT COLLAPSE! Continuous peak throughput.
        """
        times = []
        cwnds = []
        states = []
        ssthresh_list = []

        cwnd = 1.0
        ssthresh = 40.0
        state = "Slow Start"
        t = 0.0
        dt = self.rtt_sec

        while t <= self.total_time_sec:
            times.append(round(t, 3))
            cwnds.append(round(cwnd, 2))
            ssthresh_list.append(round(ssthresh, 2))
            states.append(state)

            if t >= reroute_time:
                # SDN Dynamic Reroute: Bottleneck avoided!
                # Pipe capacity effectively doubles or moves to clean link
                effective_cap = self.pipe_capacity * 1.5
                state = "SDN Rerouted (Loss Averted)"
            else:
                effective_cap = self.pipe_capacity

            if cwnd >= effective_cap:
                # Saturation reached on new path
                cwnd = effective_cap
            else:
                if cwnd < ssthresh:
                    cwnd = cwnd + 1.0
                else:
                    cwnd = cwnd + (1.0 / cwnd)

            t += dt

        return {
            "protocol": "SDN Dynamic Reroute (UDP/TCP Managed)",
            "times": times,
            "cwnds": cwnds,
            "ssthresh": ssthresh_list,
            "states": states,
            "final_cwnd": cwnds[-1]
        }
