# Viva Defense & Demonstration Guide 1: Transport Layer & Socket Programming

**Complements:** [`study1.md`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/study1.md)  
**Topic Focus:** Low-Level UDP Sockets, 22-Byte Binary Protocol, Precise Rate Pacing, Receiver Telemetry, Multi-Flow Traffic, and Rate Adaptation  
**Relevant Code Files:** `src/protocol.py`, `src/udp_sender.py`, `src/udp_receiver.py`, `src/congestion_generator.py`

---

# ================================================================
# PART 1: DELIVERABLE 1 (D1 — FOUNDATION DEMO & VIVA - 15 MARKS)
# ================================================================

## 1. D1 Step-by-Step Demonstration Walkthrough in the App

Follow these exact steps when demonstrating the **Deliverable 1 Foundation**:

### Step 1: Launch the Application
Open PowerShell or Terminal and start the GUI dashboard:
```powershell
python run.py
```
*(Point out to the evaluator that the dashboard initializes clean sockets bound to localhost `127.0.0.1` on ports `9000` (ingress), `9999` (main receiver), and `9998` (cross-traffic receiver).)*

---

### Step 2: Configure Sending Rate & Review Socket Controls
1. On **Tab 0 ("🌐 Live Visual Topology & Stream Control")**, look at the right-hand panel: **"Network Parameters & Stream Controls"**.
2. Find the **"Main Send Rate"** slider and set it to **`6.0 Mbps`**.
3. **What to say aloud:**
   > *"Here in our application layer controls, we have implemented a high-precision UDP sender. Notice that we are not using any high-level HTTP wrappers or requests libraries. We are programming directly against low-level BSD sockets using Python's native `socket` library. I am configuring our main traffic stream to transmit at exactly 6.0 Mbps."*

---

### Step 3: Start the Main UDP Stream & Verify Telemetry
1. Click the green button: **`▶ Start Main UDP Stream`**.
2. Notice the button turns pink and changes to **`⏹ Stop Main UDP Stream`**.
3. Point your finger to the bottom right: **"Category 2: Real-Time Socket Telemetry"**:
   - **Live Throughput:** Locks smoothly at **`5.9 – 6.0 Mbps`**.
   - **Goodput:** Displays **`~5.8 Mbps`** (raw payload rate excluding protocol headers).
   - **One-Way Latency:** Reads **`~5.0 ms`** (the physical propagation delay of clean Path A).
   - **RFC 3550 Jitter:** Displays a stable value under **`0.5 ms`**.
   - **Packet Counters:** `Recv` counter increments rapidly by hundreds of packets/sec with `Lost: 0`.
4. Point to the bottom plot: **"📈 Live UDP Throughput & Packet Loss Telemetry"**:
   - The green throughput curve locks stably at 6.0 Mbps.
   - The red packet loss line stays flat at 0.0%.
5. **What to say aloud:**
   > *"As soon as I start the stream, our multi-threaded UDP receiver on port 9999 begins catching datagrams. Notice how our throughput immediately locks at 6.0 Mbps with zero packet loss. Our receiver is calculating one-way transit latency by reading the 64-bit microsecond timestamp stamped into every packet header, showing approximately 5 milliseconds."*

---

### Step 4: Show Datagram Inspection in the Packet Stream Terminal
1. Switch to **Tab 2: "📟 Live Mininet Packet Stream Terminal"** (or click the orange **"🖥 Live OS Terminal"** button at the top header).
2. Show the real-time datagram logs:
   ```
   [12:15:30.142] [MAIN # 1045] Path-A | Size: 1024B | Q:  0/100 | FORWARDED
   [12:15:30.143] [MAIN # 1046] Path-A | Size: 1024B | Q:  0/100 | FORWARDED
   ```
3. Highlight the fields: Sequence Number (`#1045`), Packet Size (`1024B`), and Status (`FORWARDED`).
4. Point to the **translucent watermark `*D1`** in the bottom-right corner of the terminal and topology canvas.
5. **What to say aloud:**
   > *"Here in our packet terminal, you can inspect each individual datagram as it is serialized and dispatched. Every single packet is 1024 bytes, consisting of our custom 22-byte binary header followed by 1002 bytes of payload. We can see the sequence numbers incrementing with perfect continuity."*

---

## 2. Core D1 Viva Defense Questions & Answers

### Q1: Why did you choose UDP instead of TCP for this project?
**Answer:**
* TCP has built-in congestion control (AIMD, Reno, Cubic) that automatically throttles its congestion window (`cwnd`) when drops occur.
* UDP has **zero built-in congestion control, zero flow control, and zero retransmissions**. A UDP sender will blast packets blindly regardless of whether bottleneck queues are overflowing.
* Real-time applications (VoIP, video streaming, telemetry) require UDP because they cannot tolerate TCP retransmission delays. This makes UDP the ideal, mandatory protocol for demonstrating **Software-Defined Networking (SDN) dynamic traffic rerouting**: because endpoints cannot self-heal congestion, the network itself must step in.

### Q2: Explain the structure of your custom 22-byte binary protocol.
**Answer:**
We pack a compact C-style binary header using `struct.Struct("!4sIdHBBH")`:
1. `Magic (4B - b"SDN1")`: Validates datagram integrity and drops stray packets.
2. `Sequence Number (4B - uint32)`: Tracks packet order and enables sequence-based drop detection.
3. `Timestamp (8B - double)`: Records microsecond send time for one-way latency calculation.
4. `Flow ID (2B - uint16)`: Differentiates Flow 1 (Main) from Flow 2 (Cross-Traffic).
5. `Flags (1B)`: Signals `START (0x02)`, `DATA (0x01)`, `FIN (0x04)`, `FEEDBACK (0x10)`.
6. `Reserved (1B)`: 32-bit CPU memory alignment padding.
7. `Payload Length (2B)`: Length of trailing payload (1002 bytes $\rightarrow$ total 1024B packet).
Using network byte order (`!`) guarantees interoperability across Little-Endian and Big-Endian architectures.

### Q3: How do you prevent timer drift when pacing UDP packets at 6.0 Mbps?
**Answer:**
Standard `time.sleep()` drifts because OS process schedulers sleep slightly too long on each cycle. We implement **monotonic drift compensation** using `time.perf_counter()`:
$$\Delta t_{\text{pkt}} = \frac{\text{Packet Size (Bytes)} \times 8}{\text{Bitrate (bps)}} = \frac{1024 \times 8}{6{,}000{,}000} \approx 1.365\text{ ms}$$
On each packet, we compute `sleep_duration = next_send_time - time.perf_counter()`. If the OS slept too long on the previous packet, `sleep_duration` automatically shrinks on the next iteration, canceling out cumulative scheduling delay.

### Q4: How is RFC 3550 Inter-Arrival Jitter calculated?
**Answer:**
For consecutive packets $i$ and $j$, the difference in transit times is $D(i, j) = |(R_j - S_j) - (R_i - S_i)|$.  
The smoothed jitter estimate is updated using an exponential moving average low-pass filter ($\alpha = 1/16$):
$$J_i = J_{i-1} + \frac{D(i, j) - J_{i-1}}{16}$$

---

# ================================================================
# PART 2: DELIVERABLE 2 (D2 — ADVANCED DEMO & VIVA - 25 MARKS)
# ================================================================

## 1. D2 Step-by-Step Demonstration Walkthrough in the App

Follow these exact steps when demonstrating the **Deliverable 2 Advanced Functionality**:

### Step 1: Inject Congestion Burst and Observe Transport-Layer Impact
1. Ensure the Main UDP Stream is running at 6.0 Mbps on clean Path A.
2. Click the orange button: **`⚡ Inject Congestion (7M Burst on Path A)`**.
3. Point your finger to **"Category 2: Real-Time Socket Telemetry"**:
   - Watch **Overall Loss Rate** jump from `0.0%` to **`35% – 55%`**!
   - Watch **One-Way Latency** surge from `5.0 ms` up to **`90 – 120 ms`** due to bufferbloat in Switch $S_2$'s queue!
   - Watch **Throughput** drop from `6.0 Mbps` down to **`2.5 – 3.5 Mbps`**.
4. **What to say aloud:**
   > *"When I inject 7.0 Mbps of cross-traffic, total offered load hits 13.0 Mbps on our 10.0 Mbps bottleneck link. Because UDP has no built-in backpressure, the queue buffer saturates and drops excess packets. Notice our throughput collapses and latency spikes from 5 ms to over 100 ms due to severe bufferbloat."*

---

### Step 2: Observe Dynamic SDN Failover at the Transport Layer
1. Watch the dashboard as the SDN controller executes a dynamic reroute:
   - Point to the active path indicator switching from **`Path-A`** to **`Path-B`**.
   - Point to **One-Way Latency** shifting from `100+ ms` to **`~15.0 ms`** (reflecting Path B's physical distance).
   - Point to **Packet Loss** immediately dropping from `50%+` back to **`0.0%`**.
   - Point to **Throughput** bouncing back to full **`6.0 Mbps`**.
2. **What to say aloud:**
   > *"Notice how the receiver immediately detects the route change. As soon as traffic shifts to clean Path B, packet loss drops from 50% back to zero and throughput is fully restored. The slight increase in latency from 5 ms to 15 ms confirms our packets are physically traveling along Path B."*

---

### Step 3: Demonstrate Closed-Loop Rate Adaptation (SDN + Backpressure)
1. On the right-hand panel, find the checkbox: **`Enable Closed-Loop Rate Adaptation`** and check it.
2. Inject a prolonged congestion burst.
3. Show the evaluator how the receiver detects sustained loss and sends a `FLAG_FEEDBACK` packet back to sender port 9005.
4. Point to the sender adapting:
   - Main Send Rate automatically steps down from `6.0 Mbps` to `4.5 Mbps`, then to `3.5 Mbps`.
   - Once congestion clears, the rate probes back up toward `6.0 Mbps`.
5. Point to the **translucent watermark `*D2`** in the bottom-right corner of Tab 1 and Tab 4.
6. **What to say aloud:**
   > *"Under Deliverable 2, we have implemented Closed-Loop Rate Adaptation. When both paths experience congestion, our receiver sends feedback datagrams back to the sender on port 9005. The sender throttles its transmission rate to match available bottleneck capacity, demonstrating multi-layer transport and SDN coordination."*

---

## 2. Core D2 Viva Defense Questions & Answers

### Q5: How is multi-flow traffic generated and differentiated in your sockets?
**Answer:**
We implement two concurrent traffic flows:
- **Flow 1 (`FLOW_MAIN`):** 6.0 Mbps high-priority stream from $H_1$ to $H_2$ on port 9999.
- **Flow 2 (`FLOW_CROSS`):** 7.0 Mbps cross-traffic burst from $H_3$ to $H_4$ on port 9998, instantiated via `src/congestion_generator.py`.
Both flows pass through ingress port 9000. The 2-byte `Flow ID` field in our binary header allows switches and receivers to demultiplex and account for each flow independently.

### Q6: What is bufferbloat, and how does your telemetry detect it?
**Answer:**
Bufferbloat occurs when bottleneck switch buffers are oversized and remain persistently full during traffic surges. Packets sit in the queue waiting to be drained, adding excessive delay.
Our receiver detects bufferbloat by comparing the packet send timestamp against arrival time: under normal conditions latency is 5 ms (propagation delay), but under 13 Mbps congestion latency spikes to 90–120 ms because packets spend ~100 ms queuing inside the switch buffer before transmission.

### Q7: How does your Closed-Loop Rate Adaptation feedback mechanism work?
**Answer:**
When Rate Adaptation is enabled:
1. The receiver detects window packet loss exceeding 5.0%.
2. It constructs a 16-byte binary feedback packet with flag `FLAG_FEEDBACK (0x10)` containing the current loss rate and observed throughput.
3. The feedback packet is transmitted to the sender on feedback port 9005.
4. The sender scales back its rate ($\text{Rate} \times 0.75$) down to a safety floor of 2.0 Mbps, mitigating buffer overflow until the network stabilizes.
