# Viva Defense & Demonstration Guide 2: Network Infrastructure & Data Plane

**Complements:** [`study2.md`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/study2.md)  
**Topic Focus:** Diamond Multi-Path Topology, Linux Network Namespaces, Open vSwitch (OVS), Traffic Control (`tc`), Drop-Tail Queue Buffers, and Standalone Data Plane Emulation  
**Relevant Code Files:** `src/topology.py`, `src/network_emulator.py`, `tests/test_system.py`, `src/gui_app.py` (Topology Canvas)

---

## 1. Written Instructions: How to Demonstrate This Subsystem in the App

When presenting the Network Infrastructure and Data Plane subsystem, follow this exact click-by-click walkthrough:

### Step 1: Walk the Evaluator Through the Live Diamond Topology Canvas
1. Look at the upper-left quadrant of **Tab 0 ("🌐 Live Visual Topology & Stream Control")**.
2. Point directly to the nodes on the **Animated Topology Canvas**:
   - **Host $H_1$ (`10.0.0.1`):** Main high-priority traffic sender.
   - **Host $H_3$ (`10.0.0.3`):** Cross-traffic congestion sender.
   - **Switch $S_1$ (Ingress):** Ingress OpenFlow switch that directs flows onto either Path A or Path B.
   - **Switch $S_2$ (Path A - Primary):** Lower-latency path ($5\text{ ms}$ delay, $10.0\text{ Mbps}$ capacity).
   - **Switch $S_3$ (Path B - Backup):** Higher-latency path ($15\text{ ms}$ delay, $10.0\text{ Mbps}$ capacity).
   - **Switch $S_4$ (Egress):** Merges flows and forwards to destinations.
   - **Host $H_2$ (`10.0.0.2`):** Main receiver endpoint.
   - **Host $H_4$ (`10.0.0.4`):** Cross-traffic receiver endpoint.
3. **What to say aloud:**
   > *"This visual topology represents our multi-path Diamond network architecture. Notice how Host H1 connects to Switch S1, which acts as our ingress traffic dispatcher. We have two physically distinct paths connecting S1 to S4: Path A, our primary route with a 5 millisecond delay, and Path B, an alternative route with a 15 millisecond delay. Both links have a 10 Mbps bottleneck bandwidth limit."*

---

### Step 2: Demonstrate the Category 2 Dynamic Network Parameter Sliders
1. On the right-hand panel, find **"Network Parameters & Stream Controls"**.
2. Show the **"Queue Limit"** slider (default: `100 pkts`, adjustable from 10 to 100).
   - Drag it to `50 pkts`, then back to `100 pkts`.
   - Point to the topology label: `Queue: 0/100 pkts` updates in real time.
3. Show the **"Bottleneck BW"** slider (default: `10.0 Mbps`, adjustable from 2.0 to 10.0 Mbps).
   - Point out that adjusting this slider dynamically modifies the token accumulation rate in the underlying link shaper (`set_capacity_mbps()`).
4. **What to say aloud:**
   > *"Under our Category 2 network controls, we have exposed the physical link parameters. We can dynamically adjust the bottleneck bandwidth between 2 and 10 Mbps, and we can configure the FIFO queue buffer limit between 10 and 100 packets. This allows us to observe how buffer sizing impacts queue occupancy and packet loss during congestion."*

---

### Step 3: Show Animated Packet Flow Across the Data Plane
1. If the Main UDP Stream is not running, click **`▶ Start Main UDP Stream`**.
2. Point to the animated dots traveling across the canvas:
   - Green packet dots travel along **$H_1 \rightarrow S_1 \rightarrow S_2 \rightarrow S_4 \rightarrow H_2$**.
   - Notice the link label: `Path A: 6.0M` and `Path B: 0.0M`.
3. **What to say aloud:**
   > *"Notice the 60 FPS vector animation. The green packet stream represents our main UDP flow traveling along Path A via Switch S2. Ingress Switch S1 is currently forwarding this traffic out of Port 2. Path B is currently completely idle."*

---

### Step 4: Inject Congestion and Show the Switch Buffer Filling
1. Click the orange button: **`⚡ Inject Congestion (7M Burst on Path A)`**.
2. Immediately point to:
   - Red packet dots appear, entering from $H_3$ and traveling across Path A alongside the green dots.
   - The **Queue Buffer Meter** above Switch $S_2$: Watch the purple bar jump from `0 pkts` up to `80–100 pkts`!
   - The link label: `Path A: 13.0M` (6M main + 7M burst).
3. **What to say aloud:**
   > *"When I inject the 7.0 Mbps cross-traffic burst from Host H3, the offered load on Path A surges to 13.0 Mbps, exceeding the 10.0 Mbps link capacity. Watch the switch buffer meter above Switch S2: packets accumulate in the FIFO queue. Once the queue reaches its 100-packet limit, tail drop occurs, causing physical packet loss until the SDN controller intervenes."*

---

### Step 5: Demonstrate Pop-Out, Multi-Monitor Windows
1. In the top-right corner of the tab, click **`⧉ Pop Out Window`**.
2. The entire Topology and Operations view pops out into an independent, freely resizable OS desktop window.
3. Resize the window to prove that the vector topology scales dynamically without distortion.
4. Click **`📥 Dock Back In`** to snap the window back into the main tabbed workspace.
5. **What to say aloud:**
   > *"Our user interface supports modern NOC multi-monitor operations. Any tab can be popped out into an independent OS window, freely resized across multiple monitors, and cleanly docked back into the tabbed interface with a single click."*

---

## 2. Core Concepts You Must Master

1. **How Mininet Works (Process-Based Virtualization):**
   - Not a full VM. Uses native Linux kernel primitives directly.
   - **`ip netns` (Network Namespaces):** Isolates the network stack (routing table, interfaces, loopback) for each host ($H_1, H_2, H_3, H_4$).
   - **`veth` pairs (Virtual Ethernet):** Virtual cables connecting a host interface (e.g., `h1-eth0`) to a switch port (e.g., `s1-eth1`).
2. **Linux Traffic Control (`tc`):**
   - **Token Bucket Filter (`tbf`):** Enforces rate limiting at 10.0 Mbps.
   - **`netem`:** Injects exact artificial propagation delays (5 ms on Path A, 15 ms on Path B).
   - **Drop-Tail Buffer:** Drops packets arriving when the 100-packet queue limit is saturated.
3. **Open vSwitch (OVS):**
   - Kernel datapath for fast packet forwarding.
   - Maintains 64-bit port statistics counters (`tx_bytes`, `rx_bytes`, `tx_errors`) on every switch port.
4. **Standalone Python Emulator (`src/network_emulator.py`):**
   - Uses `SimulatedLink` with token-bucket rate limiting and bounded queues (`queue.Queue(maxsize=100)`) to provide identical data-plane physics on Windows and macOS.

---

## 3. Top Expected Viva Questions & Winning Answers

### Q1: What is the difference between Mininet and a full virtual machine like VirtualBox?
**Answer:**
> *"A full virtual machine emulates an entire hardware PC—including BIOS, CPU registers, virtual hard disks, and guest operating systems—which consumes gigabytes of RAM and introduces virtualization overhead. Mininet is a process-based network virtualization engine running natively on the host Linux kernel. It creates isolated hosts using Linux Network Namespaces (`ip netns`) and connects them using virtual Ethernet pairs (`veth`). Every host is simply a regular Linux process running with its own isolated network stack. This allows Mininet to run hundreds of virtual switches and hosts on a single laptop with near-zero overhead."*

---

### Q2: How does Linux Traffic Control (`tc`) enforce bandwidth and delay?
**Answer:**
> *"Linux Traffic Control manipulates the kernel egress queuing disciplines (qdiscs) attached to network interfaces:
> 1. To enforce bandwidth limits, it attaches a **Token Bucket Filter (`tbf`)**. Tokens are deposited into a bucket at a rate of 10 Mbps. Packets can only be transmitted if they consume sufficient tokens; otherwise, they wait in the queue.
> 2. To simulate physical distance and transmission delay, it attaches a **Network Emulator (`netem`)** qdisc that holds packets in a FIFO delay line for exactly 5 ms (Path A) or 15 ms (Path B) before delivering them to the wire.
> 3. To model finite buffer limits, `tbf` enforces `limit=100pkts`. Any packet arriving when the queue holds 100 packets is immediately discarded via drop-tail queueing."*

---

### Q3: What is a `veth` pair and how does it connect hosts to switches?
**Answer:**
> *"A virtual Ethernet (`veth`) pair is a Linux kernel networking construct that acts as a virtual bidirectional patch cable. It is created in pairs (e.g., `veth0` and `veth1`). Any packet injected into `veth0` immediately emerges from `veth1`. Mininet places one endpoint inside the host's private network namespace (named `h1-eth0`) and attaches the other endpoint to the Open vSwitch bridge (named `s1-eth1`). This gives the host a standard Ethernet interface that sends frames directly into the virtual switch."*

---

### Q4: Why is Path A given a 5 ms delay while Path B is given a 15 ms delay?
**Answer:**
> *"In real-world networks, parallel routes rarely have identical physical properties. Path A represents a direct, low-latency primary fiber route (5 ms), while Path B represents a longer, multi-hop alternate route (15 ms). This asymmetric latency is crucial for evaluating dynamic rerouting: it proves that under normal conditions, the network intelligently prefers the lower-latency path, but during severe congestion, the SDN controller will accept the slightly higher 15 ms latency in order to rescue the flow from catastrophic 55% packet loss."*

---

## 4. Examiner Trap Questions ("Gotchas") & How to Defend Them

### Trap 1: "Why not just make the queue buffer 10,000 packets so you never drop any packets?"
**Your Defense:**
> *"Making queue buffers excessively large causes a notorious networking problem known as **Bufferbloat**. If the queue holds 10,000 packets during a 13 Mbps congestion event on a 10 Mbps link, packets won't drop, but they will sit in the queue for several seconds. For real-time UDP streams like video conferences or gaming, a packet that arrives 3 seconds late is completely useless and effectively lost anyway. A bounded buffer of 100 packets (~80 milliseconds of buffering) represents real-world router queue sizing, providing a tight, realistic signal for the SDN controller to detect congestion and reroute."*

### Trap 2: "Can your data plane run on Windows without Mininet?"
**Your Defense:**
> *"Yes. While Mininet requires a Linux kernel due to `ip netns` and Linux `tc`, we specifically engineered a standalone pure-Python data plane emulator (`src/network_emulator.py`). It implements multi-switch relay sockets and uses a custom `SimulatedLink` class with dynamic token-bucket rate limiting and bounded drop-tail queues. It models the exact same Diamond topology, identical bandwidth constraints (10 Mbps), identical asymmetric delays (5 ms vs 15 ms), and identical 100-packet buffer drops on any Windows or macOS machine without requiring root privileges."*
