# Study Guide 2: Network Infrastructure, Mininet Data Plane & Linux Traffic Control

**Component Focus:** Multi-Path Diamond Topology, Linux Network Namespaces, Open vSwitch (OVS), Traffic Control (`tc`), Drop-Tail Queue Buffers, and Standalone Data Plane Emulation  
**Owned Project Files:**
- [`src/topology.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/topology.py) — Mininet Diamond multi-path topology & OpenFlow bridge configuration
- [`src/network_emulator.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/network_emulator.py) — Standalone pure-Python switch & link emulator with token-bucket shaping
- [`tests/test_system.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/tests/test_system.py) — 13-test automated end-to-end data-plane validation test suite
- [`src/gui_app.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/gui_app.py) (Data Plane Canvas) — Live Diamond Topology visualizer with 60 FPS animated packet dots, queue buffer meter, and watermark `*D1`

---

# ================================================================
# PART 1: DELIVERABLE 1 (D1 — FOUNDATION - 15 MARKS)
# ================================================================

## 1. What to Explain for Deliverable 1
In Deliverable 1, your role is to explain **how the underlying network roads, switches, and physical constraints are built**:
1. The architecture of the Diamond Multi-Path Topology ($S_1 \rightarrow S_2 / S_3 \rightarrow S_4$).
2. How Mininet virtualizes networks using Linux Network Namespaces (`ip netns`), Virtual Ethernet pairs (`veth`), and Open vSwitch (OVS).
3. How Linux Traffic Control (`tc`) enforces bandwidth limits (10 Mbps), propagation delays (5 ms vs 15 ms), and drop-tail queue limits (100 pkts).
4. How the standalone pure-Python data plane emulator (`src/network_emulator.py`) guarantees 100% functionality on Windows/macOS without root privileges.
5. How the baseline data plane directs normal traffic along Path A.

---

## 2. D1 Behind the Scenes: Data Plane Architecture Step-by-Step

### A. The Classic SDN Diamond Multi-Path Topology Layout
The network connects end-hosts through two physically isolated intermediate routes:

```
              [Host H1: Main Sender] (10.0.0.1)
                         \
                          v  (Port 1)
                     +-----------+
                     | Switch S1 | (Ingress Switch)
                     +-----------+
                     / (Port 2)   \ (Port 3)
                    /              \
                   v                v
            +-----------+      +-----------+
            | Switch S2 |      | Switch S3 |
            | (Path A)  |      | (Path B)  |
            +-----------+      +-----------+
             [Primary]          [Alternate]
             10 Mbps, 5ms       10 Mbps, 15ms
             Queue: 100 pkts    Queue: 100 pkts
                    \              /
                     \            /
                      v          v
                     +-----------+
                     | Switch S4 | (Egress Switch)
                     +-----------+
                          |  (Port 1)
                          v
              [Host H2: Main Receiver] (10.0.0.2)
```

- **Path A (Primary):** $S_1 \rightarrow S_2 \rightarrow S_4$. Propagation Delay: **5 ms**. Bottleneck Bandwidth: **10.0 Mbps**.
- **Path B (Alternate / Backup):** $S_1 \rightarrow S_3 \rightarrow S_4$. Propagation Delay: **15 ms**. Bottleneck Bandwidth: **10.0 Mbps**.
- **Default Baseline State:** Switch $S_1$ forwards all outgoing traffic to Port 2 (Path A), taking advantage of its lower 5 ms delay.

---

### B. Mininet Network Virtualization Under the Hood
Mininet is not a heavy hypervisor (like VMware). It is a **process-based network virtualization engine** running directly on the Linux kernel:

1. **Linux Network Namespaces (`ip netns`):**
   - Each host ($H_1, H_2, H_3, H_4$) runs in an isolated network namespace.
   - Each namespace has its own private routing table, ARP cache, interface list, and loopback adapter.
   - Sockets created inside $H_1$ are completely isolated from $H_2$.
2. **Virtual Ethernet Pairs (`veth`):**
   - Acts as a bidirectional virtual Ethernet cable connecting two endpoints in software.
   - One end is plugged into host interface `h1-eth0`, and the other end is plugged into switch port `s1-eth1`.
3. **Open vSwitch (OVS) Bridges:**
   - Production-grade virtual switches running inside the Linux kernel.
   - Performs wire-speed packet lookup, port-to-port forwarding, and hardware counter maintenance (`rx_bytes`, `tx_bytes`).

---

### C. Linux Traffic Control (`tc`) Link Conditioning
To simulate realistic physical networking constraints on top of gigabit Linux RAM:
- **Token Bucket Filter (`tbf`):** Enforces the 10.0 Mbps bandwidth limit. Tokens accumulate at 10 Mbps. Packets can only be transmitted when sufficient tokens exist.
- **Queue Limits (`max_queue_size=100`):** Sets the switch egress FIFO queue buffer depth to 100 packets.
- **Network Emulation (`netem`):** Injects kernel-level transmission delay: 5 ms on Path A, 15 ms on Path B.

---

### D. Standalone Cross-Platform Data Plane Emulator (`src/network_emulator.py`)
To ensure complete testability and execution on Windows and macOS:
1. **`SimulatedLink` Class:**
   - Implements a thread-safe bounded FIFO queue (`queue.Queue(maxsize=100)`).
   - Simulates wire propagation delay and drop-tail queuing.
2. **Dynamic Token-Bucket Rate Shaper:**
   - Calculates byte allowances using high-precision monotonic clocks, accurately limiting link bandwidth to 10.0 Mbps.
3. **Switch Relay Loop (`_switch_relay_loop`):**
   - Binds to ingress port 9000, receives UDP datagrams, extracts the Flow ID, queries the SDN Controller's active path decision, and forwards to the appropriate link.

---

# ================================================================
# PART 2: DELIVERABLE 2 (D2 — ADVANCED FUNCTIONALITY - 25 MARKS)
# ================================================================

## 1. What to Explain for Deliverable 2
In Deliverable 2, your role is to explain **how the data plane handles severe traffic congestion, executes dynamic SDN rerouting in hardware, and supports real-time network manipulation**:
1. How the switch queue buffer fills to capacity during a 130% traffic burst, causing physical tail-drop packet discards.
2. How Open vSwitch executes an OpenFlow 1.3 `FlowMod` instruction in hardware/kernel datapath to redirect traffic to Path B in $<3\text{ ms}$.
3. How the interactive dynamic sliders modify bottleneck bandwidth (2–10 Mbps) and queue capacity (10–100 pkts) on the fly.
4. How the automated 13-test regression suite (`tests/test_system.py`) verifies data-plane correctness.

---

## 2. D2 Behind the Scenes: Advanced Mechanics Step-by-Step

### A. Queue Buffer Dynamics Under 130% Overload
When Host $H_3$ injects 7.0 Mbps cross traffic into Path A alongside the 6.0 Mbps main flow:
1. Ingress traffic arrives at Switch $S_1$ at **13.0 Mbps**.
2. The bottleneck link shaper drains the queue at only **10.0 Mbps**.
3. Net accumulation rate: $+3.0\text{ Mbps}$ ($\approx 366\text{ packets/second}$).
4. The 100-packet queue buffer completely fills in **$\approx 270\text{ milliseconds}$**.
5. **Tail Drop:** Once the 100th packet is enqueued, all subsequent arriving packets are immediately dropped, creating severe packet loss until the control plane takes action.

---

### B. Open vSwitch Dynamic Flow Reconfiguration
When the SDN Controller issues an OpenFlow 1.3 `OFPFlowMod` instruction:
```python
match = parser.OFPMatch(eth_type=0x0800, ip_proto=17, ipv4_dst="10.0.0.2", udp_dst=9999)
actions = [parser.OFPActionOutput(port=3)] # Path B
# Priority 200 overrides the default Priority 100 baseline rule
```
1. Switch $S_1$ installs the new rule into its local Flow Table.
2. The OVS kernel datapath immediately updates its fast-path cache.
3. The very next packet arriving on Port 1 is directed to **Port 3 (Path B)** instead of Port 2.
4. **Failover Execution Latency:** Measured at **$< 3.0\text{ milliseconds}$** (well below human perception).

---

### C. Live Parameter Manipulation
Through the GUI dashboard controls:
* **Bottleneck Bandwidth Slider (2.0 – 10.0 Mbps):** Calls `set_capacity_mbps()` on the active link, dynamically altering token accumulation rates in real time.
* **Queue Buffer Slider (10 – 100 pkts):** Calls `set_max_queue()`, instantly changing the tail-drop threshold to demonstrate shallow vs deep buffer dynamics.

---

### D. Automated System Test Suite (`tests/test_system.py`)
A comprehensive automated test suite validates all data plane behaviors across 13 distinct tests:
- `test_a_basic_socket_communication`: Verifies socket bind and delivery.
- `test_c_baseline_routing`: Validates 0% loss on clean Path A.
- `test_d_congestion_detection`: Validates switch queue filling under 13 Mbps load.
- `test_e_dynamic_rerouting`: Validates sub-second failover to Path B.
- `test_g_congestion_recovery`: Validates traffic restoration after burst ends.
- `test_k_sdn_flow_rerouting_metrics`: Confirms failover latency $\le 10\text{ ms}$.

---

## 3. How Subsystem 2 Complements the Other Two Subsystems

```
[Subsystem 1: UDP Sockets]
       |
       | Transmits raw UDP datagrams
       v
[Subsystem 2: Network Infrastructure & Virtual Switches]
       |
       | 1. Accepts packets at Ingress Switch S1
       | 2. Enforces 10 Mbps bandwidth limit & 100-packet buffer depth
       | 3. Drops excess packets when load exceeds capacity (tail drop)
       | 4. Exposes hardware port counters (tx_bytes) on Switch S1
       v
[Subsystem 3: SDN Control Plane]
       |
       | 5. Polls switch counters -> detects congestion (> 8.0 Mbps)
       | 6. Sends OpenFlow FlowMod instruction to Switch S1
       v
[Subsystem 2: Switch S1 Forwarding Engine]
       |
       | 7. Reconfigures data plane: redirects packets from Port 2 to Port 3
       v
[Subsystem 1: UDP Receiver]
       |
       | 8. Receives packets over Path B with zero packet loss
```

---

## 4. Key Libraries & Technical Justifications

| Library / Module | Purpose in Subsystem 2 | Technical Justification |
| :--- | :--- | :--- |
| **`mininet.topo.Topo`** | Defines nodes, switches, and links of the multi-path topology in Python. | Standard academic and industry framework for OpenFlow and SDN network modeling. |
| **`mininet.link.TCLink`** | Applies Linux Traffic Control (`tc`) bandwidth limits, queue depths, and delays. | Uses native Linux kernel traffic shapers (`tbf` and `netem`) for hardware-accurate physics. |
| **`openvswitch-switch`** | Virtual software switch running OpenFlow 1.3 protocol engines. | Production-grade software switch used in real cloud datacenters (OpenStack, Kubernetes). |
| **`queue.Queue`** | Thread-safe FIFO queue buffer in the standalone emulator. | Thread-safe, bounded memory structure that perfectly simulates hardware drop-tail queue limits. |
| **`PyQt6`** | Canvas rendering for the live interactive Diamond Topology widget. | Renders vector graphics with subpixel antialiasing at 60 FPS, with dynamically scaling node coordinates. |
