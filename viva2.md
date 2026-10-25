# Viva Defense & Demonstration Guide 2: Network Infrastructure & Data Plane

**Complements:** [`study2.md`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/study2.md)  
**Topic Focus:** Diamond Multi-Path Topology, Mininet Virtualization, Linux Traffic Control (`tc`), Drop-Tail Queue Buffers, Standalone Data Plane Emulation, and Automated Test Suite  
**Relevant Code Files:** `src/topology.py`, `src/network_emulator.py`, `tests/test_system.py`, `src/gui_app.py` (Topology Canvas)

---

# ================================================================
# PART 1: DELIVERABLE 1 (D1 — FOUNDATION DEMO & VIVA - 15 MARKS)
# ================================================================

## 1. D1 Step-by-Step Demonstration Walkthrough in the App

Follow these exact steps when demonstrating the **Deliverable 1 Foundation**:

### Step 1: Walk the Evaluator Through the Live Diamond Topology Canvas
1. Launch the application (`python run.py`) and stay on **Tab 0 ("🌐 Live Visual Topology & Stream Control")**.
2. Look at the upper-left quadrant: **Animated Topology Canvas**.
3. Point directly to the visual nodes and links on the screen:
   - **Host $H_1$ (`10.0.0.1`):** Primary traffic source.
   - **Switch $S_1$ (Ingress Switch):** Dispatches packets to either Path A or Path B.
   - **Switch $S_2$ (Path A - Primary):** $5\text{ ms}$ delay, $10.0\text{ Mbps}$ capacity, $100\text{-packet}$ buffer.
   - **Switch $S_3$ (Path B - Backup):** $15\text{ ms}$ delay, $10.0\text{ Mbps}$ capacity, $100\text{-packet}$ buffer.
   - **Switch $S_4$ (Egress Switch):** Merges flows and forwards to destinations.
   - **Host $H_2$ (`10.0.0.2`):** Primary receiver endpoint.
4. Point to the **translucent watermark `*D1`** in the bottom-right corner of the canvas.
5. **What to say aloud:**
   > *"This visual canvas represents our multi-path Diamond network topology. Host H1 connects to Ingress Switch S1. Between S1 and Egress Switch S4, we have two physically distinct routes: Path A (the primary low-latency route with a 5 ms delay) and Path B (an alternative route with a 15 ms delay). Both paths have a 10.0 Mbps bottleneck bandwidth limit. Under Deliverable 1 baseline routing, all traffic travels across Path A."*

---

### Step 2: Show Animated Baseline Packet Flow Across the Data Plane
1. Click **`▶ Start Main UDP Stream`** (if not already running).
2. Point to the animated green dots moving across the screen:
   - Packets flow along: **$H_1 \rightarrow S_1 \rightarrow S_2 \rightarrow S_4 \rightarrow H_2$**.
   - Show the link label on Path A: `Path A: 6.0M` with `Queue: 0/100 pkts`.
   - Show the link label on Path B: `Path B: 0.0M` (idle).
3. **What to say aloud:**
   > *"Notice the 60 FPS vector animation. The green packet stream represents our main UDP flow passing through Switch S1 and traveling along Path A via Switch S2. The queue buffer on Switch S2 is empty (0/100 pkts) because our 6.0 Mbps transmission rate is well within the 10.0 Mbps link capacity. Path B is currently completely idle."*

---

### Step 3: Explain Cross-Platform Data Plane Architecture
1. Explain how the data plane works in Mininet vs Standalone mode.
2. **What to say aloud:**
   > *"In Linux, our topology runs on top of native Mininet using Linux Network Namespaces, Virtual Ethernet pairs, and Open vSwitch. For Windows and macOS demonstration, we built a standalone pure-Python data plane emulator in `src/network_emulator.py` that implements bounded FIFO drop-tail queues and token-bucket bandwidth shapers, guaranteeing 100% architectural fidelity without requiring Linux root privileges."*

---

## 2. Core D1 Viva Defense Questions & Answers

### Q1: What is a Diamond Multi-Path Topology, and why is it used?
**Answer:**
A Diamond Topology connects an ingress switch ($S_1$) to an egress switch ($S_4$) via two parallel intermediate switches ($S_2$ and $S_3$). It provides multiple distinct physical paths between the same source and destination. In our implementation:
- **Path A ($S_1 \rightarrow S_2 \rightarrow S_4$):** Low latency (5 ms), primary path.
- **Path B ($S_1 \rightarrow S_3 \rightarrow S_4$):** Higher latency (15 ms), alternative/failover path.
This layout is the canonical benchmark topology in SDN research for evaluating dynamic flow rerouting during bottleneck congestion.

### Q2: How does Mininet virtualize hosts and links on Linux?
**Answer:**
Mininet uses lightweight OS-level process virtualization features built into the Linux kernel:
1. **Network Namespaces (`ip netns`):** Each host ($H_1, H_2$) runs in an isolated network namespace with its own private routing table, ARP cache, and network interfaces.
2. **Virtual Ethernet Pairs (`veth`):** Acts as a virtual network cable; packets sent into `h1-eth0` immediately emerge at switch port `s1-eth1`.
3. **Linux Traffic Control (`tc`):** Uses Token Bucket Filter (`tbf`) for 10 Mbps bandwidth limiting, FIFO queues for 100-packet buffer depths, and `netem` for 5 ms / 15 ms delay emulation.

### Q3: How does your standalone Python data plane emulator model physical links?
**Answer:**
In [`src/network_emulator.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/network_emulator.py), each physical link is modeled by the `SimulatedLink` class:
* It maintains a bounded FIFO queue (`queue.Queue(maxsize=100)`).
* It implements a **continuous token-bucket rate limiter** that calculates byte allowances dynamically based on monotonic time deltas, draining packets at exact line rate ($1{,}250{,}000\text{ bytes/s}$ for 10 Mbps).
* If the queue reaches 100 packets, incoming packets are dropped immediately, mirroring hardware drop-tail queuing.

---

# ================================================================
# PART 2: DELIVERABLE 2 (D2 — ADVANCED DEMO & VIVA - 25 MARKS)
# ================================================================

## 1. D2 Step-by-Step Demonstration Walkthrough in the App

Follow these exact steps when demonstrating the **Deliverable 2 Advanced Functionality**:

### Step 1: Demonstrate Dynamic Parameter Controls (Sliders)
1. On the right-hand panel, find **"Network Parameters & Stream Controls"**:
2. **Queue Limit Slider (10 – 100 pkts):** Drag the slider to `40 pkts`.
   - Point to the canvas: The queue meter label above Switch $S_2$ instantly updates to `Queue: 0/40 pkts`.
   - Drag it back to `100 pkts`.
3. **Bottleneck BW Slider (2.0 – 10.0 Mbps):** Show how dragging the slider dynamically updates the token accumulation rate in the underlying link shaper (`set_capacity_mbps()`).
4. **What to say aloud:**
   > *"Under Deliverable 2, we exposed dynamic data-plane parameter controls. We can adjust bottleneck bandwidth between 2 and 10 Mbps, and modify the switch FIFO buffer limit between 10 and 100 packets in real time to observe the impact on queue saturation and packet loss."*

---

### Step 2: Inject Congestion Burst & Observe Physical Queue Overflow
1. Click the orange button: **`⚡ Inject Congestion (7M Burst on Path A)`**.
2. Immediately point to the **Animated Topology Canvas**:
   - Red packet dots appear, entering from $H_3$ and flowing onto Path A alongside green dots.
   - Point to the **Queue Buffer Meter** above Switch $S_2$: Watch the purple fill bar rapidly jump from `0 pkts` to `80–100 pkts`!
   - Point to the link label: `Path A: 13.0M (CONGESTED)`.
   - Point to the dropped packet indicators: Packets being discarded at Switch $S_2$ via tail drop.
3. **What to say aloud:**
   > *"When I inject the 7.0 Mbps cross-traffic burst, offered load on Path A surges to 13.0 Mbps. Because this exceeds the 10.0 Mbps link capacity, packets accumulate in Switch S2's buffer. Watch the queue meter fill up to 100 packets. Once full, tail drop occurs and excess packets are physically discarded."*

---

### Step 3: Observe Hardware Datapath Switching to Path B
1. Watch the canvas as the SDN controller executes failover:
   - The green packet dots instantly divert from Path A onto **Path B ($S_1 \rightarrow S_3 \rightarrow S_4$)**!
   - Path A carries only red cross-traffic dots (`7.0M`), allowing Switch $S_2$'s queue to drain back to `0/100 pkts`.
   - Switch $S_1$'s active flow table rule updates to `actions=output:3`.
2. Point to the **translucent watermark `*D2`** on the SDN Analytics dashboard (Tab 1).
3. **What to say aloud:**
   > *"Notice how the data plane instantly reroutes the main stream. Ingress Switch S1 executes the OpenFlow FlowMod instruction in under 3 milliseconds, redirecting green packets out of Port 3 to Path B. Path A's queue immediately drains, and both streams now travel without drops."*

---

### Step 4: Run the 13-Test Automated Regression Suite
1. Open a terminal and run the test suite:
   ```powershell
   py -m pytest -v tests/
   ```
2. Show the evaluator the 13 passing test results:
   ```
   tests/test_system.py::test_a_basic_socket_communication PASSED
   tests/test_system.py::test_c_baseline_routing PASSED
   tests/test_system.py::test_d_congestion_detection PASSED
   tests/test_system.py::test_e_dynamic_rerouting PASSED
   tests/test_system.py::test_k_sdn_flow_rerouting_metrics PASSED
   ======================== 13 passed in ~42s ========================
   ```
3. **What to say aloud:**
   > *"We have implemented a comprehensive 13-test automated test suite in `tests/test_system.py` that validates all data-plane behaviors, including drop-tail queue saturation, failover latency, and traffic restoration across both Mininet and standalone environments."*

---

## 2. Core D2 Viva Defense Questions & Answers

### Q4: Explain what happens inside the switch buffer during a 130% traffic burst.
**Answer:**
* Main traffic (6.0 Mbps) and cross-traffic (7.0 Mbps) combine at Switch $S_1$, producing 13.0 Mbps of offered load heading into Path A.
* The link's token bucket shaper only permits 10.0 Mbps to depart.
* Excess traffic accumulates in the 100-packet FIFO queue buffer at a rate of 3.0 Mbps ($\approx 366\text{ pkts/sec}$).
* In $\approx 270\text{ ms}$, the buffer fills completely.
* Any subsequent packet arriving while the queue is at capacity cannot be stored and is discarded via **tail drop**.

### Q5: How fast does the switch reconfigure its forwarding table upon receiving an OpenFlow `FlowMod`?
**Answer:**
In Open vSwitch, the `OFPFlowMod` message updates the user-space flow table and invalidates the fast-path datapath flow cache in the Linux kernel. The kernel datapath reconfigures in **$< 3.0\text{ milliseconds}$** (measured empirically at $\approx 2.4\text{ ms}$). Packets arriving immediately after are switched to Port 3 with zero queue delay.

### Q6: How do your dynamic sliders alter data-plane parameters in real time?
**Answer:**
* The **Bottleneck Bandwidth Slider** invokes `link.set_capacity_mbps(new_val)`, which dynamically recalculates token replenishment rates in the token-bucket shaper.
* The **Queue Limit Slider** invokes `link.set_max_queue(new_limit)`, dynamically adjusting the drop-tail threshold in memory. Both adjustments take effect on the very next packet iteration without restarting the network.
