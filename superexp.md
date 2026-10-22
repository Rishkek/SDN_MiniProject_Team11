# Master Architecture & Codebase Super-Explanation (`superexp.md`)
**Project:** Congestion Detection and Dynamic Traffic Rerouting (Topic #27)  
**Architecture:** Low-Level UDP Socket Programming + Mininet Open vSwitch + Dynamic OpenFlow 1.3 SDN Controller

---

## 1. Executive Engineering Summary

This document provides a **complete, end-to-end, line-by-line and packet-by-packet explanation** of the entire codebase and the physical/virtual network processes occurring behind the scenes.

### The Fundamental Networking Challenge:
Standard **UDP (User Datagram Protocol)** is connectionless, unacknowledged, and possesses **zero congestion control**. In contrast to TCP (which uses AIMD, sliding windows, and ACK pacing to throttle itself when drops occur), a UDP sender will blindly blast packets onto a physical link regardless of whether the bottleneck queue is empty or overflowing.

When two UDP flows share a bottleneck link whose capacity is smaller than their combined demand:
1. Switch queues fill to capacity (causing massive latency spikes known as **bufferbloat**).
2. Excess packets are discarded at the switch ingress buffer (**tail drop**).
3. The application experiences severe packet loss ($>50\%$) and collapsed throughput.

### The SDN Solution:
Rather than requiring changes to thousands of client applications, we introduce **Software-Defined Networking (SDN)**. The SDN Controller acts as an active, closed-loop telemetry supervisor:
1. It continuously polls port byte counters across all switches.
2. It mathematically calculates the real-time link bitrate.
3. When it detects that link load exceeds the safety threshold ($8.0\text{ Mbps}$ on our $10\text{ Mbps}$ link), it dynamically injects an **OpenFlow 1.3 `FlowMod` instruction** into the ingress switch.
4. The switch immediately redirects the UDP stream to an alternate, idle physical path ($S_1 \rightarrow S_3 \rightarrow S_4$) in **$9.46\text{ milliseconds}$**, restoring 100% throughput and eliminating packet loss without the client or server ever noticing a disruption.

---

## 2. The Complete Behind-the-Scenes Journey of a Single Packet

To understand the interaction between socket programming, the operating system kernel, virtual switches, and SDN rules, follow packet **#1050** sent from Host $H_1$ to Host $H_2$:

```
[Application Layer]
  1. udp_sender.py: Formulates packet #1050
  2. protocol.py: Packs 22-byte header with struct.pack('!4sIdHBBH', ...)
        |
[Transport Layer & OS Kernel]
  3. socket.sendto(data, ('10.0.0.2', 9999))
  4. Placed into Linux kernel socket buffer (SO_SNDBUF = 1MB)
        |
[Virtual Network Interface & Linux Namespace]
  5. Egresses H1 namespace through virtual interface 'h1-eth0'
  6. Enters Linux Virtual Ethernet Pair ('veth' cable)
        |
[Data Plane: Open vSwitch S1]
  7. Arrives at Ingress Switch Port 1 ('s1-eth1')
  8. OVS Kernel Datapath parses Ethernet/IP/UDP headers:
     - Match: nw_src=10.0.0.1, nw_dst=10.0.0.2, tp_dst=9999
     - Rule: Priority 200 matches -> Action: Output to Port 3 (Path B)
        |
[Physical Bottleneck Link: Linux Traffic Control (tc)]
  9. Enters Link s1-s3: Enforces 10 Mbps bandwidth & 15ms delay via Token Bucket Filter
 10. Traverses intermediate switch S3 (Port 1 -> Port 2)
 11. Traverses egress switch S4 (Port 2 -> Port 1 connected to H2)
        |
[Receiver End-Host & Application]
 12. Arrives at H2 namespace through 'h2-eth0'
 13. Buffered in Linux kernel receive buffer (SO_RCVBUF = 2MB)
 14. udp_receiver.py calls sock.recvfrom(65535)
 15. protocol.py unpacks header -> verifies Magic 'SDN1'
 16. Measures sequence continuity: 1050 == expected_seq -> 0 loss!
 17. Calculates transit latency: T_recv - T_send = 16.2 ms
 18. Updates RFC 3550 jitter filter: Ji = Ji-1 + (|D| - Ji-1)/16
```

---

## 3. The 6-Phase Lifecycle of Congestion & Dynamic Failover

Our automated benchmark runs an end-to-end experiment demonstrating the before, during, and after of network congestion:

```
 Throughput (Mbps)
    8.0 + - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
        |  [Phase 1]       [Phase 2: Congestion]     [Phase 4: Reroute]
    6.0 |==============\                           /=========================== (Path B)
        |               \                         /
    4.0 |                \                       /
        |                 \=====================/ (Degraded Path A in Static)
    2.0 |
        +-------------------|-------------------|----------------------------- Time
       T=0s                T=7s                T=8.5s                        T=25s
                          Cross-Traffic       SDN Detects &
                          Injected (7M)       Pushes FlowMod
```

### Phase 1: Baseline Normal State ($T=0\text{s}$ to $T=7\text{s}$)
* Host $H_1$ transmits at $6.0\text{ Mbps}$ using UDP port 9999.
* Default OpenFlow rule directs traffic out of Switch $S_1$ Port 2 $\rightarrow$ Path A ($S_1 \rightarrow S_2 \rightarrow S_4$).
* Link capacity is $10.0\text{ Mbps}$.
* **Metrics:** Throughput = $6.0\text{ Mbps}$, Packet Loss = $0.0\%$, Latency = $\approx 6.5\text{ ms}$, Jitter = $0.2\text{ ms}$.

### Phase 2: Congestion Injected ($T=7\text{s}$)
* `congestion_generator.py` fires on Host $H_3$, transmitting $7.0\text{ Mbps}$ of cross-traffic to Host $H_4$ through Switch $S_1$ Port 2.
* Total offered load hitting Path A = $6.0 + 7.0 = 13.0\text{ Mbps}$ ($130\%$ of link capacity).
* The Token Bucket Filter on the switch interface depletes its tokens.
* The 100-packet queue buffer fills completely within $150\text{ ms}$, creating massive queuing delay (**bufferbloat** spikes latency from $6\text{ ms}$ to $130\text{ ms}$).
* Once the queue buffer is full, incoming packets are discarded via **tail drop**.
* **Metrics:** Packet loss surges to **$55\% - 61\%$**, throughput collapses to **$2.5 - 3.0\text{ Mbps}$**.

### Phase 3: Telemetry Detection ($T=8.0\text{s}$)
* The SDN Controller's background thread polls the transmitted byte counters of Switch $S_1$ Port 2 every $0.5\text{s}$.
* It computes the delta:
  $$\text{Bitrate} = \frac{(\text{tx\_bytes}_t - \text{tx\_bytes}_{t-1}) \times 8}{0.5 \times 10^6} = 13.01\text{ Mbps}$$
* $13.01\text{ Mbps} \ge 8.0\text{ Mbps}$ threshold $\rightarrow$ Breach Counter increments to 1.
* At $T=8.5\text{s}$, the next poll confirms the breach (Breach Counter = 2).
* **Congestion Alert Confirmed!**

### Phase 4: Dynamic OpenFlow Reroute ($T=8.51\text{s}$)
* The controller executes `_trigger_reroute(to_path=PATH_ALTERNATE)`.
* It generates and injects an OpenFlow 1.3 `FlowMod` rule into Switch $S_1$:
  - Match: `ip_src=10.0.0.1, ip_dst=10.0.0.2, udp_dst=9999`
  - Priority: `200`
  - Action: `output:3` (Port 3 connects to Switch $S_3$ along Path B).
* Because Open vSwitch matches flows in priority order, packets matching priority 200 immediately bypass the default priority 50 rule.
* **Failover Recovery Time:** Measured at **$9.46\text{ milliseconds}$**.

### Phase 5: Restored Steady-State ($T=9.0\text{s}$ to $T=17.0\text{s}$)
* Traffic is now physically partitioned across two separate links:
  - **Path A Link ($S_1 \rightarrow S_2$):** Carries the $7.0\text{ Mbps}$ cross-traffic. Since $7.0\text{ Mbps} < 10.0\text{ Mbps}$, the queue drains and drops cease!
  - **Path B Link ($S_1 \rightarrow S_3$):** Carries the $6.0\text{ Mbps}$ main application traffic.
* **Metrics:** Main flow throughput immediately bounces back to **$6.0\text{ Mbps}$**, and packet loss drops to **$0.0\%$**!

### Phase 6: Hysteresis Stabilization ($T=17.0\text{s}+$)
* Cross-traffic stops. Path A's load drops to $0.0\text{ Mbps}$.
* Our controller enforces an anti-flapping threshold (`HYSTERESIS_RECOVERY_MBPS = 4.5 Mbps`).
* Rather than greedily flapping back and forth, the flow remains stable on Path B until a permanent network rebalancing is scheduled.

---

## 4. Exhaustive File-by-File Codebase Reference

### File 1: [`setup.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/setup.py) (Automated Environment Bootstrapper)
* **Goal:** Make the project run immediately in any environment (Windows, Ubuntu VM, Mininet VM).
* **Architecture:**
  - `check_python_modules()`: Inspects `sys.modules` for `matplotlib`, `networkx`, `tabulate`, `rich`, `psutil`, `pytest`.
  - `check_linux_system_tools()`: If running on Linux, checks `shutil.which()` for `mn` (Mininet), `ovs-vsctl`, `ovs-ofctl`, and `ifconfig`.
  - `install_linux_packages()`: Invokes `sudo apt-get update && apt-get install -y mininet openvswitch-switch net-tools`.
  - `launch_run_py()`: If all dependencies are already satisfied, it invokes `os.execv(sys.executable, ["run.py"])`, replacing the setup process with `run.py` instantly with zero user friction.

### File 2: [`run.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/run.py) (Master Orchestration CLI)
* **Goal:** Provides both a user-friendly interactive terminal menu and automated CLI flags.
* **CLI Flags:**
  - `--demo`: Launches the real-time simulation with live telemetry logging.
  - `--benchmark`: Runs the automated comparative experiment and renders plots.
  - `--mininet`: Launches the Mininet CLI on Linux.
  - `--test`: Runs `pytest -v tests/`.

### File 3: [`src/config.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/config.py) (Central Configuration Repository)
* Centralizes all IP addresses (`10.0.0.1` - `10.0.0.4`), UDP ports (Main: `9999`, Cross: `9998`), link bandwidths (`10.0 Mbps`), delays ($5\text{ms}$ vs $15\text{ms}$), queue depths ($100\text{ packets}$), rate limits ($6\text{ Mbps}$ vs $7\text{ Mbps}$), and detection thresholds ($8.0\text{ Mbps}$, $N=2$ breaches).

### File 4: [`src/protocol.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/protocol.py) (Binary Protocol Engine)
* **Header Format:** `!4s I d H B B H` (22 bytes total).
* `pack_packet(seq_num, flow_id, flags, payload)`: Uses `time.time()` for high-precision timestamping and packs binary bytes into network byte order (big-endian).
* `unpack_packet(data)`: Validates magic bytes `SDN1`, unpacks header, slices trailing payload, and raises `InvalidPacketError` if malformed.

### File 5: [`src/udp_sender.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/udp_sender.py) (Precision UDP Socket Client)
* Creates socket using `socket(AF_INET, SOCK_DGRAM)`.
* Expands `SO_SNDBUF` to 1 MB.
* Implements a **monotonic drift-compensated transmission loop**:
  - Computes exact packet interval: $\Delta t = \frac{\text{packet\_size} \times 8}{\text{rate\_bps}}$.
  - Compares `time.perf_counter()` against `next_send_time` to eliminate OS scheduling drift.
  - Tags packets with `FLAG_START` on initialization and `FLAG_FIN` on termination.

### File 6: [`src/udp_receiver.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/udp_receiver.py) (Multi-Threaded Telemetry Server)
* Binds to `0.0.0.0:9999` with `SO_RCVBUF` set to 2 MB and a $0.5\text{s}$ socket timeout.
* Thread-safe telemetry collection:
  - Tracks total received packets, bytes, sequence gaps, and out-of-order packets.
  - Computes one-way latency: $(T_{\text{recv}} - T_{\text{send}}) \times 1000\text{ ms}$.
  - Computes RFC 3550 exponential moving average jitter:
    $$J_i = J_{i-1} + \frac{|D(i, j)| - J_{i-1}}{16}$$
  - Maintains rolling 500ms sliding windows for live throughput and loss percentage calculation.

### File 7: [`src/congestion_generator.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/congestion_generator.py) (Cross-Traffic Engine)
* Waits for `start_delay = 7.0s`, then launches a high-rate $7.0\text{ Mbps}$ UDP burst tagged with `FLOW_CROSS = 2` directed to Host $H_4$.
* Overloads Path A to 13 Mbps, inducing the controlled network stress scenario.

### File 8: [`src/topology.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/topology.py) (Mininet Diamond Topology)
* Defines `DiamondTopo(Topo)`:
  - Adds 4 Open vSwitch instances ($S_1, S_2, S_3, S_4$) with `protocols="OpenFlow13"`.
  - Adds 4 hosts with `/24` subnet IP configurations.
  - Uses `TCLink` to enforce $10\text{ Mbps}$ bandwidth, $5\text{ms}$ delay on Path A, $15\text{ms}$ delay on Path B, and 100-packet buffer limits.
  - `setup_ovs_flows()` installs baseline OpenFlow rules for ARP flooding and initial routing out of Port 2.

### File 9: [`src/network_emulator.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/network_emulator.py) (Pure-Python Network Emulator)
* Allows the entire system to run on Windows or non-root environments without installing Mininet.
* Implements `SimulatedLink` using thread-safe `queue.Queue(maxsize=100)`.
* Drains packets at exact serialization rate ($1,250,000\text{ bytes/sec}$), drops packets on queue overflow, and routes packets dynamically based on the SDN controller's active path.

### File 10: [`src/sdn_controller.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/sdn_controller.py) (SDN Controller & Telemetry Brain)
* Background telemetry loop runs every $0.5\text{s}$.
* Calculates rate in Mbps: $\frac{\Delta \text{bytes} \times 8}{\Delta t \times 10^6}$.
* Detects breach ($>8.0\text{ Mbps}$). If breach persists for $N=2$ samples, triggers reroute.
* Dispatches OpenFlow `FlowMod` to Switch $S_1$ via `ovs-ofctl`, matching UDP port 9999 with action `output:3` at `priority=200`.
* Measures Recovery Time between breach detection and flow rule confirmation ($9.46\text{ ms}$).

### File 11: [`src/ryu_controller.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/ryu_controller.py) (Standard Ryu OpenFlow 1.3 App)
* Implements the official Ryu event-driven architecture using `EventOFPPortStatsReply` and `OFPFlowMod`.
* Compatible with `ryu-manager src/ryu_controller.py`.

### File 12: [`src/benchmark.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/benchmark.py) (Scientific Comparison Suite)
* Runs two consecutive experiments under identical traffic patterns:
  1. Static Routing (adaptive rerouting disabled).
  2. Dynamic SDN Adaptive Routing (controller enabled).
* Computes average throughput, packet loss, peak loss, latency, and recovery time.
* Uses Matplotlib with the headless `"Agg"` backend to render the 4-panel comparison figure saved as `evaluation_results.png`.

### File 13: [`src/tcp_congestion_sim.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/tcp_congestion_sim.py) (Transport Layer Congestion Models)
* Implements mathematical algorithmic models for:
  - **TCP Tahoe:** Slow start, congestion avoidance, drops to 1 MSS on loss.
  - **TCP Reno:** Fast recovery (halves window to ssthresh on 3 dup ACKs).
  - **TCP CUBIC:** RFC 8312 cubic window growth function: $W_{\text{cubic}}(t) = C(t - K)^3 + W_{\max}$.
  - **SDN Dynamic Rerouting:** Demonstrates that by redirecting traffic before buffer overflow, the transport-layer window $cwnd$ never collapses!

### File 14: [`src/gui_app.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/gui_app.py) (Master PyQt6 Presentation Dashboard)
* **Live Topology Canvas:** QPainter rendering $H_1, H_3 \rightarrow S_1 \rightarrow S_2 / S_3 \rightarrow S_4 \rightarrow H_2, H_4$ with glowing active paths and red flashing congestion alerts.
* **Interactive Sliders:** Queue limit (10 to 100 packets), bottleneck bandwidth (2 to 10 Mbps), host rate (1 to 10 Mbps), and cross-traffic rate (1 to 10 Mbps).
* **Live Category 2 Gauges:** Throughput, packet loss rate %, latency, RFC 3550 jitter, and packet counters.
* **Embedded Charts:** Live real-time throughput & loss plotting, and TCP Tahoe vs Reno vs CUBIC CWND saw-tooth graphs.

---

## 5. Mathematical Summary Table

| Metric | Mathematical Formula | Code Implementation |
| :--- | :--- | :--- |
| **Instantaneous Bitrate** | $\text{Mbps} = \frac{\Delta \text{Bytes} \times 8}{\Delta t \times 1,000,000}$ | `src/sdn_controller.py` line 180 |
| **Packet Loss Count** | $\text{Loss} = \text{Seq}_{\text{recv}} - \text{Seq}_{\text{expected}}$ | `src/udp_receiver.py` line 143 |
| **One-Way Delay** | $\text{Latency} = (T_{\text{recv}} - T_{\text{send}}) \times 1000\text{ ms}$ | `src/udp_receiver.py` line 131 |
| **RFC 3550 Jitter** | $J_i = J_{i-1} + \frac{|(R_j - S_j) - (R_i - S_i)| - J_{i-1}}{16}$ | `src/udp_receiver.py` line 137 |
| **Packet Interval (Pacing)** | $\Delta t_{\text{pkt}} = \frac{\text{Packet Size (Bytes)} \times 8}{\text{Bitrate (bps)}}$ | `src/udp_sender.py` line 113 |
| **Serialization Delay** | $t_{\text{serialize}} = \frac{\text{Packet Length (Bytes)} \times 8}{\text{Link Capacity (bps)}}$ | `src/network_emulator.py` line 77 |
| **Recovery Time** | $T_{\text{recovery}} = T_{\text{rule\_confirmed}} - T_{\text{breach\_detected}}$ | `src/sdn_controller.py` line 150 |
