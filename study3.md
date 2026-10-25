# Study Guide 3: SDN Control Plane, Closed-Loop Telemetry & Dynamic OpenFlow Rerouting

**Component Focus:** OpenFlow 1.3 Controller Architecture, Continuous Telemetry Polling, Congestion Detection, Hysteresis, Dynamic FlowMod Rerouting, and Automated Performance Benchmarking  
**Owned Project Files:**
- [`src/sdn_controller.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/sdn_controller.py) — Core SDN controller, telemetry engine, hysteresis state machine, and flow table manager
- [`src/ryu_controller.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/ryu_controller.py) — Standard Ryu OpenFlow 1.3 framework application for Mininet environments
- [`src/benchmark.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/benchmark.py) — Automated comparative evaluation engine (Static vs Adaptive Routing vs Rate Control)
- [`src/gui_app.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/gui_app.py) (SDN Analytics Dashboard & Benchmark Dashboard) — Dual-path load graphs, flow table inspector, and watermark `*D2`

---

# ================================================================
# PART 1: DELIVERABLE 1 (D1 — FOUNDATION - 15 MARKS)
# ================================================================

## 1. What to Explain for Deliverable 1
In Deliverable 1, your role is to explain **how the SDN Control Plane decouples network intelligence from switch hardware**:
1. The difference between the Control Plane (intelligence) and the Data Plane (forwarding).
2. How the OpenFlow 1.3 protocol defines communications between switches and the controller.
3. How Switch $S_1$'s initial flow table is configured with default baseline rules (Priority 100 directing traffic to Path A).
4. How the controller queries 64-bit hardware port byte counters using `OFPPortStatsRequest`.
5. Why traditional routing protocols like OSPF and ECMP are fundamentally incapable of preventing congestion in this scenario.

---

## 2. D1 Behind the Scenes: Control Plane Architecture Step-by-Step

### A. Control Plane vs. Data Plane Decoupling
In traditional networking, switches are isolated, distributed boxes running complex embedded software. In **Software-Defined Networking (SDN)**:
* **Data Plane (Switches):** Performs simple, high-speed packet forwarding based on match-action rules stored in flow tables.
* **Control Plane (Controller):** Operates as a centralized software brain with global visibility of the entire network topology, making dynamic forwarding decisions using high-level Python code.

---

### B. Baseline OpenFlow 1.3 Flow Rules
When the network starts up, the controller installs baseline forwarding rules into Switch $S_1$:
```
Table 0:
- Priority 100: Match in_port=1 (H1) -> Action: Output to Port 2 (Path A)
- Priority 0: Match * (All other traffic) -> Action: Normal / Drop
```
Under normal baseline conditions (6.0 Mbps transmission), traffic flows smoothly over Path A with low 5 ms latency and zero packet loss.

---

### C. Hardware Port Statistics Accounting
The controller continuously communicates with OpenFlow switches using asynchronous request-reply messages:
1. The controller sends an `OFPPortStatsRequest` targeting Switch $S_1$.
2. The switch returns an `OFPPortStatsReply` containing cumulative 64-bit counters:
   - `tx_bytes`: Total bytes transmitted out of each port.
   - `rx_bytes`: Total bytes received on each port.
   - `tx_dropped`: Packets dropped due to queue buffer exhaustion.

---

### D. Why Traditional Routing Protocols Fail in This Scenario
A classic viva exam question is: *Why can't OSPF or ECMP solve this congestion problem?*

#### 1. Why OSPF (Open Shortest Path First) Fails:
* **OSPF is completely load-blind.** It computes routes based on static administrative link metrics ($\text{Cost} = \frac{10^8}{\text{Bandwidth}}$) or static delays.
* Because Path A has a lower delay (5 ms) than Path B (15 ms), OSPF routes 100% of packets over Path A.
* Even when Path A is drowning in 130% load and dropping half of all packets, OSPF will stubbornly keep sending traffic over Path A.
* Furthermore, OSPF link-state convergence takes **several seconds to minutes**, far too slow to prevent packet drops.

#### 2. Why ECMP (Equal-Cost Multi-Path) Fails:
* ECMP balances traffic across parallel paths by computing a hash of the packet header 5-tuple (`src IP, dst IP, src port, dst port, proto`).
* Because all datagrams in our main flow share the exact same 5-tuple, ECMP hashes every single packet into the same bucket, pinning the entire flow to Path A. ECMP has zero real-time awareness of link utilization or queue overflow.

---

# ================================================================
# PART 2: DELIVERABLE 2 (D2 — ADVANCED FUNCTIONALITY - 25 MARKS)
# ================================================================

## 1. What to Explain for Deliverable 2
In Deliverable 2, your role is to explain **how the closed-loop telemetry engine detects congestion, executes dynamic failover, prevents route flapping, and scientifically proves performance gains**:
1. How the closed-loop telemetry poller samples byte deltas every $\Delta t = 0.5\text{ seconds}$ to compute real-time link bitrate.
2. The Congestion Detection Algorithm: 8.0 Mbps threshold (80% link capacity) with 2-consecutive breach filtering ($N=2$) to eliminate false triggers from momentary traffic spikes.
3. How the controller pushes an autonomous OpenFlow 1.3 `OFPFlowMod` instruction to redirect traffic to Path B with sub-second failover latency ($\le 9.5\text{ ms}$).
4. The Anti-Flapping Hysteresis State Machine (4.5 Mbps recovery threshold) ensuring network stability.
5. The 3-Phase Automated Benchmark Evaluation (`src/benchmark.py` & Tab 4) demonstrating quantitative metrics and high-DPI comparative plots.

---

## 2. D2 Behind the Scenes: Closed-Loop SDN Engine Step-by-Step

### A. The Closed-Loop Telemetry & Rerouting State Machine

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

---

### B. Detailed Step-by-Step Mechanics

#### 1. Real-Time Telemetry Calculation:
Every $\Delta t = 0.5\text{ seconds}$, the controller reads the byte counter delta:
$$\text{Bitrate (Mbps)} = \frac{(\text{bytes}_t - \text{bytes}_{t-1}) \times 8}{\Delta t \times 1{,}000{,}000}$$

#### 2. Two-Stage Breach Filtering ($N=2$):
* To prevent expensive, disruptive route changes due to short micro-bursts (e.g., a momentary 10 ms spike), the controller enforces a 2-consecutive breach rule.
* Congestion is only declared when load $\ge 8.0\text{ Mbps}$ for **two consecutive intervals** ($1.0\text{ second}$ of sustained overload).

#### 3. Autonomous OpenFlow 1.3 `OFPFlowMod` Injection:
Upon confirming congestion:
```python
# Create high-priority flow rule
match = parser.OFPMatch(eth_type=0x0800, ip_proto=17, ipv4_dst="10.0.0.2", udp_dst=9999)
actions = [parser.OFPActionOutput(port=3)] # Redirect to Path B
# Install with Priority 200 (overrides default Priority 100)
```
* Switch $S_1$ installs the rule into its hardware/kernel datapath in **$\approx 2.4\text{ ms}$**.
* Subsequent packets are immediately diverted to clean Path B. Packet loss drops to **0.0%**.

#### 4. Anti-Flapping Hysteresis:
* When the main flow shifts to Path B, Path A's load drops abruptly.
* Without hysteresis, a naive controller would immediately shift traffic back to Path A, creating an endless loop of route flapping.
* Our controller enforces **hysteresis**: traffic is held on Path B until Path A load remains stably below **`4.5 Mbps`** ($\text{HYSTERESIS\_RECOVERY\_MBPS}$).

---

### C. 3-Phase Automated Performance Evaluation Engine (`src/benchmark.py`)
To empirically prove the benefits of SDN, Tab 4 executes an automated comparative evaluation across three experiments:
1. **Experiment A (Static Routing Baseline):** Rerouting disabled. Path A saturates under 13 Mbps load; packet loss surges to ~55%, throughput collapses to ~3.5 Mbps, bufferbloat causes 100+ ms latency.
2. **Experiment B (Dynamic SDN Rerouting):** Autonomous OpenFlow failover to Path B restores throughput to 6.0 Mbps with 0% sustained loss and sub-second recovery.
3. **Experiment C (SDN + Closed-Loop Rate Adaptation):** When both paths experience constraints, client rate throttling dynamically matches network capacity.
* **Features:** Live phase-by-phase table streaming, timestamped execution badges (`[Run #N — Completed at HH:MM:SS]`), and 4-panel comparative graphs.

---

## 3. How Subsystem 3 Complements the Other Two Subsystems

```
[Subsystem 1: UDP Endpoints]
       |
       | Generates traffic across the network
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

---

## 4. Key Libraries & Technical Justifications

| Library / Module | Purpose in Subsystem 3 | Technical Justification |
| :--- | :--- | :--- |
| **`ryu.base.app_manager`** | Standard Ryu OpenFlow 1.3 controller framework. | Industry-standard SDN controller framework used in production research and enterprise network virtualization. |
| **`ryu.ofproto.ofproto_v1_3`** | OpenFlow 1.3 protocol message definitions (`OFPFlowMod`, `OFPPortStatsRequest`). | Implements modern OpenFlow 1.3 multi-table pipeline matching and 64-bit port statistics counters. |
| **`pyqtgraph`** | Hardware-accelerated real-time live telemetry charting in the GUI. | Sub-millisecond vector rendering (<0.3 ms updates) with native interactive panning and zooming. |
| **`matplotlib`** | Generates publication-ready comparative benchmark charts (`evaluation_results.png`). | High-DPI crisp vector rendering with subpixel antialiasing and headless server rendering support. |
| **`tabulate`** | Formats raw benchmark telemetry into clean ASCII tables in the terminal. | Provides human-readable, professional terminal output during viva demonstrations. |
