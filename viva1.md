# Viva Defense & Demonstration Guide 1: Transport Layer & Socket Programming

**Complements:** [`study1.md`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/study1.md)  
**Topic Focus:** Low-Level UDP Sockets, 22-Byte Binary Protocol, Precise Rate Pacing, Receiver Telemetry, and Cross-Traffic Injection  
**Relevant Code Files:** `src/protocol.py`, `src/udp_sender.py`, `src/udp_receiver.py`, `src/congestion_generator.py`

---

## 1. Written Instructions: How to Demonstrate This Subsystem in the App

When it is your turn to present or defend the Transport Layer and Socket Programming subsystem, follow this exact step-by-step procedure:

### Step 1: Launch the Application
Open PowerShell or Terminal and start the GUI dashboard:
```powershell
python run.py
```
*(Point out to the evaluator that the dashboard initializes clean sockets bound to localhost `127.0.0.1` on ports `9000` (ingress), `9999` (main receiver), and `9998` (cross-traffic receiver).)*

---

### Step 2: Show the Category 2 Stream Controls & Set Sending Rate
1. Look at the right-hand panel of **Tab 0 ("🌐 Live Visual Topology & Stream Control")**.
2. Find the **"Main Send Rate"** slider under *Network Parameters & Stream Controls*.
3. Drag the slider to **`6.0 Mbps`** (the baseline mission-critical sending rate).
4. **What to say aloud:**
   > *"Here in our application layer controls, we have implemented a high-precision UDP sender. Notice that we are not using any high-level HTTP wrappers or requests libraries. We are programming directly against low-level BSD sockets using Python's native `socket` library. I am configuring our main traffic stream to transmit at exactly 6.0 Mbps."*

---

### Step 3: Start the Main UDP Stream
1. Click the green button: **`▶ Start Main UDP Stream`**.
2. Notice the button turns pink and changes to **`⏹ Stop Main UDP Stream`**.
3. Point your finger to the bottom right: **"Category 2: Real-Time Socket Telemetry"**:
   - **Live Throughput:** Rises smoothly to **`5.9 – 6.0 Mbps`**.
   - **Goodput:** Displays **`~5.8 Mbps`** (raw payload rate excluding protocol headers).
   - **One-Way Latency:** Reads **`~5.0 ms`** (the physical propagation delay of Path A).
   - **RFC 3550 Jitter:** Shows a tight, stable value under **`0.5 ms`**.
   - **Packet Counters:** The `Recv` counter increments rapidly by hundreds of packets every second with `Lost: 0`.
4. Point to the bottom plot: **"📈 Live UDP Throughput & Packet Loss Telemetry"**:
   - The green throughput curve locks stably at 6.0 Mbps.
   - The red packet loss line stays flat at 0%.
5. **What to say aloud:**
   > *"As soon as I start the stream, our multi-threaded UDP receiver on port 9999 begins catching datagrams. Notice how our throughput immediately locks at 6.0 Mbps with zero packet loss. Our receiver is calculating one-way transit latency by reading the 64-bit microsecond timestamp stamped into every packet header, showing approximately 5 milliseconds."*

---

### Step 4: Show the Live Datagram Stream in the Terminal
1. Click on **Tab 2: "📟 Live Mininet Packet Stream Terminal"** (or click the orange **"🖥 Live OS Terminal"** button at the top header).
2. Show the real-time datagram logs streaming across the screen:
   ```
   [12:15:30.142] [MAIN # 1045] Path-A | Size: 1024B | Q:  0/100 | FORWARDED
   [12:15:30.143] [MAIN # 1046] Path-A | Size: 1024B | Q:  0/100 | FORWARDED
   ```
3. Highlight the fields: Sequence Number (`#1045`), Packet Size (`1024B`), and Status (`FORWARDED`).
4. **What to say aloud:**
   > *"Here in our packet terminal, you can inspect each individual datagram as it is serialized and dispatched. Every single packet is 1024 bytes, consisting of our custom 22-byte binary header followed by 1002 bytes of payload. We can see the sequence numbers incrementing with perfect continuity."*

---

### Step 5: Demonstrate Closed-Loop Rate Adaptation (Optional Bonus Feature)
1. Switch back to **Tab 0**.
2. Click the button: **`UDP Rate Adaptation: OFF`** to turn it **`ON`**.
3. **What to say aloud:**
   > *"While standard UDP has no flow control, we also engineered an optional closed-loop rate adaptation mechanism. The receiver computes sliding-window loss and transmits periodic feedback datagrams (`FLAG_FEEDBACK = 0x10`) back to the sender on port 9005. If packet loss exceeds 5%, the sender performs a multiplicative rate decrease (-30%) to relieve pressure on the network."*

---

## 2. Core Concepts You Must Master

1. **Why UDP over TCP:**
   - TCP has built-in congestion control (AIMD/Cubic). Senders back off automatically when packets drop.
   - UDP is connectionless and unthrottled. It will blindly flood a link, causing severe queue overflows. Real-world applications like live video, VoIP, and telemetry require UDP because retransmissions cause unacceptable lag. This is why an external SDN controller is necessary.
2. **The 22-Byte Protocol Header:**
   - Format: `!4s I d H B B H` (Magic `SDN1`, 32-bit Seq Num, 64-bit Timestamp, 16-bit Flow ID, 8-bit Flags, 8-bit Reserved, 16-bit Payload Length).
   - Pre-compiled with `struct.Struct` for $O(1)$ packing speed. Big-Endian network byte order (`!`).
3. **Drift-Compensated Pacing:**
   - Interval between packets = $(\text{Packet Size} \times 8) / \text{Target Rate}$.
   - Monotonic timer (`time.perf_counter()`) prevents cumulative clock drift caused by OS scheduler sleep quantization.
4. **RFC 3550 Inter-Arrival Jitter:**
   - Difference in transit times: $D(i, j) = |(R_j - S_j) - (R_i - S_i)|$.
   - Smoothed with low-pass filter: $J = J + \frac{D(i, j) - J}{16}$.

---

## 3. Top Expected Viva Questions & Winning Answers

### Q1: Why did you design a custom binary protocol instead of sending JSON or plain text?
**Answer:**
> *"Sending JSON or plain text over UDP is inefficient for high-speed network telemetry. JSON requires string encoding, delimiters, and parsing on every packet, introducing significant CPU overhead and ballooning header size to over 150–200 bytes. Our custom binary protocol is exactly 22 bytes. Using Python's pre-compiled `struct.Struct`, packing and unpacking is an $O(1)$ memory copy operation that runs in microseconds, preserving bandwidth and maximizing throughput."*

---

### Q2: How does your receiver calculate packet loss if UDP has no acknowledgments (ACKs)?
**Answer:**
> *"Because UDP has no ACKs, the receiver relies on the 32-bit Sequence Number embedded in our custom header. The sender increments this sequence number monotonically on every packet (0, 1, 2, 3...). The receiver tracks the expected sequence number. If packet #100 arrives and the next packet is #105, the receiver immediately registers that 4 packets were lost in the network. The loss percentage is calculated over a rolling 500 ms window as $\frac{\text{Lost}}{\text{Received} + \text{Lost}} \times 100\%$."*

---

### Q3: How do you measure one-way latency, and how do you handle clock synchronization?
**Answer:**
> *"At the instant before `socket.sendto()` is called, the sender records the epoch timestamp in microseconds using `time.time()` and packs it into the 8-byte double field of the header. Upon arrival, the receiver records arrival time and subtracts: $\text{Latency} = (T_{\text{recv}} - T_{\text{send}}) \times 1000\text{ ms}$. In a distributed physical setup, clocks are synchronized using PTP (Precision Time Protocol) or NTP. In our local Mininet emulation, both hosts share the same underlying system hardware clock, providing microsecond-level accuracy without clock skew."*

---

### Q4: Why did you tune the socket buffers using `SO_SNDBUF` and `SO_RCVBUF`?
**Answer:**
> *"Default OS socket buffers can be as small as 64 KB. At high transmission rates (6 to 13 Mbps), an OS thread context switch can cause a temporary delay in reading the socket. If the socket buffer is only 64 KB, it fills up in under 40 milliseconds, causing the OS kernel to drop packets locally before they ever touch the network. We tuned `SO_SNDBUF` to 1 MB and `SO_RCVBUF` to 2 MB, guaranteeing that all observed packet drops are true physical drops caused by network queue bottleneck saturation, not OS buffer starvation."*

---

## 4. Examiner Trap Questions ("Gotchas") & How to Defend Them

### Trap 1: "Why don't you use `time.sleep()` directly to pace packets?"
**Your Defense:**
> *"Calling `time.sleep()` directly causes cumulative timing drift. On Windows and Linux, `time.sleep()` has a minimum scheduling granularity of 1 to 15 milliseconds. If our target packet interval is 1.36 milliseconds, sleeping for 2 milliseconds on each packet would throttle our transmission to under 4 Mbps instead of 6 Mbps. We use monotonic drift compensation with `time.perf_counter()`, where any excess sleep on packet $N$ is deducted from the target wake time of packet $N+1$, maintaining an exact 6.0 Mbps average."*

### Trap 2: "If UDP is unreliable, how do you know your telemetry feedback datagrams aren't lost?"
**Your Defense:**
> *"Rate-adaptation feedback datagrams are transmitted periodically every 500 milliseconds. Because network conditions change continuously, feedback is treated as a continuous stream of state updates rather than a transactional command. Even if a single feedback packet is dropped, the subsequent snapshot arrives 500 milliseconds later. This design avoids the head-of-line blocking that TCP ACK retransmissions would introduce."*
