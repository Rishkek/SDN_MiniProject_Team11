# SDN-Socket Programming: Viva Defense & Examination Guide
**Project:** Congestion Detection and Dynamic Traffic Rerouting (Topic #27)  
**Protocol:** UDP Socket Programming + OpenFlow 1.3 SDN Controller

---

## 1. Core Networking & Protocol Concepts

### Q1: Why does UDP require SDN-assisted congestion control, whereas TCP does not?
**Answer:**
* **TCP** includes built-in end-to-end transport-layer congestion control algorithms (e.g., AIMD, Reno, Cubic, BBR) utilizing ACK clocks, sequence numbers, and dynamic congestion windows (`cwnd`). When packets are dropped, TCP senders throttle themselves back.
* **UDP** is a connectionless, best-effort datagram protocol with **no flow control, no ACK feedback, and no congestion control**. A UDP sender will transmit packets as fast as its application requests, even if bottleneck queues overflow completely, causing severe packet drops and starving other flows.
* **SDN Solution:** Because UDP endpoints do not adapt, the **SDN Controller acts as an external intelligence layer**. It continuously polls network switch counters, detects bottleneck congestion, and dynamically installs OpenFlow `FlowMod` rules to steer UDP flows to alternate, under-utilized physical paths without modifying the end-host applications.

---

### Q2: What is the packet structure of your custom UDP datagram protocol?
**Answer:**
We designed a 22-byte binary protocol header packed with Python's `struct` module using network byte order (`!` big-endian):
```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Magic "SDN1" (4B)                       |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Sequence Number (4B, unsigned)             |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                    Timestamp (8B, float double)               +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          Flow ID (2B)         |   Flags (1B)  |  Reserved(1B) |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       Payload Length (2B)     |       Payload Data ...        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```
* **Magic Bytes (`SDN1`)**: Validates datagram integrity and prevents malformed packet processing.
* **Sequence Number**: Enables receiver to compute packet loss ($seq_{current} - seq_{expected}$) and detect out-of-order packets.
* **Timestamp**: Enables one-way delay and inter-arrival jitter calculation.
* **Flow ID**: Differentiates main mission-critical traffic (Flow 1) from cross-traffic (Flow 2).
* **Flags**: Signals `START`, `DATA`, `FIN`, or `HEARTBEAT`.

---

### Q3: How is RFC 3550 Inter-Arrival Jitter calculated?
**Answer:**
For packet $i$ arriving at time $R_i$ sent at time $S_i$, the transit time is $D_i = R_i - S_i$. The difference between two consecutive packets $i$ and $j$ is:
$$D(i, j) = |(R_j - S_j) - (R_i - S_i)|$$
The smoothed statistical jitter estimate $J_i$ is updated recursively using a low-pass filter (gain $\alpha = 1/16$):
$$J_i = J_{i-1} + \frac{D(i, j) - J_{i-1}}{16}$$

---

## 2. SDN & OpenFlow Architecture

### Q4: Explain the difference between the Data Plane and Control Plane in this project.
**Answer:**
* **Data Plane (Forwarding):** Implemented by Open vSwitch (`s1`, `s2`, `s3`, `s4`). Switches parse incoming Ethernet/IP/UDP headers, inspect their local OpenFlow flow tables, and forward packets out of matching physical/virtual ports.
* **Control Plane (Intelligence):** Implemented by the **SDN Controller**. The controller does not forward packets itself; instead, it maintains global network visibility by querying switch port telemetry (`OFPPortStatsRequest`), executes the rerouting algorithm, and configures the data plane via `OFPFlowMod` messages.

---

### Q5: How is Congestion Detected? What formula is used?
**Answer:**
Every $\Delta t = 0.5$ seconds, the controller queries the transmitted byte counters ($tx\_bytes$) of switch ports along Path A.
The instantaneous link throughput is calculated as:
$$\text{Throughput (bps)} = \frac{(tx\_bytes_t - tx\_bytes_{t-1}) \times 8}{\Delta t}$$
If $\text{Throughput} \ge \text{CONGESTION\_THRESHOLD}$ ($8.0\text{ Mbps}$ on our $10\text{ Mbps}$ bottleneck link) for $N=2$ consecutive samples:
* A **Congestion Alarm** is triggered.
* The controller identifies the alternate path (Path B) and initiates dynamic rerouting.

---

### Q6: What is Hysteresis and why is it important in traffic rerouting?
**Answer:**
* Without hysteresis, as soon as Flow 1 is rerouted away from Path A, Path A's load drops below the 8.0 Mbps threshold. If the controller immediately switched Flow 1 back, Path A would congest again, causing constant route oscillation (**flapping**).
* **Hysteresis Mechanism:** To prevent route flapping, the controller requires Path A load to drop below a lower stabilization threshold ($\le 4.5\text{ Mbps}$) before considering Path A eligible for normal flow allocation.

---

### Q7: What exact OpenFlow 1.3 message is used to reroute traffic?
**Answer:**
The controller sends an `OFPFlowMod` (Flow Modification) message with `command = OFPFC_ADD` (or `OFPFC_MODIFY`) to ingress switch `s1`:
* **Match criteria:**
  - `eth_type = 0x0800` (IPv4)
  - `ip_proto = 17` (UDP)
  - `nw_src = 10.0.0.1` (H1)
  - `nw_dst = 10.0.0.2` (H2)
  - `tp_dst = 9999` (Main UDP Port)
* **Priority:** `200` (higher than default baseline forwarding rules).
* **Instruction/Action:** `OFPAT_OUTPUT -> Port 3` (connecting to switch `s3` along Path B).
* Because Open vSwitch processes flows based on highest priority first, packets matching this flow immediately exit Port 3 instead of Port 2.

---

## 3. Mininet & Linux Emulation

### Q8: How does Mininet create virtual hosts and links?
**Answer:**
* **Hosts:** Mininet creates isolated Linux **Network Namespaces (`ip netns`)**. Each host has its own private routing table, IP stack, and virtual loopback interface.
* **Links:** Mininet uses Linux **Virtual Ethernet pairs (`veth`)**. One end of the `veth` pair is attached to the host namespace, and the other end is attached to an Open vSwitch bridge.
* **Bandwidth & Delay Limits:** Enforced via Linux Traffic Control (`tc` with `netem` and token bucket filter `tbf`) through Mininet's `TCLink` class.

---

### Q9: What is "Recovery Time" and what was the measured result?
**Answer:**
* **Recovery Time** is the time interval starting from the moment congestion threshold is breached until the SDN controller successfully installs the alternate flow rule and packets begin arriving through Path B.
* In our tests, the recovery time is measured at **$\approx 0.05$ to $0.5$ seconds**, restoring nominal 6.0 Mbps throughput and reducing packet loss from $\sim 55\%$ back to $\sim 0\%$.
