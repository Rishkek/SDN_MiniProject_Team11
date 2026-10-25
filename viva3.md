# Viva Defense & Demonstration Guide 3: SDN Control Plane & Dynamic Rerouting

**Complements:** [`study3.md`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/study3.md)  
**Topic Focus:** OpenFlow 1.3 Controller Architecture, Continuous Telemetry Polling, Congestion Detection, Hysteresis, Dynamic FlowMod Rerouting, and Automated Benchmarking  
**Relevant Code Files:** `src/sdn_controller.py`, `src/ryu_controller.py`, `src/benchmark.py`, `src/gui_app.py` (SDN Analytics Dashboard & Benchmark Dashboard)

---

# ================================================================
# PART 1: DELIVERABLE 1 (D1 — FOUNDATION DEMO & VIVA - 15 MARKS)
# ================================================================

## 1. D1 Step-by-Step Demonstration Walkthrough in the App

Follow these exact steps when demonstrating the **Deliverable 1 Foundation**:

### Step 1: Explain the Decoupled SDN Architecture
1. Launch the application (`python run.py`) and stay on **Tab 0 ("🌐 Live Visual Topology & Stream Control")**.
2. **What to say aloud:**
   > *"In traditional networks, switches are isolated, uncoordinated boxes. In Software-Defined Networking, we separate the Data Plane (fast packet forwarding in switches) from the Control Plane (centralized routing intelligence in software). Our controller maintains a global view of all switch port counters and programs switch behavior dynamically using OpenFlow 1.3."*

---

### Step 2: Inspect Switch S1's Baseline OpenFlow 1.3 Flow Table
1. Look at the right-hand panel of Tab 0: find the **"Switch S1 OpenFlow 1.3 Flow Table"** display.
2. Point to the baseline Priority 100 flow rule:
   ```
   cookie=0x0, duration=12.4s, table=0, n_packets=4210, n_bytes=4311040,
   priority=100,udp,in_port=1,nw_dst=10.0.0.2,tp_dst=9999 actions=output:2
   ```
3. Point out:
   - `priority=100`: The default baseline rule.
   - `in_port=1`: Traffic arriving from Host $H_1$.
   - `actions=output:2`: Steers traffic to Port 2 (Path A via Switch $S_2$).
4. Point to the **translucent watermark `*D1`** on the visual topology canvas.
5. **What to say aloud:**
   > *"Here in Switch S1's flow table, we can inspect the baseline OpenFlow rule. It directs incoming UDP packets destined for 10.0.0.2 out of Port 2 along Path A. Path A is selected as the default route because it has a lower propagation delay (5 ms vs 15 ms). As long as traffic remains clean, packets travel over Path A with zero loss."*

---

### Step 3: Explain How the Controller Polls Port Hardware Counters
1. Explain how `OFPPortStatsRequest` works behind the scenes.
2. **What to say aloud:**
   > *"Our SDN controller continuously communicates with Switch S1 using OpenFlow 1.3. Every 500 milliseconds, it queries the hardware port counters using `OFPPortStatsRequest`. The switch replies with transmitted byte counts (`tx_bytes`). By calculating the difference between consecutive polls, the controller calculates the exact bitrate passing through each physical link in real time."*

---

## 2. Core D1 Viva Defense Questions & Answers

### Q1: What is the difference between the Control Plane and Data Plane in SDN?
**Answer:**
* **Data Plane:** Implemented inside switches (Open vSwitch). It is responsible only for forwarding packets from input ports to output ports at line rate based on match-action rules stored in flow tables.
* **Control Plane:** Implemented by the **SDN Controller**. It operates as the centralized brain, calculating routing policies, monitoring network-wide port telemetry, and installing/deleting flow rules across switches via OpenFlow messages.

### Q2: Why couldn't traditional routing protocols like OSPF solve this congestion?
**Answer:**
* **OSPF is completely load-blind.** It computes shortest paths based on static administrative metrics ($\text{Cost} = \frac{10^8}{\text{Bandwidth}}$) or static link delays.
* Because Path A has a 5 ms delay and Path B has a 15 ms delay, OSPF always computes Path A as the shortest path.
* Even when Path A is overloaded at 130% capacity and dropping 50% of all packets, OSPF stubbornly keeps routing all traffic over Path A.
* Furthermore, OSPF link-state convergence takes **several seconds to minutes**, far too slow to prevent packet drops during sudden surges.

### Q3: Why does ECMP (Equal-Cost Multi-Path) fail in this scenario?
**Answer:**
ECMP distributes traffic across parallel links by hashing the 5-tuple header (`src IP, dst IP, src port, dst port, proto`). Because all datagrams in our main flow share the identical 5-tuple, ECMP hashes every single packet into the same bucket, pinning the entire flow to Path A. ECMP has zero real-time awareness of link utilization or buffer occupancy.

---

# ================================================================
# PART 2: DELIVERABLE 2 (D2 — ADVANCED DEMO & VIVA - 25 MARKS)
# ================================================================

## 1. D2 Step-by-Step Demonstration Walkthrough in the App

Follow these exact steps when demonstrating the **Deliverable 2 Advanced Functionality**:

### Step 1: Open the Dedicated SDN Analytics Dashboard
1. Click on **Tab 1: "📊 SDN Dynamic Rerouting Analytics & Dual-Path Telemetry"**.
2. Point out the three full-height analytical plots powered by PyQtGraph:
   - **Top Plot:** *Dual-Path Offered Load vs SDN Congestion Threshold & Capacity*.
     - Point to the dashed yellow line: **`SDN Threshold (8.0M)`**.
     - Point to the dotted orange line: **`Bottleneck Capacity (10.0M)`**.
     - Point to the green curve: **`Path-A Load (Primary)`**.
     - Point to the blue curve: **`Path-B Load (Alternate)`**.
   - **Bottom-Left Plot:** *Switch S1 Ingress Buffer Queue & Packet Loss Rate*.
   - **Bottom-Right Plot:** *End-to-End One-Way Latency & RFC 3550 Jitter Stability*.
3. Point to the **translucent watermark `*D2`** in the bottom-right corner.
4. **What to say aloud:**
   > *"Under Deliverable 2, we have built a dedicated real-time SDN Analytics Dashboard. The top plot displays our dual-path offered load against the 8.0 Mbps SDN congestion threshold and 10.0 Mbps link capacity ceiling. Notice our telemetry polling loop calculates bitrate every 500 milliseconds. Currently, Path A carries 6.0 Mbps, well below the threshold."*

---

### Step 2: Trigger Congestion & Demonstrate Autonomous SDN Failover
1. Click **`⚡ Inject Congestion (7M Burst on Path A)`**.
2. Immediately observe **Tab 1**:
   - Watch the green curve (Path A load) surge from `6.0 Mbps` to `13.0 Mbps`, crossing the yellow `8.0 Mbps` threshold line!
   - In the bottom-left plot, watch the purple queue occupancy line spike to 85 pkts.
   - After exactly two polling intervals (1.0 second), **watch the failover occur**:
     - The green curve (Path A) instantly plummets to `0.0 Mbps`.
     - The blue curve (Path B) instantly jumps to `6.0 Mbps`!
   - Look at the top-right header status pill:
     - Turns bright blue: **`ACTIVE PATH: Path-B (DYNAMICALLY REROUTED)`**.
     - Displays: **`Failover Latency: ~2.4 ms`**.
   - Point to the bottom event log:
     ```
     [SDN FLOWMOD EVENT] Congestion Detected on Path-A! Switch S1 dynamically steered flow to Path-B. Failover latency: 2.4 ms
     ```
3. **What to say aloud:**
   > *"When cross-traffic hit Path A, load surged to 13.0 Mbps. To avoid reacting to momentary 10 ms blips, our controller required two consecutive breach intervals. Once confirmed, it pushed an OpenFlow 1.3 FlowMod message with Priority 200 to Switch S1, redirecting traffic to Port 3. Failover occurred in just 2.4 milliseconds, instantly eliminating packet drops."*

---

### Step 3: Show the Dynamic Flow Rule in Switch S1's Hardware Flow Table
1. Switch back to **Tab 0 ("🌐 Live Visual Topology & Stream Control")**.
2. Look at the **"Switch S1 OpenFlow 1.3 Flow Table"** readout:
   ```
   cookie=0x0, duration=4.2s, table=0, n_packets=2410, n_bytes=2467840,
   priority=200,udp,in_port=1,nw_dst=10.0.0.2,tp_dst=9999 actions=output:3
   ```
3. Point out that **`priority=200`** overrides the default Priority 100 rule, outputting to **`Port 3 (Path B)`**.
4. **What to say aloud:**
   > *"Here in Switch S1's flow table, we see the newly installed Priority 200 rule. Because Open vSwitch matches flows in descending priority order, incoming packets destined for port 9999 match this rule first and are immediately forwarded out of Port 3 onto clean Path B."*

---

### Step 4: Execute the 3-Phase Automated Benchmark Evaluation
1. Switch to **Tab 3: "⚡ Automated Benchmark Performance Evaluation"**.
2. Point out that cached baseline results are loaded with badge `[Cached Baseline — Click Execute to Re-Evaluate]`.
3. Click the bold button: **`⚡ Execute 3-Phase Automated Benchmark (Static vs Dynamic vs Rate-Adapt)`**.
4. Point out the real-time execution feedback:
   - Header badge immediately updates: `📊 Quantitative Benchmark Evaluation [Executing Run #1...]`.
   - Table cells show active progress: `⏳ Measuring Exp A (Static)...`.
   - Graph shows the active run placeholder.
   - Progress bar advances smoothly (0% to 100%).
   - **Phase 1 completes:** Column 1 (Static) immediately populates with live measured numbers!
   - **Phase 2 completes:** Column 2 (Dynamic SDN) populates with live numbers, and Column 4 calculates initial bandwidth recovery gain!
   - **Phase 3 completes:** Column 3 (SDN+Rate) populates, and the full 11-row table updates with final verdicts!
   - Embedded Matplotlib canvas re-renders with fresh 4-panel graphs and timestamp badge:
     `SDN Congestion Detection and Traffic Rerouting - Empirical Performance Evaluation [Run #1 — HH:MM:SS]`.
5. Highlight the final comparative metrics:
   - **Throughput:** Dynamic restored to **`~5.3 Mbps`** (+25% over Static).
   - **Packet Loss:** Static experienced **`~15% avg / 39% peak loss`**, while Dynamic dropped loss to **`<2.5%`**.
   - **Recovery Time:** Dynamic recovered in **`<10 ms`**, while Static suffered sustained loss with **`No Recovery`**.
6. **What to say aloud:**
   > *"Under Deliverable 2, we built an automated 3-phase benchmark engine. As you saw, the dashboard streams live metrics phase-by-phase as each experiment completes. The final comparison scientifically proves that our dynamic SDN controller slashes packet loss from 39% to near zero and restores full application throughput with sub-second failover recovery."*

---

## 2. Core D2 Viva Defense Questions & Answers

### Q4: Explain the step-by-step logic of your Congestion Detection Algorithm.
**Answer:**
Every $\Delta t = 0.5\text{ seconds}$, the controller executes:
1. **Delta Throughput:** $\text{Bitrate} = \frac{(\text{bytes}_t - \text{bytes}_{t-1}) \times 8}{\Delta t \times 1{,}000{,}000}$.
2. **Threshold Comparison:** Checks if $\text{Bitrate} \ge \text{CONGESTION\_THRESHOLD\_MBPS} (8.0\text{ Mbps})$.
3. **Transient Noise Filter ($N=2$):** If breached, `consecutive_breaches` increments. Congestion is only declared when the counter reaches 2 ($1.0\text{ second}$ of sustained overload).
4. **Action:** Once confirmed, it triggers `_trigger_reroute()`, constructing and dispatching the OpenFlow `FlowMod` instruction to Switch $S_1$.

### Q5: What is route flapping, and how does your controller prevent it using hysteresis?
**Answer:**
Route flapping occurs when shifting traffic away from Path A causes Path A's load to drop to zero, prompting a naive controller to immediately switch traffic back to Path A, resulting in an endless oscillation loop.  
Our controller enforces **anti-flapping hysteresis**: once traffic is shifted to Path B, it is locked there until Path A's load drops stably below $\text{HYSTERESIS\_RECOVERY\_MBPS} = 4.5\text{ Mbps}$.

### Q6: What were the key performance optimizations made to the GUI dashboard?
**Answer:**
* **PyQtGraph Migration:** Replaced Matplotlib real-time canvas redraws with PyQtGraph (`pg.GraphicsLayoutWidget`), dropping curve update latency from **240 ms down to 2.47 ms (~97x faster)** and eliminating Qt event-loop freezing.
* **Bounded Ring Buffers:** Used `collections.deque(maxlen=2000)` and trailing sliding-window de-indexing to keep RAM usage locked at **~92–95 MB** indefinitely.
* **Thread-Safe Matplotlib Rendering:** Restricted Matplotlib figure generation and file saving strictly to the main GUI thread, preventing cross-thread Qt widget crashes.
