# Study Guide 3: SDN Control Plane, Closed-Loop Telemetry & Dynamic OpenFlow Rerouting

## Subsystem 3: SDN Control Plane, Telemetry & Performance Evaluation
**Component Focus:** OpenFlow 1.3 Controller Architecture, Continuous Telemetry Polling, Congestion Detection, Hysteresis, Dynamic FlowMod Rerouting, and Automated Benchmarking  
**Owned Project Files:**
- [`src/sdn_controller.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/sdn_controller.py) — Core SDN controller, telemetry engine, hysteresis state machine, and flow table manager
- [`src/ryu_controller.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/ryu_controller.py) — Standard Ryu OpenFlow 1.3 framework application for Mininet environments
- [`src/benchmark.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/benchmark.py) — Automated comparative evaluation engine (Static vs Adaptive Routing)
- [`src/gui_app.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/gui_app.py) (SDN Analytics Dashboard) — Full-height 3-panel dynamic rerouting dashboard, dual-path load graphs, and flow table inspector

---

## 1. What This Subsystem Does (Plain English Overview)

If Subsystem 1 creates the cars (UDP traffic) and Subsystem 2 builds the roads and bridges (switches and links), **Subsystem 3 is the central air traffic control tower of the entire network**.

In traditional computer networks, switches are "dumb" isolated devices. When a link gets jammed, a traditional switch simply shrugs its shoulders and throws packets in the trash. It has no idea that right next to it, an empty backup road is sitting completely unused.

Subsystem 3 solves this problem through **Software-Defined Networking (SDN)**:
1. **The Watchful Eye (Telemetry Poller):** Acts like a camera perched above the network, constantly checking how many bytes pass through every switch port every 0.5 seconds.
2. **The Congestion Detector:** Calculates live traffic speed in Megabits per second. If the primary road (Path A) gets crammed above its 8.0 Mbps safety threshold (80% of link capacity) for two consecutive checks, the controller immediately sounds a congestion alarm.
3. **The Instant Traffic Diverter (OpenFlow FlowMod):** Instead of waiting for a human operator, the controller pushes an instant digital instruction to Ingress Switch $S_1$ in less than 3 milliseconds: *"Divert the main UDP stream away from congested Path A and onto clean Path B immediately!"*
4. **Anti-Oscillation Stability (Hysteresis):** Prevents route "flapping" (bouncing back and forth uncontrollably). The controller will not switch traffic back to Path A until its traffic has cooled down well below 4.5 Mbps.
5. **The Comparative Auditor (Benchmark Suite):** Runs scientific experiments comparing dumb static routing against smart SDN adaptive routing, proving that dynamic rerouting slashes packet loss from 55% down to 0% and restores full network throughput.

---

## 2. Behind the Scenes: How the Technology Works Step-by-Step

### A. Control Plane vs. Data Plane Decoupling
The foundational principle of Software-Defined Networking is the strict separation between the **Data Plane** and the **Control Plane**:
* **Data Plane (Switches):** Responsible only for the raw muscle work—moving packets from an input port to an output port according to a lookup table.
* **Control Plane (SDN Controller):** Responsible for the brain work—deciding *which* paths traffic should take across the entire global topology.

By removing the intelligence from individual switches and placing it into a centralized software controller, we can program the behavior of the entire network using high-level Python code.

---

### B. Why Traditional Routing Protocols Fail in This Scenario

During a technical evaluation, one of the most critical theoretical questions is: *Why couldn't traditional routing protocols like OSPF or ECMP solve this congestion?*

#### 1. Why OSPF (Open Shortest Path First) Fails:
* OSPF calculates routes based on static administrative link costs, typically inversely proportional to bandwidth ($\text{Cost} = \frac{10^8}{\text{Bandwidth}}$) or static link delays.
* Because Path A has a lower propagation delay ($5\text{ms}$) than Path B ($15\text{ms}$), OSPF calculates Path A as the shortest path for all packets.
* **OSPF is completely load-blind.** Even if Path A is running at 130% load and dropping half of all packets, OSPF stubbornly keeps routing all traffic over Path A.
* Furthermore, OSPF routing updates rely on flooding Link-State Advertisements (LSAs) and recomputing Dijkstra’s algorithm, which takes **several seconds to minutes**—far too slow to prevent packet drops during sudden traffic surges.

#### 2. Why ECMP (Equal-Cost Multi-Path) Fails:
* ECMP distributes packets across parallel links by computing a mathematical hash of the packet header 5-tuple (`source IP, destination IP, source port, destination port, protocol`).
* Because all datagrams in our main video/telemetry stream share the exact same 5-tuple, ECMP hashes every single packet into the exact same bucket, pinning the entire flow to Path A. ECMP has zero visibility into real-time queue occupancy or packet drops.

---

### C. The Closed-Loop Telemetry & Rerouting State Machine

The SDN Controller runs a high-precision closed-loop control cycle every $\Delta t = 0.5\text{ seconds}$:

```
  +-------------------------------------------------------------+
  |              THE CLOSED-LOOP SDN CONTROL CYCLE              |
  +-------------------------------------------------------------+
                               |
                               v
                     [1. Poll Switch Ports]
           Query S1 Port 2 (Path A) & Port 3 (Path B) tx_bytes
                               |
                               v
                  [2. Calculate Ingress Load]
             Rate = (tx_bytes_now - tx_bytes_prev) * 8 / Δt
                               |
                               v
                 [3. Threshold Evaluation]
                 Is Path A Load >= 8.0 Mbps?
                               |
                  +------------+------------+
                  |                         |
              NO (Clean)               YES (Congested)
                  |                         |
                  v                         v
          [Reset Breach Counter]   [Increment Breach Counter]
                  |                         |
                  |                Does Counter == 2?
                  |                         |
                  |                   +-----+-----+
                  |                   |           |
                  |                  NO          YES
                  |                   |           |
                  |           (Wait next poll)    v
                  |                     [4. Trigger Failover]
                  |                     Push OFPFlowMod to S1
                  |                     Set priority=200, out_port=3
                  |                     Record Failover Latency (~2.4ms)
                  |                               |
                  +---------------+---------------+
                                  |
                                  v
                    [5. Hysteresis Cooldown Check]
              Does Path A Load drop below 4.5 Mbps?
              If yes, clear cooldown lock.
```

#### Detailed State Machine Steps:
1. **Telemetry Polling (`OFPPortStatsRequest`):** The controller sends a request to Switch $S_1$ asking for the cumulative transmitted byte counters on Port 2 (Path A) and Port 3 (Path B).
2. **Delta Throughput Calculation:**
   $$\text{Throughput (Mbps)} = \frac{(tx\_bytes_t - tx\_bytes_{t-1}) \times 8}{\Delta t \times 1_000_000}$$
3. **Congestion Detection Filter:**
   - Threshold: $\text{CONGESTION\_THRESHOLD\_MBPS} = 8.0\text{ Mbps}$ (80% of link capacity).
   - **Transient Noise Filtering ($N=2$):** A single momentary 10-millisecond traffic blip shouldn't trigger an expensive route change. The controller requires **two consecutive polling intervals** ($1.0\text{ s}$ total) of sustained overload before declaring congestion.
4. **Dynamic OpenFlow Flow Modification (`OFPFlowMod`):**
   - The controller constructs an `OFPFlowMod` packet targeting Ingress Switch $S_1$:
     - **Match Fields:** `IPv4`, `Protocol=UDP (17)`, `nw_dst=10.0.0.2`, `tp_dst=9999`.
     - **Priority:** `200` (higher than the default baseline rule of priority 100).
     - **Action:** `OFPAT_OUTPUT -> Port 3` (Path B).
   - Because Open vSwitch processes rules by descending priority, the hardware immediately redirects subsequent UDP datagrams out of Port 3 in **under 3 milliseconds**.
5. **Anti-Flapping Hysteresis:**
   - As soon as the main stream is moved to Path B, the traffic load on Path A abruptly drops to zero.
   - If the controller were naive, it would say: *"Path A is empty now, let's move traffic back!"* That would cause an immediate loop of endless bouncing (**route flapping**).
   - To guarantee network stability, the controller enforces **hysteresis**: traffic is held on Path B until Path A load remains stably below $\text{HYSTERESIS\_RECOVERY\_MBPS} = 4.5\text{ Mbps}$.

---

### D. Automated Benchmarking Engine (`src/benchmark.py`)
To scientifically prove the superiority of the SDN architecture, the project includes an automated benchmarking testbed:
* Runs an identical 14-second experiment under two scenarios:
  1. **Static Routing (Legacy Mode):** Auto-SDN rerouting is disabled. When the 7.0 Mbps congestion burst hits Path A, the switch cannot adapt.
  2. **Dynamic SDN Routing (Adaptive Mode):** Auto-SDN rerouting is enabled. The controller detects the overload and steers the stream to Path B.
* Measures and plots four critical performance metrics:
  - **Throughput:** Maintained at ~6.0 Mbps in dynamic mode vs dropping to ~3.5 Mbps in static mode.
  - **Packet Loss:** Drops from ~55% peak loss in static mode to 0% in dynamic mode.
  - **Failover Recovery Time:** Quantifies the exact time taken from congestion onset to restored transmission (consistently $\le 10\text{ ms}$).
  - **One-Way Latency & Jitter:** Demonstrates the slight tradeoff: Path B has a higher base delay (15 ms vs 5 ms), but provides **zero packet loss and rock-solid jitter stability**.

---

## 3. How Subsystem 3 Complements the Other Two Subsystems

```
[Subsystem 1: UDP Endpoints]
       |
       | Pumps traffic across the network
       v
[Subsystem 2: Network Infrastructure & Virtual Switches]
       |
       | Transmits packets; accumulates byte counters on Switch S1
       v
[Subsystem 3: SDN Control Plane]
       |
       | 1. Continuously polls Subsystem 2's switch port counters
       | 2. Detects that combined traffic (13.0 Mbps) exceeds the 8.0 Mbps threshold
       | 3. Generates an OpenFlow FlowMod instruction
       v
[Subsystem 2: Switch S1 Forwarding Table]
       |
       | 4. Hardware/Kernel datapath flips output port from Port 2 to Port 3
       v
[Subsystem 1: UDP Receiver]
       |
       | 5. Experiences zero packet drops, restoring application performance
```

1. **Complementing Subsystem 1 (UDP Sockets):**
   - Subsystem 1's UDP streams are inherently defenseless against congestion. Subsystem 3 acts as their guardian angel, monitoring their path health and steering them to safety before severe drop-tail loss degrades the user experience.
2. **Complementing Subsystem 2 (Network Infrastructure):**
   - Subsystem 2 builds the physical switches and links, but those switches have no inherent intelligence. Subsystem 3 provides the brain that transforms those switches into an adaptive, self-healing software-defined network fabric.

---

## 4. Key Libraries & Why They Were Chosen

| Library / Module | Purpose in Subsystem 3 | Technical Justification |
| :--- | :--- | :--- |
| **`ryu.base.app_manager`** | Standard Ryu OpenFlow 1.3 controller framework. | Industry-standard SDN controller framework used in production research and enterprise network virtualization. |
| **`ryu.ofproto.ofproto_v1_3`** | OpenFlow 1.3 protocol message definitions (`OFPFlowMod`, `OFPPortStatsRequest`). | Implements modern OpenFlow 1.3 multi-table pipeline matching and 64-bit port statistics counters. |
| **`matplotlib`** | Generates real-time plots in the GUI and renders publication-ready benchmark charts (`evaluation_results.png`). | High-DPI crisp vector rendering with subpixel antialiasing and headless server rendering support. |
| **`tabulate`** | Formats raw benchmark telemetry into clean ASCII tables in the terminal. | Provides human-readable, professional terminal output during viva demonstrations. |
