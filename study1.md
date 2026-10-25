# Study Guide 1: Transport Layer, Low-Level UDP Sockets & Protocol Engineering

**Component Focus:** Socket Programming, Binary Datagram Protocol, Rate Pacing, Multi-Flow Traffic Generation, and End-to-End Telemetry  
**Owned Project Files:**
- [`src/protocol.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/protocol.py) — Custom 22-byte binary protocol serialization/deserialization
- [`src/udp_sender.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/udp_sender.py) — Low-level rate-paced UDP client with monotonic timer
- [`src/udp_receiver.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/udp_receiver.py) — Multi-threaded telemetry receiver with sliding-window metrics
- [`src/congestion_generator.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/congestion_generator.py) — Cross-traffic burst injection engine

---

# ================================================================
# PART 1: DELIVERABLE 1 (D1 — FOUNDATION - 15 MARKS)
# ================================================================

## 1. What to Explain for Deliverable 1
In Deliverable 1, your role is to explain **how end-hosts talk across the network at the raw socket level** before any congestion occurs:
1. How we created raw BSD sockets using Python's native `socket` library without high-level wrappers.
2. Why we chose UDP over TCP for real-time mission traffic.
3. How we engineered a custom 22-byte binary protocol header using `struct.Struct` in Big-Endian network byte order.
4. How the sender accurately paces traffic at exactly 6.0 Mbps without timer drift.
5. How the receiver measures sequence continuity, one-way latency ($T_{\text{recv}} - T_{\text{send}}$), and RFC 3550 jitter.

---

## 2. D1 Behind the Scenes: How the Sockets Work Step-by-Step

### A. Raw UDP Socket Creation at the OS Level
When the application starts, it creates a UDP socket:
```python
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
```
* `AF_INET`: Specifies IPv4 addressing.
* `SOCK_DGRAM`: Specifies connectionless User Datagram Protocol (UDP).
* **Why UDP instead of TCP?**
  - TCP has built-in congestion control (AIMD, Reno, Cubic). When packets are dropped, TCP senders throttle themselves back.
  - UDP has **zero built-in congestion control, zero flow control, and zero retransmissions**. A UDP sender blasts packets regardless of network state.
  - Real-time applications (VoIP, video conferencing, live telemetry) require UDP because they cannot tolerate TCP retransmission stalls. Because UDP endpoints cannot self-heal congestion, an external intelligence layer (SDN) is required.

---

### B. Custom 22-Byte Binary Protocol Header (`src/protocol.py`)
Rather than sending slow, heavy JSON or text strings, every packet contains an ultra-compact **22-byte C-style binary header** packed in Big-Endian network byte order:

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

#### Detailed Header Breakdown:
1. **Magic (`4 Bytes - b"SDN1"`):** Packet validation tag. Rejects stray or malformed packets from other processes immediately.
2. **Sequence Number (`4 Bytes - uint32`):** Starts at 0 and increments sequentially (`0, 1, 2, 3...`). Enables the receiver to detect lost or out-of-order packets.
3. **Timestamp (`8 Bytes - double float`):** High-precision transmission time recorded with `time.time()`. Receiver subtracts this from arrival time to compute **one-way latency**:
   $$\text{Latency} = (T_{\text{arrival}} - T_{\text{send}}) \times 1000\text{ ms}$$
4. **Flow ID (`2 Bytes`):** Identifies traffic streams:
   - `FLOW_MAIN = 1` ($H_1 \rightarrow H_2$ primary stream)
   - `FLOW_CROSS = 2` ($H_3 \rightarrow H_4$ cross-traffic burst)
5. **Flags (`1 Byte`):** Bitmask signaling lifecycle states: `FLAG_START (0x02)`, `FLAG_DATA (0x01)`, `FLAG_FIN (0x04)`, `FLAG_FEEDBACK (0x10)`.
6. **Reserved (`1 Byte`):** Padding byte for 32-bit CPU memory alignment.
7. **Payload Length (`2 Bytes`):** Size of dummy payload following the header (typically 1002 bytes, making the entire datagram 1024 bytes).

#### Why Big-Endian (`!`) and Pre-Compiled `struct.Struct`?
* **Network Byte Order (`!`):** Mandates that multi-byte integers are transmitted with the most significant byte first, guaranteeing identical packet parsing across x86 (Little-Endian) and ARM CPUs.
* **Pre-compiled `struct.Struct("!4sIdHBBH")`:** Avoids re-parsing format strings on every packet, speeding up serialization by **~2.8x**.

---

### C. Rate Pacing & Monotonic Drift Compensation (`src/udp_sender.py`)
To maintain an exact transmission rate (e.g., 6.0 Mbps), the sender calculates inter-packet interval:
$$\text{Interval} = \frac{\text{Packet Size (Bytes)} \times 8}{\text{Target Rate (bps)}} = \frac{1024 \times 8}{6{,}000{,}000} \approx 1.365\text{ ms}$$

Standard OS timers drift over time. Our sender uses **monotonic drift compensation** with `time.perf_counter()`:
```python
next_send_time += self._packet_interval
sleep_duration = next_send_time - time.perf_counter()
if sleep_duration > 0.0005:
    time.sleep(sleep_duration)
elif sleep_duration < -0.05:
    next_send_time = time.perf_counter() # Resync clock if lagging
```
This guarantees an unwavering 6.0 Mbps data rate without cumulative timer lag.

---

### D. Receiver Telemetry & Sliding-Window Metrics (`src/udp_receiver.py`)
The receiver runs a dedicated thread listening on port 9999 with an expanded **2 MB socket buffer** (`SO_RCVBUF`):
1. **Packet Loss Detection:** Compares arriving `seq` against `expected_seq`:
   $$\text{Dropped Packets} = \text{seq} - \text{expected\_seq}$$
2. **RFC 3550 Inter-Arrival Jitter:**
   For consecutive packets $i$ and $j$, transit difference is $D(i, j) = |(R_j - S_j) - (R_i - S_i)|$.  
   Jitter is smoothed using a low-pass filter ($\alpha = 1/16$):
   $$J_i = J_{i-1} + \frac{D(i, j) - J_{i-1}}{16}$$
3. **Sliding-Window Throughput:**
   Calculated over 500 ms sampling windows:
   $$\text{Throughput (Mbps)} = \frac{\text{Window Bytes} \times 8}{\Delta t \times 10^6}$$

---

# ================================================================
# PART 2: DELIVERABLE 2 (D2 — ADVANCED FUNCTIONALITY - 25 MARKS)
# ================================================================

## 1. What to Explain for Deliverable 2
In Deliverable 2, your role is to explain **what happens when the network experiences overload and how the transport layer interacts with advanced SDN capabilities**:
1. How multi-flow traffic is generated using the Cross-Traffic Congestion Generator.
2. How injecting 7.0 Mbps of cross-traffic causes total offered load to hit 13.0 Mbps (130% of link capacity).
3. Why UDP traffic collapses without SDN (bufferbloat, tail drop, >50% packet loss).
4. How the receiver measures sub-second recovery when the SDN Controller redirects the flow to Path B.
5. How client-side Closed-Loop Rate Adaptation works when both paths are congested.

---

## 2. D2 Behind the Scenes: Advanced Mechanics Step-by-Step

### A. Multi-Flow Cross-Traffic Burst Generator (`src/congestion_generator.py`)
To test network resilience, we launch a secondary sender:
* Binds to a separate socket and injects packets tagged with `FLOW_CROSS = 2` directed to port 9000 (ingress switch).
* Generates **7.0 Mbps** of unyielding UDP traffic during the congestion burst window.
* Combined load on Path A:
  $$\text{Total Offered Load} = 6.0\text{ Mbps (Main)} + 7.0\text{ Mbps (Cross)} = 13.0\text{ Mbps}$$
  This is **130%** of the 10.0 Mbps bottleneck link capacity.

---

### B. What Happens to UDP Under Congestion (Without SDN Rerouting)
Because UDP has no congestion window:
1. Switch queues fill to capacity (100 packets), causing **bufferbloat** (latency spikes from 5 ms to 100+ ms).
2. Excess packets are discarded at the switch via **tail drop**.
3. The receiver records:
   - Packet loss surging to **35% - 55%**.
   - Throughput collapsing from 6.0 Mbps down to **2.5 - 3.5 Mbps**.
   - Jitter fluctuating erratically due to varying queue wait times.

---

### C. Observing Dynamic SDN Recovery at the Receiver
When the SDN Controller detects congestion and executes an OpenFlow `FlowMod` to Path B:
1. Main packets immediately begin arriving via Path B.
2. Sequence continuity resumes: packet loss drops instantly back to **0.0%**.
3. Throughput restores to full **6.0 Mbps**.
4. One-way latency shifts to **~15.0 ms** (reflecting Path B's physical link delay), confirming the route change occurred.

---

### D. Closed-Loop Rate Adaptation (SDN + Source Throttling)
In extreme scenarios where both Path A and Path B are congested:
* The receiver detects sustained packet loss even after rerouting.
* The receiver sends a lightweight **Feedback Packet (`FLAG_FEEDBACK`)** back to the sender on port 9005.
* Upon receiving feedback, the sender dynamically scales back its sending rate:
  $$\text{New Rate} = \max(2.0\text{ Mbps}, \text{Current Rate} \times 0.75)$$
* Once congestion subsides, the sender gradually probes upward back to nominal rate, demonstrating **transport-level closed-loop backpressure**.

---

## 3. How Subsystem 1 Complements the Other Two Subsystems

```
[Subsystem 1: UDP Endpoints]
       |
       | 1. Generates 6.0 Mbps Main Stream + 7.0 Mbps Cross Burst
       v
[Subsystem 2: Network Infrastructure & Virtual Switches]
       |
       | 2. Bottleneck Link (10 Mbps, 100-pkt queue) hits 13 Mbps
       | 3. Buffer overflows -> tail-drop packet loss begins
       | 4. Switch S1 records rising tx_bytes on Port 2
       v
[Subsystem 3: SDN Controller & Telemetry]
       |
       | 5. Polls Port 2 counters, detects load >= 8.0 Mbps threshold
       | 6. Sends OpenFlow FlowMod instruction to Switch S1
       v
[Subsystem 2: Switch S1 Forwarding Table]
       |
       | 7. Main stream redirected from Port 2 (Path A) to Port 3 (Path B)
       v
[Subsystem 1: UDP Receiver Endpoint]
       |
       | 8. Detects immediate recovery: packet loss drops from 50%+ back to 0.0%
```

---

## 4. Key Libraries & Technical Justifications

| Library / Module | Purpose in Subsystem 1 | Technical Justification |
| :--- | :--- | :--- |
| **`socket`** (Standard Library) | Creates raw UDP sockets (`AF_INET`, `SOCK_DGRAM`), sets socket options (`SO_RCVBUF`, `SO_SNDBUF`). | Satisfies the requirement for low-level socket programming without relying on high-level HTTP abstractions. |
| **`struct`** (Standard Library) | Serializes binary numbers and byte strings into exact C-style struct memory blocks (`struct.Struct`). | Blazing fast $O(1)$ packing time with zero string parsing. Uses only 22 bytes per packet compared to 200+ bytes for JSON. |
| **`time.perf_counter`** | Nanosecond-resolution monotonic clock for rate pacing. | Unlike `time.time()`, it never jumps backwards when the OS synchronizes time via NTP, preventing packet burst artifacts. |
| **`threading`** | Runs packet transmission and socket receiving concurrently. | Prevents console logging or file I/O from blocking the time-critical packet reception loop. |
