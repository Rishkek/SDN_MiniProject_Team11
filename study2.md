# Study Guide 2: Network Infrastructure, Mininet Topology & Data Plane Virtualization

**Team Member:** Member 2  
**Project Share:** Exactly 1/3 of the Project (The Network Infrastructure & Data Plane Subsystem)  
**Owned Codebase Files:**
- [`src/topology.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/topology.py) — Mininet Diamond multi-path topology
- [`src/network_emulator.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/network_emulator.py) — Standalone pure-Python switch & link emulator
- [`tests/test_system.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/tests/test_system.py) — Data-plane validation test suite
- [`src/gui_app.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/gui_app.py) — Live Topology Canvas & Link Controls Subsystem

---

## 1. Role Overview: What You Are Doing in This 1/3 of the Project

You are responsible for the **Network Infrastructure, Virtual Switches, and Data Plane**.
In computer networking, end-hosts do not communicate over thin air; their datagrams traverse physical links, queues, and switching fabrics. Your job is to:
1. Design and deploy the **Diamond Multi-Path Network Topology** in Mininet with 4 Open vSwitch (OVS) switches ($S_1, S_2, S_3, S_4$) and 4 end-hosts ($H_1, H_2, H_3, H_4$).
2. Configure **hardware-realistic link constraints** using Linux Traffic Control (`tc`): enforcing a $10.0\text{ Mbps}$ bandwidth limit, asymmetric link delays ($5\text{ms}$ on Path A vs $15\text{ms}$ on Path B), and finite FIFO queue buffers ($100\text{ packets}$).
3. Install the **baseline OpenFlow 1.3 forwarding rules** so that the network starts with normal connectivity, handles ARP requests, and directs initial UDP flows through Path A.
4. Build the **cross-platform SDN network emulator** (`src/network_emulator.py`) so that the team can demonstrate the exact same data-plane queuing and switching behavior on any laptop without needing root permissions.

---

## 2. How Your 1/3 Complements the Other Two Members

```
[Member 1: UDP Sockets]
       | (Pumps 6 Mbps UDP into Ingress Switch S1)
       v
[Member 2: Data Plane & Topology]
       |-- Ingress Switch S1: Routes traffic to Port 2 (Path A)
       |-- Path A Link: Enforces 10 Mbps limit & 100-packet queue
       |-- When traffic hits 13 Mbps: Drops packets due to queue overflow
       |-- Exposes port tx_bytes telemetry counters to Member 3
       v
[Member 3: SDN Controller]
       | (Detects load > 8 Mbps -> Sends OFPFlowMod to S1)
       v
[Member 2: Ingress Switch S1 Flow Table Updated]
       |-- Diverts UDP stream to Port 3 (Path B, 10 Mbps, 15ms)
       v
[Member 1: UDP Receiver on H2] (Receives stream with 0% loss)
```

* **Complementing Member 1 (Sockets):** Member 1's UDP sender and receiver rely completely on your topology to pass packets. You provide the virtual interfaces (`h1-eth0`, `h2-eth0`) and links. When Member 1 injects cross-traffic, your bottleneck link enforces the bandwidth throttling that forces packet loss.
* **Complementing Member 3 (SDN Controller):** Member 3's controller cannot function without your switches. Your switches record transmitted bytes on every port, which Member 3 queries. When Member 3 pushes an OpenFlow `FlowMod` instruction, your switch $S_1$ modifies its hardware/kernel lookup table and switches output ports from Port 2 to Port 3 in milliseconds.

---

## 3. Mininet and Linux Kernel Networking Explained in Depth

This is the most critical conceptual part of your viva defense. Evaluators frequently ask how Mininet actually works under the hood.

### A. What is Mininet and Why Does It Require Linux?
* Mininet is **not a hardware emulator** (like QEMU) and **not a full virtual machine** (like VirtualBox).
* Instead, Mininet is a **process-based network virtualization platform**.
* It runs real Linux code, real Python scripts, and real Open vSwitch daemons directly on the host Linux kernel, but wraps them in isolated virtual boundaries.
* This is why Mininet **cannot run natively on Windows without Linux/WSL2**: it depends directly on Linux kernel network namespaces and Linux Traffic Control (`tc`).

### B. Linux Network Namespaces (`ip netns`)
* In Linux, a **Network Namespace** provides a completely isolated copy of the network stack.
* When Mininet creates host $H_1$:
  - $H_1$ gets its own private IP address (`10.0.0.1`), its own loopback interface (`lo`), its own routing table, and its own socket binding table.
  - An application running on $H_1$ (e.g. `udp_sender.py`) cannot see the IP packets or sockets of $H_2$ or the host computer.
  - You can inspect these namespaces in Linux using: `ip netns list`.

### C. Virtual Ethernet Pairs (`veth`)
* How do you connect two isolated namespaces together? Through a Linux **veth pair**.
* A `veth` pair functions like a virtual bidirectional Ethernet cable:
  - Any packet injected into one end instantly pops out of the other end.
  - When Mininet connects $H_1$ to Switch $S_1$, it creates a `veth` pair: `h1-eth0` is placed inside $H_1$'s namespace, while `s1-eth1` is attached to the Open vSwitch bridge $S_1$.

### D. Linux Traffic Control (`tc`) and `TCLink`
* Real cables have bandwidth limits and propagation delay; virtual `veth` cables by default have infinite speed (RAM-to-RAM copy).
* To simulate real network physics, Mininet uses **Linux Traffic Control (`tc`)**:
  1. **Token Bucket Filter (`tbf`):** Enforces the $10.0\text{ Mbps}$ bandwidth ceiling. Tokens are added to the bucket at a rate of $10\text{ Mbps}$. When packets arrive, they consume tokens. If the bucket is empty, packets sit in the queue buffer.
  2. **Finite Queue Buffers (`max_queue_size=100`):** If the buffer exceeds 100 packets, excess packets are discarded (**tail drop**). This is how your network creates real packet loss during congestion.
  3. **Network Emulator (`netem`):** Injects exact artificial propagation delay ($5\text{ms}$ on Path A, $15\text{ms}$ on Path B).

### E. Open vSwitch (OVS) Architecture
* Every switch ($S_1, S_2, S_3, S_4$) is an instance of **Open vSwitch**.
* OVS consists of:
  - `ovs-vswitchd`: The user-space daemon that communicates with the SDN controller via the OpenFlow 1.3 protocol.
  - `ovsdb-server`: The configuration database storing port mappings and bridge settings.
  - **Kernel Datapath Module:** A high-speed caching engine in the Linux kernel that forwards packets at wire speed based on flow table matches.

---

## 4. Libraries Used & Why They Were Chosen

| Library / Module | Purpose in Member 2's Code | Why It Was Chosen Over Alternatives |
| :--- | :--- | :--- |
| **`mininet.topo.Topo`** | Base class for designing custom network topologies. | Official Mininet API. Allows programmatic multi-switch, multi-host graph definitions. |
| **`mininet.net.Mininet`** | Orchestrates the network lifecycle (`net.start()`, `net.stop()`). | Provides unified control of namespaces, switches, and controllers. |
| **`mininet.link.TCLink`** | Advanced link implementation wrapping Linux `tc`. | Essential for configuring `bw=10`, `delay="5ms"`, and `max_queue_size=100`. Standard `Link` cannot limit bandwidth. |
| **`mininet.node.OVSKernelSwitch`** | Instantiates Open vSwitch kernel bridges. | Enables OpenFlow 1.3 protocol support (`protocols="OpenFlow13"`). |
| **`subprocess`** | Executes `ovs-ofctl` commands directly on the host system. | Directly inspects and injects OpenFlow table rules into OVS bridges. |
| **`queue.Queue`** | Thread-safe FIFO queue used in `network_emulator.py`. | Simulates hardware switch ingress buffers with a hard cap of 100 packets. |

---

## 5. Line-by-Line Code Explanation of Member 2's Files

### A. Mininet Diamond Topology Script ([`src/topology.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/topology.py))

#### 1. Defining Switches and Hosts
```python
class DiamondTopo(Topo):
    def build(self):
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")
        s3 = self.addSwitch("s3", protocols="OpenFlow13")
        s4 = self.addSwitch("s4", protocols="OpenFlow13")

        h1 = self.addHost("h1", ip="10.0.0.1/24", defaultRoute="via 10.0.0.254")
        h2 = self.addHost("h2", ip="10.0.0.2/24", defaultRoute="via 10.0.0.254")
        h3 = self.addHost("h3", ip="10.0.0.3/24", defaultRoute="via 10.0.0.254")
        h4 = self.addHost("h4", ip="10.0.0.4/24", defaultRoute="via 10.0.0.254")
```
- Switches are configured with `protocols="OpenFlow13"` so they accept modern OpenFlow 1.3 instructions.
- Hosts are given static `/24` IP addresses matching the project specification.

#### 2. Wiring Bottleneck Links with Asymmetric Delays
```python
# Path A (Primary): Lowest latency (5ms), 10 Mbps bottleneck
self.addLink(s1, s2, bw=10, delay="5ms", max_queue_size=100)
self.addLink(s2, s4, bw=10, delay="5ms", max_queue_size=100)

# Path B (Backup): Higher latency (15ms), 10 Mbps bottleneck
self.addLink(s1, s3, bw=10, delay="15ms", max_queue_size=100)
self.addLink(s3, s4, bw=10, delay="15ms", max_queue_size=100)
```
- Port mapping on Ingress Switch $S_1$:
  - **Port 1:** Connected to $H_1$ (Main Sender).
  - **Port 4:** Connected to $H_3$ (Cross-Traffic Sender).
  - **Port 2:** Connected to $S_2$ (**Path A Link**).
  - **Port 3:** Connected to $S_3$ (**Path B Link**).
- By observing which port traffic leaves on $S_1$, we know whether it is traversing Path A (Port 2) or Path B (Port 3).

#### 3. Baseline Flow Rules Setup (`setup_ovs_flows()`)
```python
commands = [
    # Allow ARP requests to flood so hosts can resolve MAC addresses
    "ovs-ofctl -O OpenFlow13 add-flow s1 priority=10,dl_type=0x0806,actions=FLOOD",

    # Initial Rule: Route H1->H2 UDP port 9999 to Port 2 (Path A)
    "ovs-ofctl -O OpenFlow13 add-flow s1 priority=50,udp,nw_src=10.0.0.1,nw_dst=10.0.0.2,tp_dst=9999,actions=output:2",

    # Initial Rule: Route H3->H4 cross-traffic to Port 2 (Path A)
    "ovs-ofctl -O OpenFlow13 add-flow s1 priority=50,udp,nw_src=10.0.0.3,nw_dst=10.0.0.4,tp_dst=9998,actions=output:2"
]
```
- Sets priority `50` for the default routes out of Port 2.
- When Member 3 pushes an alternate rule with priority `200` to Port 3, OpenFlow automatically prioritizes the higher priority rule without needing to delete the old one.

---

### B. Pure-Python Network Emulator ([`src/network_emulator.py`](file:///c:/Users/Lenovo/Desktop/CN_project_congestion%20and%20traffic%20rerouting/src/network_emulator.py))

#### 1. Rate-Limited Serialization Loop
```python
def _drain_loop(self):
    bytes_per_sec = (self.capacity_mbps * 1_000_000.0) / 8.0
    while self._running:
        pkt_data, dest, enq_time = self.packet_queue.get(timeout=0.1)
        pkt_len = len(pkt_data)
        
        # Serialization delay: time taken to physically push bits onto the wire
        tx_delay = pkt_len / bytes_per_sec
        time.sleep(tx_delay)
        self.tx_bytes += pkt_len
        self.forward_handler(pkt_data, dest)
```
- Recreates the exact physical delay of a $10\text{ Mbps}$ link.
- At $10\text{ Mbps}$, pushing a 1024-byte packet takes:
  $$t_{\text{serialize}} = \frac{1024 \times 8}{10,000,000} \approx 0.819\text{ ms}$$
- If packets arrive faster than $0.819\text{ ms}$ per packet, the queue builds up. Once the queue hits 100 packets, `queue.Full` triggers and excess packets are dropped.

---

## 6. How to Present Your 1/3 During the Project Demo & Viva

When it is your turn to speak:
1. **Explain the Topology:** Point to the Diamond diagram in the terminal or `README.md`. Explain why Path A has 5ms delay and Path B has 15ms delay.
2. **Explain Mininet Internals:** Tell the evaluator: *"Mininet uses Linux Network Namespaces (`ip netns`) to give each host its own isolated networking stack, `veth` pairs as virtual cables, and Linux Traffic Control (`tc`) with Token Bucket Filters to enforce our 10 Mbps bottleneck links."*
3. **Show Open vSwitch Flow Tables:** Show the `ovs-ofctl` baseline rules in `src/topology.py` and explain why Port 2 connects to Path A and Port 3 connects to Path B.
4. **Transition to Member 3:** *"Now that the physical topology and switching fabric are established with 10 Mbps limits, Member 3 will explain how the SDN controller monitors port telemetry and dynamically issues FlowMod instructions."*
