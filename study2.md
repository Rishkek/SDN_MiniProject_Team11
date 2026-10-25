# Study Guide 2: Network Infrastructure, Mininet Data Plane & Linux Traffic Control

## Subsystem 2: Network Infrastructure & Data Plane Virtualization
**Component Focus:** Multi-Path Diamond Topology, Linux Network Namespaces, Open vSwitch (OVS), Traffic Control (`tc`), and Standalone Data Plane Emulation  
**Owned Project Files:**
- [`src/topology.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/topology.py) — Mininet Diamond multi-path topology & OpenFlow bridge configuration
- [`src/network_emulator.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/network_emulator.py) — Standalone pure-Python switch & link emulator with token-bucket shaping
- [`tests/test_system.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/tests/test_system.py) — 12-test automated end-to-end data-plane validation test suite
- [`src/gui_app.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/gui_app.py) (Data Plane Canvas) — Live Diamond Topology visualizer with 60 FPS animated packet dots and queue buffer meter

---

## 1. What This Subsystem Does (Plain English Overview)

While Subsystem 1 creates the cars (the UDP packets) and Subsystem 3 creates the smart traffic signals (the SDN Controller), **Subsystem 2 builds the entire physical road network itself**.

Think of this subsystem as the **highway system and civil engineering department**:
1. **The Diamond Topology:** Lays down the roads and intersections. It creates an Ingress Switch ($S_1$), two parallel mountain passes—**Path A** (short, fast, but narrow road) and **Path B** (longer, scenic bypass road)—and an Egress Switch ($S_4$) that connects to the destination houses ($H_2$ and $H_4$).
2. **Speed Limits and Delays:** Configures realistic physical constraints on each road. Path A has a 5 millisecond travel delay, while Path B has a 15 millisecond travel delay. Both roads have a maximum capacity of 10.0 Mbps.
3. **The Buffer Waiting Room (Queue):** Builds a parking lot (buffer queue) at the entrance of Path A that can hold at most 100 packets. When traffic arrives faster than 10.0 Mbps, cars pile up in this waiting room. Once the 100th spot is full, any new arriving car is shoved off the cliff (**tail drop**).
4. **The Virtual Switch Fabrics:** Manages Open vSwitch bridges that inspect incoming packet headers and switch them from input ports to output ports in nanoseconds.
5. **Cross-Platform Portability:** Provides both the Linux Mininet deployment and a standalone pure-Python data plane emulator so that anyone can test and demonstrate the exact same data-plane physics on Windows, macOS, or unprivileged Linux machines.

---

## 2. Behind the Scenes: How the Technology Works Step-by-Step

### A. The Diamond Multi-Path Topology Layout
The network topology is structured in a classic SDN Diamond configuration:

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

- **Path A (Primary):** $S_1 \rightarrow S_2 \rightarrow S_4$. Delay: **5 ms**. Bottleneck capacity: **10.0 Mbps**.
- **Path B (Alternate / Backup):** $S_1 \rightarrow S_3 \rightarrow S_4$. Delay: **15 ms**. Bottleneck capacity: **10.0 Mbps**.
- **Cross-Traffic Ingress:** Host $H_3$ (10.0.0.3) injects background congestion into Switch $S_1$, targeted at Host $H_4$ (10.0.0.4) through Path A.

---

### B. Mininet Network Virtualization Under the Hood
Many people mistakenly believe Mininet is a virtual machine like VMware or VirtualBox. **It is not.** Mininet is a **process-based network virtualization engine** that runs directly on top of the host Linux kernel.

Here are the three Linux kernel features Mininet uses:

#### 1. Linux Network Namespaces (`ip netns`)
- In Linux, a Network Namespace creates an isolated instance of the network subsystem.
- When Mininet creates host $H_1$, the Linux kernel gives $H_1$ its own private loopback interface, its own routing table, its own ARP cache, and its own private IP address (`10.0.0.1`).
- Programs running inside $H_1$ (such as `udp_sender.py`) are completely blind to the sockets or packets of $H_2$ or the host machine.

#### 2. Virtual Ethernet Pairs (`veth`)
- A `veth` pair is a pair of virtual network interfaces connected by a virtual bidirectional cable.
- Packets sent into one interface instantly pop out of the other interface.
- Mininet plugs one end of the pair (`h1-eth0`) into the $H_1$ network namespace, and plugs the other end (`s1-eth1`) into the Open vSwitch bridge $S_1$.

#### 3. Linux Traffic Control (`tc`) and `TCLink`
Virtual Ethernet pairs inside Linux RAM can transmit data at gigabytes per second. To make the virtual network mimic real physical hardware, Mininet uses **Linux Traffic Control (`tc`)**:
- **Token Bucket Filter (`tbf`):** Enforces the $10.0\text{ Mbps}$ bandwidth ceiling. Tokens accumulate in a bucket at a rate of 10 Mbps. Packets can only leave the link if there are enough tokens.
- **Queue Limits (`max_queue_size=100`):** Sets the FIFO queue buffer depth to exactly 100 packets. When the link is congested and 100 packets are waiting, subsequent packets are dropped (**tail drop**).
- **Network Emulation (`netem`):** Inserts precise kernel-level delay queues ($5\text{ms}$ on Path A, $15\text{ms}$ on Path B).

---

### C. Open vSwitch (OVS) Architecture
Each switch ($S_1, S_2, S_3, S_4$) runs as an Open vSwitch daemon:
- **Kernel Datapath:** Fast-path packet forwarding running directly in kernel space.
- **Flow Table:** An ordered list of matching rules. Every incoming packet is matched against flow rules:
  - Default baseline rule: Forward all general traffic from Port 1 to Port 2 (Path A).
  - SDN Dynamic rule: Forward UDP traffic matching `tp_dst=9999` to Port 3 (Path B).
- **Port Statistics Accounting:** OVS automatically maintains 64-bit hardware counters on every port: `rx_packets`, `rx_bytes`, `tx_packets`, `tx_bytes`, and `tx_errors`. These counters are what the SDN Controller queries to detect congestion!

---

### D. The Standalone Cross-Platform Network Emulator (`src/network_emulator.py`)
Because Mininet requires a native Linux kernel with root permissions, we built a pure-Python, zero-dependency data plane emulator to guarantee 100% portability on Windows and macOS:
1. **Virtual Link Modeling (`SimulatedLink`):**
   - Each link has a bounded FIFO queue (`queue.Queue(maxsize=100)`).
   - Enforces drop-tail queuing: if `packet_queue.qsize() >= 100`, the packet is dropped immediately and `dropped_packets` increments.
2. **Dynamic Token-Bucket Rate Limiter:**
   - Implements a continuous token-bucket algorithm that recalculates byte allowances dynamically at high clock rates without relying on coarse OS sleep timers.
   - When the user drags the Category 2 "Bottleneck BW" slider, `set_capacity_mbps()` instantly updates the token accumulation rate in real time.
3. **Switch Relay Loop (`_switch_relay_loop`):**
   - Binds to an ingress socket, receives datagrams, extracts the flow ID, queries the SDN Controller's active path decision, and enqueues the packet into either `link_path_a` or `link_path_b`.
   - Records port byte counters and feeds them to the SDN Controller, mirroring real OpenFlow switch behavior.

---

## 3. How Subsystem 2 Complements the Other Two Subsystems

```
[Subsystem 1: UDP Endpoints]
       |
       | Transmits raw UDP datagrams
       v
[Subsystem 2: Network Infrastructure & Virtual Switches]
       |
       | 1. Accepts packets at Ingress Switch S1
       | 2. Enforces 10 Mbps bandwidth ceiling and 100-packet buffer limits
       | 3. Drops excess packets when load exceeds capacity (physical tail drop)
       | 4. Exposes port byte counters (tx_bytes) on Switch S1
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

1. **Complementing Subsystem 1 (UDP Sockets):**
   - Subsystem 1 needs physical links and queues to travel across. Subsystem 2 provides the virtual switches, links, and realistic bottleneck constraints.
   - When Subsystem 1 pumps 13 Mbps of combined traffic into a 10 Mbps link, Subsystem 2's queue buffer saturates and creates the physical packet drops that Subsystem 1's receiver detects.
2. **Complementing Subsystem 3 (SDN Controller):**
   - The SDN Controller cannot make decisions without data. Subsystem 2's switches record transmitted bytes on every port, providing the telemetry data Subsystem 3 needs.
   - When Subsystem 3 issues a `FlowMod` command, Subsystem 2 executes that command inside the switch forwarding table, moving packets from Port 2 to Port 3 in under 3 milliseconds.

---

## 4. Key Libraries & Why They Were Chosen

| Library / Module | Purpose in Subsystem 2 | Technical Justification |
| :--- | :--- | :--- |
| **`mininet.topo.Topo`** | Defines the nodes, switches, and links of the multi-path topology in Python. | Standard academic and industry standard for OpenFlow and SDN topology modeling. |
| **`mininet.link.TCLink`** | Applies Linux Traffic Control (`tc`) bandwidth limits, queue depths, and delays. | Uses native Linux kernel traffic shapers (`tbf` and `netem`) for hardware-accurate physics. |
| **`openvswitch-switch`** | Virtual software switch running OpenFlow 1.3 protocol engines. | Production-grade software switch used in real cloud datacenters (OpenStack, Kubernetes). |
| **`queue.Queue`** | Thread-safe FIFO queue buffer in the standalone emulator. | Thread-safe, bounded memory structure that perfectly simulates hardware drop-tail queue limits. |
| **`PyQt6`** | Canvas rendering for the live interactive Diamond Topology widget. | Renders vector graphics with subpixel antialiasing at 60 FPS, with dynamically scaling node coordinates. |
