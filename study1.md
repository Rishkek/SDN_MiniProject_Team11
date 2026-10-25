# Study Guide 1: Transport Layer, Low-Level UDP Sockets & Custom Binary Protocol

## Subsystem 1: Application Endpoints & Transport Layer Engineering
**Component Focus:** Socket Programming, Binary Datagram Protocol, Rate Pacing, and End-to-End Telemetry Measurement  
**Owned Project Files:**
- [`src/protocol.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/protocol.py) — Custom 22-byte binary protocol serialization/deserialization
- [`src/udp_sender.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/udp_sender.py) — Low-level rate-paced UDP client with monotonic timer
- [`src/udp_receiver.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/udp_receiver.py) — Multi-threaded telemetry receiver with sliding-window metrics
- [`src/congestion_generator.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/congestion_generator.py) — Cross-traffic burst injection engine

---

## 1. What This Subsystem Does (Plain English Overview)

In any computer network, switches, cables, and routers do not generate data by themselves—end-user applications do. This subsystem represents the **Endpoints** (the Sender and Receiver hosts) that sit at the edges of the network.

Think of this subsystem as the **traffic generator and performance auditor**:
1. **The Sender:** Acts like a high-speed courier that packs data boxes (UDP packets) and dispatches them onto the road at a strict, controlled speed (e.g., exactly 6.0 Mbps).
2. **The Custom Header:** Stamps a special 22-byte digital label onto every single box. This label tells the receiver which sequence number the box is, the microsecond it left the sender, and whether it is high-priority mission traffic or cross-traffic.
3. **The Receiver:** Sits at the destination endpoint, catches every arriving packet, and acts like a network doctor. By examining sequence numbers and timestamps, it calculates whether packets were lost on the road, how long they took to travel (one-way latency), and whether packet delivery was smooth or jittery (RFC 3550 jitter).
4. **The Congestion Generator:** Deliberately launches a massive flood of background traffic (7.0 Mbps) onto the same shared highway. Because 6.0 Mbps + 7.0 Mbps = 13.0 Mbps (which exceeds the 10.0 Mbps highway capacity), this intentionally triggers traffic congestion to test the network's resilience.

---

## 2. Behind the Scenes: How the Technology Works Step-by-Step

### A. What is a UDP Socket at the OS Level?
A network socket is an application's doorway to the operating system's networking stack:
* When Python calls `socket.socket(socket.AF_INET, socket.SOCK_DGRAM)`, the operating system allocates a kernel-level data structure for handling User Datagram Protocol (UDP) traffic.
* **Why UDP instead of TCP?**
  - TCP has built-in congestion control (like Cubic or Reno). If network congestion occurs, TCP senders automatically slow down by shrinking their congestion window (`cwnd`).
  - UDP has **zero built-in congestion control, zero flow control, and zero retransmissions**. A UDP application will pump datagrams as fast as the code instructs it, even if queues overflow and every packet gets dropped.
  - Real-time applications—such as live video streaming, VoIP phone calls, and gaming telemetry—use UDP because they cannot tolerate TCP retransmission delays. This makes UDP the ideal, mandatory protocol for demonstrating **Software-Defined Network (SDN) dynamic traffic rerouting**: because the endpoints cannot fix congestion on their own, the network itself must step in.

### B. Custom 22-Byte Binary Protocol Header (`src/protocol.py`)
Rather than sending unstructured text or slow, bloated JSON/XML strings, we engineer an ultra-compact **22-byte C-style binary header** packed in network byte order (Big-Endian).

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

#### Why Big-Endian (`!`) and Pre-Compiled `struct.Struct`?
1. **Network Byte Order (`!`):** Internet standards dictate that multi-byte integers are transmitted with the most significant byte first (Big-Endian). Using `!` ensures consistent binary interpretation whether running on an x86 Intel/AMD CPU (Little-Endian) or an ARM chip.
2. **Pre-Compiled `struct.Struct`:** Calling `struct.pack("!4sIdHBBH", ...)` on every single datagram causes Python to re-parse the format string millions of times. We pre-compile it once (`HEADER_STRUCT = struct.Struct("!4sIdHBBH")`), speeding up packet packing by **~2.8x**.

#### Breakdown of the Header Fields:
1. `Magic (4 Bytes - b"SDN1")`: A security and integrity tag. If stray packets from other programs hit our port, the receiver drops them immediately.
2. `Sequence Number (4 Bytes - unsigned int)`: Starts at 0 and counts up (0, 1, 2, 3...). If the receiver sees packet 10 arrive immediately after packet 7, it knows mathematically that 2 packets were lost in the network.
3. `Timestamp (8 Bytes - double float)`: Recorded using `time.time()` at the exact moment of transmission. When the receiver catches the packet, it subtracts the send time from the arrival time to measure **one-way latency**:
   $$\text{Latency} = (T_{\text{arrival}} - T_{\text{send}}) \times 1000\text{ ms}$$
4. `Flow ID (2 Bytes)`: Differentiates traffic types:
   - `FLOW_MAIN = 1` ($H_1 \rightarrow H_2$ primary high-priority stream)
   - `FLOW_CROSS = 2` ($H_3 \rightarrow H_4$ congestion burst traffic)
5. `Flags (1 Byte)`: Bitmask flags signaling lifecycle events: `FLAG_START (0x02)`, `FLAG_DATA (0x01)`, `FLAG_FIN (0x04)`, and `FLAG_FEEDBACK (0x10)`.
6. `Reserved (1 Byte)`: Alignment byte to keep memory on 32-bit word boundaries.
7. `Payload Length (2 Bytes)`: The byte count of the dummy payload following the header.

---

### C. Rate Pacing & Monotonic Drift Compensation (`src/udp_sender.py`)
Transmitting data at a target rate (e.g., 6.0 Mbps) is harder than it sounds. If a program simply does `time.sleep(interval)` in a loop, standard OS schedulers introduce **timer drift**—sleeping slightly too long on every packet, resulting in an actual rate far lower than requested.

To solve this, our sender implements **monotonic drift compensation**:
```python
next_send_time += self._packet_interval
sleep_duration = next_send_time - time.perf_counter()
if sleep_duration > 0.0005:
    time.sleep(sleep_duration)
elif sleep_duration < -0.05:
    # Lagging by >50ms, resynchronize clock baseline
    next_send_time = time.perf_counter()
```
- We calculate the time interval between packets:
  $$\text{Interval (s)} = \frac{\text{Packet Size (Bytes)} \times 8}{\text{Target Rate (bps)}}$$
  For 1024-byte packets at 6.0 Mbps, a packet must be dispatched every **1.365 milliseconds**.
- We use `time.perf_counter()` because it is strictly monotonic and unaffected by system clock adjustments.
- If the OS scheduler sleeps too long on one iteration, `sleep_duration` becomes smaller on the next iteration, automatically catching up and eliminating cumulative drift.

---

### D. Receiver Telemetry & Sliding Window Metrics (`src/udp_receiver.py`)
The receiver uses a dedicated worker thread running a high-speed socket loop:
1. **OS Receive Buffer Tuning:** We explicitly expand the socket buffer to 2 MB using `SO_RCVBUF`. Standard OS buffers (64 KB) can easily overflow during 10 Mbps bursts, dropping packets inside the host before Python reads them.
2. **RFC 3550 Inter-Arrival Jitter Calculation:**
   Jitter measures the statistical variance (instability) of packet delivery times. High jitter causes robotic voices in VoIP and stuttering in video streams. We implement the RFC 3550 standard algorithm:
   - For consecutive packets $i$ and $j$, calculate the difference in transit times:
     $$D(i, j) = |(R_j - S_j) - (R_i - S_i)|$$
   - Smooth the jitter estimate using an exponential moving average low-pass filter ($\alpha = 1/16$):
     $$J = J + \frac{D(i, j) - J}{16}$$
3. **Sliding Window Telemetry:**
   Every 500 ms, the receiver flushes a telemetry snapshot:
   - $\text{Throughput (Mbps)} = \frac{\text{Window Bytes} \times 8}{\Delta t \times 10^6}$
   - $\text{Packet Loss Rate (\%)} = \frac{\text{Lost Packets}}{\text{Received Packets} + \text{Lost Packets}} \times 100\%$

---

## 3. How Subsystem 1 Complements the Other Two Subsystems

```
+-------------------------------------------------------------------------------+
|                        THE THREE-PART FEEDBACK LOOP                           |
+-------------------------------------------------------------------------------+

[Subsystem 1: UDP Sockets]
       |
       | 1. Pumps 6.0 Mbps Main UDP Stream + 7.0 Mbps Congestion Burst
       v
[Subsystem 2: Network Infrastructure & Virtual Switches]
       |
       | 2. Bottleneck Link (10 Mbps capacity, 100-packet buffer) hits 13 Mbps
       | 3. Queue overflows -> physical tail-drop packet loss begins
       | 4. Switch S1 records rising tx_bytes on Port 2
       v
[Subsystem 3: SDN Controller & Telemetry]
       |
       | 5. Polls Port 2 counters, calculates load = 13.0 Mbps >= 8.0 Mbps threshold
       | 6. Sends OpenFlow FlowMod instruction to Switch S1
       v
[Subsystem 2: Switch S1 Forwarding Table Updated]
       |
       | 7. Main stream redirected from Port 2 (Path A) to Port 3 (Path B)
       v
[Subsystem 1: UDP Receiver Endpoint]
       |
       | 8. Detects immediate recovery: packet loss drops from 55% back to 0.0%
       +------------------------------------------------------------------------+
```

1. **Complementing Subsystem 2 (Network Infrastructure):**
   - Subsystem 2 builds the virtual switches ($S_1, S_2, S_3, S_4$) and the 10 Mbps bottleneck links. Without Subsystem 1's socket programs, the network is an empty shell with no traffic.
   - When Subsystem 2's bottleneck link queue fills up, Subsystem 1's receiver is what mathematically measures the resulting packet loss and latency changes.
2. **Complementing Subsystem 3 (SDN Control Plane):**
   - Subsystem 3 needs traffic to monitor. Subsystem 1 generates the 6.0 Mbps stream and injects the 7.0 Mbps cross-traffic burst that triggers Subsystem 3's 8.0 Mbps threshold breach.
   - When Subsystem 3 executes a dynamic reroute, Subsystem 1's receiver provides the definitive proof of success: throughput is restored to 6.0 Mbps, and packet loss drops to zero.

---

## 4. Key Libraries & Why They Were Chosen

| Library / Module | Purpose in Subsystem 1 | Technical Justification |
| :--- | :--- | :--- |
| **`socket`** (Standard Library) | Creates raw UDP datagram sockets (`AF_INET`, `SOCK_DGRAM`), sets socket options (`SO_RCVBUF`, `SO_SNDBUF`). | Satisfies the requirement for low-level socket programming without relying on heavy third-party application abstractions. |
| **`struct`** (Standard Library) | Serializes binary numbers and byte strings into exact C-style struct memory blocks (`struct.Struct`). | Blazing fast $O(1)$ packing time with zero string parsing. Uses only 22 bytes per packet compared to 200+ bytes for JSON. |
| **`time.perf_counter`** | Nanosecond-resolution monotonic clock for rate pacing. | Unlike `time.time()`, it never jumps backwards when the OS synchronizes time via NTP, preventing packet burst artifacts. |
| **`threading`** | Runs packet transmission and socket receiving concurrently. | Prevents console logging or file I/O from blocking the time-critical packet reception loop. |
