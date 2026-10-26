# Topic 27: SDN Congestion Detection & Dynamic Traffic Rerouting
## Codebase Function Catalog & Technical Reference

> **Document Overview:**
> This document provides a comprehensive, file-by-file breakdown of every single function, method, and class across all Python source modules in the `src/` directory.
> Each entry details the function's signature, operational purpose, inputs/parameters, and return outputs in a concise, structured format.

---

### Source Module Summary

| Module | Primary Responsibility | Items Documented |
| :--- | :--- | :---: |
| **`src/config.py`** | Global constants and configuration parameters for IP addresses, UDP ports, ... | 8 |
| **`src/protocol.py`** | Custom binary datagram serialization protocol. Implements a 22-byte header ... | 6 |
| **`src/udp_sender.py`** | High-precision rate-controlled UDP socket sender with monotonic timing, dyn... | 10 |
| **`src/udp_receiver.py`** | High-performance multithreaded UDP socket receiver with sliding window tele... | 9 |
| **`src/congestion_generator.py`** | Background cross-traffic congestion injector. Generates scheduled high-rate... | 3 |
| **`src/network_emulator.py`** | Software-defined network emulator. Emulates OpenFlow Diamond topology with ... | 14 |
| **`src/sdn_controller.py`** | Centralized OpenFlow 1.3 controller and congestion telemetry engine. Polls ... | 12 |
| **`src/ryu_controller.py`** | Standard Ryu OpenFlow 1.3 controller application. Implements event-driven h... | 7 |
| **`src/topology_handler.py`** | Dynamic topology interaction manager. Coordinates cable bottlenecks, senders, and sidebar controls. | 10 |
| **`src/topology_loader.py`** | Topology loader engine for Topologia (.toponet) files. Validates extensions and loads schemas. | 13 |
| **`src/benchmark.py`** | Automated comparative benchmark test suite. Executes experiments across Sta... | 3 |
| **`src/gui_app.py`** | Comprehensive PyQt5 / PyQtGraph GUI application. Implements animated topolo... | 69 |

---

## 1. `src/config.py`

> **File Description:**  
> Global constants and configuration parameters for IP addresses, UDP ports, link capacities, delays, queue depth limits, traffic rates, and SDN hysteresis thresholds.

### Key Configuration Constants

+--------------------------------------------------------------------------------+
| Constant(s): `HOST_H1_IP, HOST_H2_IP, HOST_H3_IP, HOST_H4_IP`
+--------------------------------------------------------------------------------+
  Description: Mininet IP addresses for H1 (10.0.0.1 Sender), H2 (10.0.0.2 Receiver), H3 (10.0.0.3 Cross Sender), H4 (10.0.0.4 Cross Receiver).

+--------------------------------------------------------------------------------+
| Constant(s): `MAIN_UDP_PORT, CROSS_UDP_PORT`
+--------------------------------------------------------------------------------+
  Description: UDP destination ports: 9999 for primary video/data stream, 9998 for background cross-traffic stream.

+--------------------------------------------------------------------------------+
| Constant(s): `CONTROLLER_PORT, CONTROLLER_REST_PORT, TELEMETRY_MONITOR_PORT`
+--------------------------------------------------------------------------------+
  Description: OpenFlow Southbound port (6653), Ryu REST API port (8080), and standalone live telemetry terminal port (9010).

+--------------------------------------------------------------------------------+
| Constant(s): `LINK_CAPACITY_MBPS, PATH_A_DELAY_MS, PATH_B_DELAY_MS, QUEUE_LIMIT_PACKETS`
+--------------------------------------------------------------------------------+
  Description: Physical link constraints: 10.0 Mbps bottleneck bandwidth, 5 ms Path A latency, 15 ms Path B latency, and 100-packet max buffer queue limit.

+--------------------------------------------------------------------------------+
| Constant(s): `DEFAULT_PACKET_SIZE, MAIN_TRAFFIC_RATE_MBPS, CROSS_TRAFFIC_RATE_MBPS`
+--------------------------------------------------------------------------------+
  Description: Traffic generation settings: 1024-byte MTU-safe packets, 6.0 Mbps main flow injection, and 7.0 Mbps cross-traffic burst injection (13.0 Mbps aggregate load).

+--------------------------------------------------------------------------------+
| Constant(s): `CONGESTION_THRESHOLD_MBPS, CONGESTION_LOSS_THRESHOLD_PCT, HYSTERESIS_RECOVERY_MBPS`
+--------------------------------------------------------------------------------+
  Description: SDN reroute thresholds: 8.0 Mbps upper trigger (80% link capacity), 3.0% loss trigger, and 4.5 Mbps lower hysteresis recovery threshold.

+--------------------------------------------------------------------------------+
| Constant(s): `POLL_INTERVAL_SEC, CONSECUTIVE_TRIGGERS_REQUIRED`
+--------------------------------------------------------------------------------+
  Description: SDN monitoring parameters: 0.5s polling period, N=2 consecutive threshold breach intervals required to confirm persistent congestion.

+--------------------------------------------------------------------------------+
| Constant(s): `PATH_PRIMARY, PATH_ALTERNATE`
+--------------------------------------------------------------------------------+
  Description: String path identifiers: 'Path-A (S1 -> S2 -> S4)' and 'Path-B (S1 -> S3 -> S4)'.

---

## 2. `src/protocol.py`

> **File Description:**  
> Custom binary datagram serialization protocol. Implements a 22-byte header with magic validation, sequence tracking, microsecond timestamps, flow isolation, and feedback encoding.

### Functions & Methods (6 documented)

+--------------------------------------------------------------------------------+
| [CLASS EXCEPTION] InvalidPacketError
| Signature: class InvalidPacketError(Exception)
+--------------------------------------------------------------------------------+
  - **Purpose:** Custom exception raised when a received datagram fails magic byte validation, is truncated below 22 bytes, or contains corrupted header fields.
  - **Inputs:** Message string describing the parsing failure.
  - **Outputs:** Exception instance.

+--------------------------------------------------------------------------------+
| [FUNCTION] pack_packet
| Signature: pack_packet(seq_num: int, flow_id: int = FLOW_MAIN, flags: int = FLAG_DATA, payload: bytes = b'') -> bytes
+--------------------------------------------------------------------------------+
  - **Purpose:** Serializes a UDP datagram with a 22-byte binary header using Python struct ('!4s I d H B B H'). Embeds 'SDN1' magic bytes, 32-bit sequence number, 64-bit IEEE timestamp (time.time()), 16-bit flow ID, 8-bit flags, reserved byte, and 16-bit payload length.
  - **Inputs:** seq_num (int): Monotonic packet index; flow_id (int): Flow identifier (1=Main, 2=Cross); flags (int): Packet flags (DATA/START/FIN/FEEDBACK); payload (bytes): Application payload.
  - **Outputs:** bytes: Fully serialized binary datagram (22-byte header + payload).

+--------------------------------------------------------------------------------+
| [FUNCTION] unpack_packet
| Signature: unpack_packet(data: bytes) -> Tuple[int, float, int, int, bytes]
+--------------------------------------------------------------------------------+
  - **Purpose:** Deserializes incoming raw UDP datagram bytes. Validates length (>= 22 bytes) and 'SDN1' magic bytes. Extracts header fields and slices the application payload.
  - **Inputs:** data (bytes): Raw datagram received from socket.
  - **Outputs:** tuple: (seq_num, send_time, flow_id, flags, payload).

+--------------------------------------------------------------------------------+
| [FUNCTION] make_dummy_payload
| Signature: make_dummy_payload(target_total_packet_size: int = 1024) -> bytes
+--------------------------------------------------------------------------------+
  - **Purpose:** Generates a pre-allocated padding byte buffer ('X' * N) such that header (22 bytes) + payload exactly equals target_total_packet_size (default 1024 bytes). Prevents runtime memory allocation overhead.
  - **Inputs:** target_total_packet_size (int): Total target datagram size in bytes (default: 1024).
  - **Outputs:** bytes: Pre-allocated ASCII padding bytes (1002 bytes for 1024-byte packet).

+--------------------------------------------------------------------------------+
| [FUNCTION] pack_feedback
| Signature: pack_feedback(loss_pct: float, throughput_mbps: float, latency_ms: float, suggested_rate_mbps: float) -> bytes
+--------------------------------------------------------------------------------+
  - **Purpose:** Packs receiver-side telemetry metrics into a 16-byte binary payload ('!ffff') and wraps it in a datagram with FLAG_FEEDBACK. Used for closed-loop rate adaptation.
  - **Inputs:** loss_pct (float), throughput_mbps (float), latency_ms (float), suggested_rate_mbps (float).
  - **Outputs:** bytes: Binary feedback datagram ready for socket transmission.

+--------------------------------------------------------------------------------+
| [FUNCTION] unpack_feedback
| Signature: unpack_feedback(payload: bytes) -> Tuple[float, float, float, float]
+--------------------------------------------------------------------------------+
  - **Purpose:** Deserializes a 16-byte feedback payload into its 4 constituent floating-point network metrics.
  - **Inputs:** payload (bytes): 16-byte binary payload extracted from a feedback datagram.
  - **Outputs:** tuple: (loss_pct, throughput_mbps, latency_ms, suggested_rate_mbps).

---

## 3. `src/udp_sender.py`

> **File Description:**  
> High-precision rate-controlled UDP socket sender with monotonic timing, dynamic rate adjustment, feedback listener, and sequence numbering.

### Functions & Methods (10 documented)

+--------------------------------------------------------------------------------+
| [METHOD] UDPSender.__init__
| Signature: UDPSender.__init__(target_ip: str, target_port: int, rate_mbps: float = 6.0, packet_size: int = 1024, flow_id: int = 1, duration: Optional[float] = None, enable_rate_adaptation: bool = False, min_rate_mbps: float = 1.5, feedback_port: Optional[int] = None)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes UDP sender state, calculates initial inter-packet interval, pre-allocates payload buffer, and configures rate adaptation parameters.
  - **Inputs:** target_ip (str), target_port (int), rate_mbps (float), packet_size (int), flow_id (int), duration (float or None), enable_rate_adaptation (bool), min_rate_mbps (float), feedback_port (int or None).
  - **Outputs:** UDPSender instance.

+--------------------------------------------------------------------------------+
| [METHOD] UDPSender.set_rate
| Signature: UDPSender.set_rate(new_rate_mbps: float)
+--------------------------------------------------------------------------------+
  - **Purpose:** Dynamically modifies target injection throughput in real time, bounds rate between [min_rate_mbps, 12.0], recomputes inter-packet transmission interval, and logs rate change event.
  - **Inputs:** new_rate_mbps (float): Requested sending throughput in Mbps.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPSender.handle_feedback
| Signature: UDPSender.handle_feedback(loss_pct: float, throughput_mbps: float, latency_ms: float)
+--------------------------------------------------------------------------------+
  - **Purpose:** Executes application-layer AIMD rate adaptation: -30% multiplicative decrease for severe loss (>5%), -15% decrease for moderate loss (2-5%), and +0.5 Mbps additive increase for clean network (<1%). Enforces 1.0s hysteresis hold interval to prevent oscillation.
  - **Inputs:** loss_pct (float): Receiver packet loss %; throughput_mbps (float): Receiver goodput; latency_ms (float): End-to-end latency.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPSender._setup_socket
| Signature: UDPSender._setup_socket()
+--------------------------------------------------------------------------------+
  - **Purpose:** Creates non-blocking UDP socket, sets SO_SNDBUF to 1MB to prevent OS transmission buffer drop, and optionally binds secondary feedback socket on feedback_port.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPSender.start
| Signature: UDPSender.start()
+--------------------------------------------------------------------------------+
  - **Purpose:** Spawns background daemon thread executing _run_loop for paced transmission, and optionally spawns _feedback_thread for handling incoming telemetry feedback.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPSender.stop
| Signature: UDPSender.stop()
+--------------------------------------------------------------------------------+
  - **Purpose:** Sets running flag to False, transmits final FLAG_FIN datagram to signal receiver, joins worker threads, and cleanly closes all sockets.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPSender._feedback_loop
| Signature: UDPSender._feedback_loop()
+--------------------------------------------------------------------------------+
  - **Purpose:** Background thread loop listening for UDP feedback datagrams, unpacking metrics, and routing them to handle_feedback.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPSender._run_loop
| Signature: UDPSender._run_loop()
+--------------------------------------------------------------------------------+
  - **Purpose:** Core packet generation loop. Sends FLAG_START packet, uses time.perf_counter() monotonic rate pacing to inject datagrams at precise microsecond intervals, tracks packet/byte counts, and handles socket errors.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPSender.get_stats
| Signature: UDPSender.get_stats() -> Dict[str, Any]
+--------------------------------------------------------------------------------+
  - **Purpose:** Returns instantaneous snapshot of sender metrics: total packets sent, total bytes sent, active elapsed time, instantaneous throughput (Mbps), current rate, adaptation event log, and running status.
  - **Inputs:** None.
  - **Outputs:** dict: Sender performance metrics.

+--------------------------------------------------------------------------------+
| [FUNCTION] udp_sender.main
| Signature: main()
+--------------------------------------------------------------------------------+
  - **Purpose:** CLI entry point. Parses command line arguments (--target, --port, --rate, --duration, --flow-id), runs UDPSender instance, prints live progress, and prints final transmission summary.
  - **Inputs:** CLI arguments via sys.argv.
  - **Outputs:** None (CLI process).

---

## 4. `src/udp_receiver.py`

> **File Description:**  
> High-performance multithreaded UDP socket receiver with sliding window telemetry, sequence loss tracking, RFC 3550 jitter calculation, and feedback generation.

### Functions & Methods (9 documented)

+--------------------------------------------------------------------------------+
| [METHOD] UDPReceiver.__init__
| Signature: UDPReceiver.__init__(bind_ip: str = '0.0.0.0', bind_port: int = 9999, log_file: Optional[str] = None, feedback_target: Optional[tuple] = None)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes receiver state, circular buffers (latencies, rolling history), RFC 3550 jitter state, sequence tracking counters, and synchronization lock.
  - **Inputs:** bind_ip (str), bind_port (int), log_file (str or None), feedback_target (tuple (ip, port) or None).
  - **Outputs:** UDPReceiver instance.

+--------------------------------------------------------------------------------+
| [METHOD] UDPReceiver._setup_socket
| Signature: UDPReceiver._setup_socket()
+--------------------------------------------------------------------------------+
  - **Purpose:** Creates UDP socket, sets SO_REUSEADDR and 2MB SO_RCVBUF to prevent OS buffer drops under high-rate burst congestion, binds to IP/port, sets 0.5s timeout, and creates dedicated outbound feedback socket.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPReceiver.start
| Signature: UDPReceiver.start()
+--------------------------------------------------------------------------------+
  - **Purpose:** Sets up socket and launches background worker thread executing _listen_loop.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPReceiver.stop
| Signature: UDPReceiver.stop()
+--------------------------------------------------------------------------------+
  - **Purpose:** Sets running flag to False, joins receiver thread, closes sockets, and optionally exports collected telemetry history to JSON log file.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPReceiver._listen_loop
| Signature: UDPReceiver._listen_loop()
+--------------------------------------------------------------------------------+
  - **Purpose:** Core packet ingestion loop. Receives datagrams, extracts timestamps, measures one-way delay (t_rx - t_tx), calculates RFC 3550 EWMA jitter, tracks sequence gaps for packet loss, and periodically triggers window evaluation.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPReceiver._check_window
| Signature: UDPReceiver._check_window(current_time: float)
+--------------------------------------------------------------------------------+
  - **Purpose:** Evaluates 500ms sliding telemetry window. Computes window loss %, throughput, goodput, and average latency. Appends snapshot to circular history, transmits feedback datagram to feedback_target if configured, and resets window counters.
  - **Inputs:** current_time (float): Current timestamp.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] UDPReceiver.get_latest_stats
| Signature: UDPReceiver.get_latest_stats() -> Dict[str, Any]
+--------------------------------------------------------------------------------+
  - **Purpose:** Thread-safe retrieval of latest telemetry metrics: throughput, goodput, window loss %, overall loss %, average latency, jitter, total received, total lost, and out-of-order count.
  - **Inputs:** None.
  - **Outputs:** dict: Real-time telemetry snapshot.

+--------------------------------------------------------------------------------+
| [METHOD] UDPReceiver.export_history_to_file
| Signature: UDPReceiver.export_history_to_file(filepath: str)
+--------------------------------------------------------------------------------+
  - **Purpose:** Serializes the complete rolling telemetry history list into a formatted JSON file.
  - **Inputs:** filepath (str): Target output file path.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [FUNCTION] udp_receiver.main
| Signature: main()
+--------------------------------------------------------------------------------+
  - **Purpose:** CLI entry point. Parses arguments (--ip, --port, --log), instantiates UDPReceiver, logs live throughput and loss to stdout every second, and prints final summary upon interrupt.
  - **Inputs:** CLI arguments via sys.argv.
  - **Outputs:** None (CLI process).

---

## 5. `src/congestion_generator.py`

> **File Description:**  
> Background cross-traffic congestion injector. Generates scheduled high-rate UDP bursts on shared links to saturate buffers and trigger SDN rerouting.

### Functions & Methods (3 documented)

+--------------------------------------------------------------------------------+
| [METHOD] CongestionGenerator.__init__
| Signature: CongestionGenerator.__init__(target_ip: str = '10.0.0.4', target_port: int = 9998, rate_mbps: float = 7.0, start_delay: float = 0.0, duration: float = 10.0)
+--------------------------------------------------------------------------------+
  - **Purpose:** Configures cross-traffic burst parameters: destination IP/port, target bit-rate (default 7.0 Mbps), initial delay before firing, and burst duration.
  - **Inputs:** target_ip (str), target_port (int), rate_mbps (float), start_delay (float), duration (float).
  - **Outputs:** CongestionGenerator instance.

+--------------------------------------------------------------------------------+
| [METHOD] CongestionGenerator.run
| Signature: CongestionGenerator.run()
+--------------------------------------------------------------------------------+
  - **Purpose:** Sleeps for start_delay seconds, instantiates and starts an internal UDPSender with FLOW_CROSS, waits for duration, cleanly stops sender, and logs total burst packets and throughput.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [FUNCTION] congestion_generator.main
| Signature: main()
+--------------------------------------------------------------------------------+
  - **Purpose:** CLI entry point for running standalone cross-traffic injection with custom rate, delay, and duration arguments.
  - **Inputs:** CLI arguments via sys.argv.
  - **Outputs:** None (CLI process).

---

## 6. `src/network_emulator.py`

> **File Description:**  
> Software-defined network emulator. Emulates OpenFlow Diamond topology with virtual links, token-bucket rate limiting, tail-drop buffers, propagation delay, and packet relaying.

### Functions & Methods (14 documented)

+--------------------------------------------------------------------------------+
| [METHOD] SimulatedLink.__init__
| Signature: SimulatedLink.__init__(name: str, capacity_mbps: float, delay_ms: float, max_queue: int = 100)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes virtual link model with bandwidth capacity, propagation delay, and bounded FIFO packet queue (default 100 packets). Computes token-bucket parameters.
  - **Inputs:** name (str), capacity_mbps (float), delay_ms (float), max_queue (int).
  - **Outputs:** SimulatedLink instance.

+--------------------------------------------------------------------------------+
| [METHOD] SimulatedLink.set_max_queue
| Signature: SimulatedLink.set_max_queue(new_limit: int)
+--------------------------------------------------------------------------------+
  - **Purpose:** Dynamically adjusts queue depth limit [10, 100] in real time when user moves GUI queue slider.
  - **Inputs:** new_limit (int): New maximum queue packet depth.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] SimulatedLink.set_capacity_mbps
| Signature: SimulatedLink.set_capacity_mbps(new_capacity: float)
+--------------------------------------------------------------------------------+
  - **Purpose:** Dynamically updates link bandwidth [1.0, 20.0 Mbps] and recalculates token bucket drain rate in real time.
  - **Inputs:** new_capacity (float): New bandwidth capacity in Mbps.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] SimulatedLink.start
| Signature: SimulatedLink.start(forward_handler: Callable)
+--------------------------------------------------------------------------------+
  - **Purpose:** Assigns forward delivery callback and starts background drain loop thread.
  - **Inputs:** forward_handler (callable): Function called to deliver packet to destination socket.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] SimulatedLink.stop
| Signature: SimulatedLink.stop()
+--------------------------------------------------------------------------------+
  - **Purpose:** Stops link drain loop thread cleanly.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] SimulatedLink.enqueue
| Signature: SimulatedLink.enqueue(packet_bytes: bytes, destination_addr: tuple) -> bool
+--------------------------------------------------------------------------------+
  - **Purpose:** Enforces tail-drop queuing policy. Increments rx_bytes. If current queue size >= max_queue, drops packet and increments dropped_packets. Otherwise, places packet in FIFO queue with enqueue timestamp.
  - **Inputs:** packet_bytes (bytes): Packet payload; destination_addr (tuple): Target (ip, port).
  - **Outputs:** bool: True if forwarded/queued, False if dropped due to buffer overflow.

+--------------------------------------------------------------------------------+
| [METHOD] SimulatedLink._drain_loop
| Signature: SimulatedLink._drain_loop()
+--------------------------------------------------------------------------------+
  - **Purpose:** Background thread executing token-bucket rate shaping and propagation delay. Holds packets until arrival_time + delay_sec, meters byte rate using token accumulation, and delivers packets to forward_handler.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] NetworkEmulator.__init__
| Signature: NetworkEmulator.__init__(controller: SDNController, ingress_port: int = 9000, main_dest_port: int = 9999, cross_dest_port: int = 9998)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes emulator instance, links it to SDN controller, configures ingress listening port (9000) and egress destination ports, and creates SimulatedLink instances for Path A and Path B.
  - **Inputs:** controller (SDNController), ingress_port (int), main_dest_port (int), cross_dest_port (int).
  - **Outputs:** NetworkEmulator instance.

+--------------------------------------------------------------------------------+
| [METHOD] NetworkEmulator.register_packet_callback
| Signature: NetworkEmulator.register_packet_callback(cb: Callable)
+--------------------------------------------------------------------------------+
  - **Purpose:** Registers a GUI callback function to receive packet transmission/drop event notifications.
  - **Inputs:** cb (callable): Function accepting packet event dict.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] NetworkEmulator.unregister_packet_callback
| Signature: NetworkEmulator.unregister_packet_callback(cb: Callable)
+--------------------------------------------------------------------------------+
  - **Purpose:** Removes a previously registered packet event callback.
  - **Inputs:** cb (callable).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] NetworkEmulator.start
| Signature: NetworkEmulator.start()
+--------------------------------------------------------------------------------+
  - **Purpose:** Binds ingress UDP socket (port 9000), starts Path A and Path B SimulatedLinks, opens egress and monitor sockets, and launches _switch_relay_loop thread.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] NetworkEmulator.stop
| Signature: NetworkEmulator.stop()
+--------------------------------------------------------------------------------+
  - **Purpose:** Stops link drain loops, closes ingress, egress, and telemetry monitor sockets, and terminates relay thread.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] NetworkEmulator._dispatch_packet_event
| Signature: NetworkEmulator._dispatch_packet_event(seq: int, flow_id: int, size: int, active_link: SimulatedLink, is_forwarded: bool)
+--------------------------------------------------------------------------------+
  - **Purpose:** Constructs structured packet event record (time, flow, seq, size, path, queue occupancy, status, dropped flag, rerouted flag), notifies GUI callbacks, and transmits summary line to external terminal monitor on port 9010.
  - **Inputs:** seq (int), flow_id (int), size (int), active_link (SimulatedLink), is_forwarded (bool).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] NetworkEmulator._switch_relay_loop
| Signature: NetworkEmulator._switch_relay_loop()
+--------------------------------------------------------------------------------+
  - **Purpose:** Core virtual switch datapath. Ingests packets on port 9000, periodically feeds cumulative switch port byte counters to SDN controller, queries controller.current_active_path to route FLOW_MAIN to Path A or Path B, routes FLOW_CROSS to Path A, enqueues packets, and dispatches events.
  - **Inputs:** None.
  - **Outputs:** None.

---

## 7. `src/sdn_controller.py`

> **File Description:**  
> Centralized OpenFlow 1.3 controller and congestion telemetry engine. Polls switch port counters, implements 3-state congestion FSM, evaluates hysteresis thresholds, executes OpenFlow FlowMod reroutes, and measures recovery time.

### Functions & Methods (12 documented)

+--------------------------------------------------------------------------------+
| [METHOD] SDNController.__init__
| Signature: SDNController.__init__(congestion_threshold_mbps: float = 8.0, poll_interval: float = 0.5, adaptive_routing_enabled: bool = True, auto_revert_enabled: bool = True)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes SDN controller state, threshold settings (8.0 Mbps trigger, 4.5 Mbps hysteresis recovery), polling timer, breach/recovery counters, and port statistics cache.
  - **Inputs:** congestion_threshold_mbps (float), poll_interval (float), adaptive_routing_enabled (bool), auto_revert_enabled (bool).
  - **Outputs:** SDNController instance.

+--------------------------------------------------------------------------------+
| [METHOD] SDNController.start
| Signature: SDNController.start()
+--------------------------------------------------------------------------------+
  - **Purpose:** Spawns background telemetry thread executing _telemetry_loop.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] SDNController.stop
| Signature: SDNController.stop()
+--------------------------------------------------------------------------------+
  - **Purpose:** Sets running flag to False and joins telemetry thread.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] SDNController._query_ovs_port_stats
| Signature: SDNController._query_ovs_port_stats()
+--------------------------------------------------------------------------------+
  - **Purpose:** When running inside Linux/Mininet, executes 'ovs-ofctl -O OpenFlow13 dump-ports s1' via subprocess, parses live port 2 (Path A) and port 3 (Path B) tx_bytes, and feeds them into port_stats.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] SDNController._telemetry_loop
| Signature: SDNController._telemetry_loop()
+--------------------------------------------------------------------------------+
  - **Purpose:** Background thread loop running every poll_interval (0.5s). Queries port statistics and triggers _poll_and_evaluate.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] SDNController._poll_and_evaluate
| Signature: SDNController._poll_and_evaluate()
+--------------------------------------------------------------------------------+
  - **Purpose:** Core congestion decision engine. Calculates real-time bitrate on Path A and Path B. When on Path A: tracks consecutive breaches (>=8.0 Mbps); triggers reroute to Path B when breaches >= 2. When on Path B: checks hysteresis cooldown (<4.5 Mbps on Path A and <8.0 Mbps on Path B); reverts to Path A when recoveries >= 4 (2.0s cooldown).
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] SDNController._trigger_reroute
| Signature: SDNController._trigger_reroute(to_path: str, reason: str)
+--------------------------------------------------------------------------------+
  - **Purpose:** Executes dynamic path failover. Dispatches _apply_flow_mod, measures failover duration in milliseconds, updates current_active_path, increments total_reroutes, and logs structured reroute event record.
  - **Inputs:** to_path (str): Target destination path; reason (str): Textual justification for reroute.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] SDNController._apply_flow_mod
| Signature: SDNController._apply_flow_mod(path: str) -> bool
+--------------------------------------------------------------------------------+
  - **Purpose:** Constructs and dispatches OpenFlow 1.3 FlowMod rule: adds flow with priority=100 matching UDP packets to port 9999 and actions=output:3 (for Path B) or output:2 (for Path A). Falls back gracefully to virtual state if OVS is unavailable.
  - **Inputs:** path (str): Target path constant (PATH_PRIMARY or PATH_ALTERNATE).
  - **Outputs:** bool: True on successful flow rule insertion.

+--------------------------------------------------------------------------------+
| [METHOD] SDNController.record_external_stats
| Signature: SDNController.record_external_stats(switch: str, port_no: int, rx_bytes: int, tx_bytes: int)
+--------------------------------------------------------------------------------+
  - **Purpose:** Thread-safe entry point for feeding cumulative switch port bytes. Computes delta bytes over delta time to calculate instantaneous port throughput in Mbps.
  - **Inputs:** switch (str): Switch name (e.g. 's1'); port_no (int): Port index; rx_bytes (int); tx_bytes (int).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] SDNController.get_path_load
| Signature: SDNController.get_path_load(switch: str, port_no: int) -> float
+--------------------------------------------------------------------------------+
  - **Purpose:** Thread-safe retrieval of current measured throughput (Mbps) on a specified switch port.
  - **Inputs:** switch (str), port_no (int).
  - **Outputs:** float: Measured throughput in Mbps.

+--------------------------------------------------------------------------------+
| [METHOD] SDNController.get_flow_table
| Signature: SDNController.get_flow_table(switch: str = 's1') -> str
+--------------------------------------------------------------------------------+
  - **Purpose:** Returns formatted text representation of the active OpenFlow flow table. Queries live kernel flows via 'ovs-ofctl dump-flows' if available, otherwise formats active controller rules.
  - **Inputs:** switch (str): Target switch name (default: 's1').
  - **Outputs:** str: Multi-line formatted flow table string.

+--------------------------------------------------------------------------------+
| [METHOD] SDNController.get_controller_status
| Signature: SDNController.get_controller_status() -> Dict[str, Any]
+--------------------------------------------------------------------------------+
  - **Purpose:** Thread-safe export of complete controller telemetry status: active_path, total_reroutes, path_a_load_mbps, path_b_load_mbps, latest_recovery_time_sec, and both_paths_congested flag.
  - **Inputs:** None.
  - **Outputs:** dict: Complete controller status dictionary.

---

## 8. `src/ryu_controller.py`

> **File Description:**  
> Standard Ryu OpenFlow 1.3 controller application. Implements event-driven handlers for switch feature negotiation, periodic port statistics queries, threshold breach detection, and OpenFlow FlowMod generation.

### Functions & Methods (7 documented)

+--------------------------------------------------------------------------------+
| [METHOD] RyuCongestionRerouter.__init__
| Signature: RyuCongestionRerouter.__init__(*args, **kwargs)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes Ryu application, registers datapath dictionary, initializes port statistics tracking dictionary, sets 8.0 Mbps threshold, and spawns background hub monitor thread.
  - **Inputs:** *args, **kwargs passed from Ryu app manager.
  - **Outputs:** RyuCongestionRerouter instance.

+--------------------------------------------------------------------------------+
| [METHOD] RyuCongestionRerouter.switch_features_handler
| Signature: RyuCongestionRerouter.switch_features_handler(ev: EventOFPSwitchFeatures)
+--------------------------------------------------------------------------------+
  - **Purpose:** OpenFlow event handler triggered when a switch connects (CONFIG_DISPATCHER). Stores switch datapath object and installs baseline table-miss flow entry (Priority 0) sending unknown packets to controller.
  - **Inputs:** ev (EventOFPSwitchFeatures): OpenFlow switch features event.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] RyuCongestionRerouter.add_flow
| Signature: RyuCongestionRerouter.add_flow(datapath, priority, match, actions, buffer_id=None)
+--------------------------------------------------------------------------------+
  - **Purpose:** Constructs and transmits an OFPFlowMod message to install a flow rule with specified priority, match filter, and action list into switch datapath.
  - **Inputs:** datapath: Switch connection object; priority (int); match (OFPMatch); actions (list of OFPAction); buffer_id (int or None).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] RyuCongestionRerouter._monitor
| Signature: RyuCongestionRerouter._monitor()
+--------------------------------------------------------------------------------+
  - **Purpose:** Periodic background coroutine loop (hub.spawn). Iterates through all connected switch datapaths and triggers _request_port_stats every 0.5 seconds.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] RyuCongestionRerouter._request_port_stats
| Signature: RyuCongestionRerouter._request_port_stats(datapath)
+--------------------------------------------------------------------------------+
  - **Purpose:** Constructs and dispatches an OFPPortStatsRequest message to query port telemetry counters from a switch datapath.
  - **Inputs:** datapath: Target switch datapath object.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] RyuCongestionRerouter.port_stats_reply_handler
| Signature: RyuCongestionRerouter.port_stats_reply_handler(ev: EventOFPPortStatsReply)
+--------------------------------------------------------------------------------+
  - **Purpose:** OpenFlow event handler triggered on port statistics reply (MAIN_DISPATCHER). Calculates port throughput deltas. If ingress switch S1 port 2 throughput > 8.0 Mbps, logs congestion alert and invokes _reroute_to_path_b.
  - **Inputs:** ev (EventOFPPortStatsReply): OpenFlow port stats event.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] RyuCongestionRerouter._reroute_to_path_b
| Signature: RyuCongestionRerouter._reroute_to_path_b(datapath)
+--------------------------------------------------------------------------------+
  - **Purpose:** Constructs OFPMatch for UDP packets to port 9999, creates OFPActionOutput(3) (Port 3 -> Path B), and installs flow entry with Priority 200 via add_flow.
  - **Inputs:** datapath: Target switch datapath object (Switch S1).
  - **Outputs:** None.

---

## 9. `src/topology_handler.py`

> **File Description:**  
> Central manager for dynamic topology interactions and reactions. Manages cable bottleneck constraints, queue limits, sender pacing rates, and synchronizes real-time updates across the network emulator, SDN controller, and GUI sidebar controls.

### Functions & Methods (10 documented)

+--------------------------------------------------------------------------------+
| [METHOD] CableElement.__init__
| Signature: CableElement.__init__(cable_id: str, name: str, cable_type: str, src: str, dst: str, capacity_mbps: float = 10.0, delay_ms: float = 5.0, queue_limit: int = 100, path_segment: str = '')
+--------------------------------------------------------------------------------+
  - **Purpose:** Encapsulates a physical or virtual cable/link in the topology with attributes for capacity, delay, max queue limit, path affiliation, and active status.
  - **Inputs:** cable_id (str), name (str), cable_type (str), src (str), dst (str), capacity_mbps (float), delay_ms (float), queue_limit (int), path_segment (str).
  - **Outputs:** CableElement instance.

+--------------------------------------------------------------------------------+
| [METHOD] SenderElement.__init__
| Signature: SenderElement.__init__(sender_id: str, name: str, host_id: str, target_ip: str, target_port: int, rate_mbps: float = 6.0, role: str = 'main_sender')
+--------------------------------------------------------------------------------+
  - **Purpose:** Encapsulates an active or configurable traffic generator (e.g. Main stream sender H1 or Cross-traffic burst generator H3) with target destination, rate, and running state.
  - **Inputs:** sender_id (str), name (str), host_id (str), target_ip (str), target_port (int), rate_mbps (float), role (str).
  - **Outputs:** SenderElement instance.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyHandler.__init__
| Signature: TopologyHandler.__init__(topo_def=None, emulator=None, sdn_controller=None)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes topology handler, binds topology definition, network emulator, and SDN controller, and extracts cable and sender inventories.
  - **Inputs:** topo_def (TopologyDefinition), emulator (NetworkEmulator), sdn_controller (SDNController).
  - **Outputs:** TopologyHandler instance.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyHandler.load_from_definition
| Signature: TopologyHandler.load_from_definition(topo_def)
+--------------------------------------------------------------------------------+
  - **Purpose:** Reconstructs cable elements (primary bottleneck Path A, alternate bottleneck Path B, host edge links) and sender elements from a parsed TopologyDefinition, applying settings to emulator links.
  - **Inputs:** topo_def (TopologyDefinition).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyHandler.set_cable_bottleneck
| Signature: TopologyHandler.set_cable_bottleneck(cable_id: str, capacity_mbps: float)
+--------------------------------------------------------------------------------+
  - **Purpose:** Dynamically adjusts the bottleneck bandwidth capacity of a specific cable (Path A or Path B) and applies rate changes immediately to emulator token-bucket limiters.
  - **Inputs:** cable_id (str): Cable identifier; capacity_mbps (float): New bandwidth capacity (1-50 Mbps).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyHandler.set_cable_queue_limit
| Signature: TopologyHandler.set_cable_queue_limit(cable_id: str, queue_limit: int)
+--------------------------------------------------------------------------------+
  - **Purpose:** Adjusts drop-tail queue buffer capacity for individual or all cables in the topology.
  - **Inputs:** cable_id (str): Cable ID or 'all'; queue_limit (int): Buffer capacity in packets (10-500).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyHandler.set_cable_delay
| Signature: TopologyHandler.set_cable_delay(cable_id: str, delay_ms: float)
+--------------------------------------------------------------------------------+
  - **Purpose:** Dynamically adjusts propagation delay on specified cable links.
  - **Inputs:** cable_id (str): Cable identifier; delay_ms (float): Propagation delay in ms.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyHandler.set_sender_rate
| Signature: TopologyHandler.set_sender_rate(sender_id: str, rate_mbps: float)
+--------------------------------------------------------------------------------+
  - **Purpose:** Adjusts transmission pacing rate of a traffic sender (Main sender or Cross burst generator) and updates active socket sender threads in real time.
  - **Inputs:** sender_id (str): Sender identifier; rate_mbps (float): Target sending rate (0.5-30 Mbps).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyHandler.on_reroute
| Signature: TopologyHandler.on_reroute(active_path: str)
+--------------------------------------------------------------------------------+
  - **Purpose:** Updates internal active/inactive status across cables when SDN controller triggers a path switch between Path A and Path B.
  - **Inputs:** active_path (str): Target active path key ('path_a' or 'path_b').
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyHandler.reset_defaults
| Signature: TopologyHandler.reset_defaults()
+--------------------------------------------------------------------------------+
  - **Purpose:** Restores nominal cable capacities (10 Mbps), queue limits (100 pkts), and default sender rates.
  - **Inputs:** None.
  - **Outputs:** None.

---

## 10. `src/topology_loader.py`

> **File Description:**  
> Topology loader engine for Topologia (.toponet) files. Validates .toponet extensions, parses JSON topology schemas, converts definitions to Mininet Topo instances, and configures emulator links and canvas layouts.

### Functions & Methods (13 documented)

+--------------------------------------------------------------------------------+
| [CLASS EXCEPTION] InvalidTopologyExtensionError
| Signature: class InvalidTopologyExtensionError(ValueError)
+--------------------------------------------------------------------------------+
  - **Purpose:** Custom exception raised when attempting to load a topology file that does not have the mandatory '.toponet' extension.
  - **Inputs:** Message string describing the invalid extension.
  - **Outputs:** Exception instance.

+--------------------------------------------------------------------------------+
| [CLASS EXCEPTION] CorruptTopologyFileError
| Signature: class CorruptTopologyFileError(ValueError)
+--------------------------------------------------------------------------------+
  - **Purpose:** Custom exception raised when a .toponet file contains invalid JSON or is missing essential topology schema fields (switches, hosts, links).
  - **Inputs:** Message string describing corrupt data or missing field.
  - **Outputs:** Exception instance.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyDefinition.__init__
| Signature: TopologyDefinition.__init__(data: Dict[str, Any], filepath: str = '')
+--------------------------------------------------------------------------------+
  - **Purpose:** Parses and structures .toponet topology dictionary: extracts format, version, topology_name, description, switches, hosts, links, paths, traffic_profile, and sdn_policy. Builds fast lookup node map.
  - **Inputs:** data (dict): Raw parsed JSON dictionary; filepath (str): Source file path.
  - **Outputs:** TopologyDefinition instance.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyDefinition.get_node
| Signature: TopologyDefinition.get_node(node_id: str) -> Optional[Dict[str, Any]]
+--------------------------------------------------------------------------------+
  - **Purpose:** Case-insensitive lookup retrieving node dictionary for a given node ID (e.g. 's1', 'h2').
  - **Inputs:** node_id (str): Identifier of switch or host.
  - **Outputs:** dict or None: Node specification dictionary.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyDefinition.get_node_pos
| Signature: TopologyDefinition.get_node_pos(node_id: str, default: Tuple[float, float] = (0.5, 0.5)) -> Tuple[float, float]
+--------------------------------------------------------------------------------+
  - **Purpose:** Extracts normalized (x, y) coordinates [0.0, 1.0] for canvas visualization.
  - **Inputs:** node_id (str): Target node ID; default (tuple): Fallback coordinates.
  - **Outputs:** tuple: (x, y) float coordinates.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyDefinition.get_path
| Signature: TopologyDefinition.get_path(path_key: str) -> Optional[Dict[str, Any]]
+--------------------------------------------------------------------------------+
  - **Purpose:** Retrieves routing path parameters dictionary for specified path key (e.g. 'path_a', 'path_b').
  - **Inputs:** path_key (str): Path identifier.
  - **Outputs:** dict or None: Path parameters (name, hops, delay_ms, capacity_mbps, queue_limit).

+--------------------------------------------------------------------------------+
| [METHOD] TopologyDefinition.to_dict
| Signature: TopologyDefinition.to_dict() -> Dict[str, Any]
+--------------------------------------------------------------------------------+
  - **Purpose:** Exports the structured topology definition back to a serializable dictionary for JSON storage.
  - **Inputs:** None.
  - **Outputs:** dict: Complete topology schema dictionary.

+--------------------------------------------------------------------------------+
| [METHOD] TopologyDefinition.build_mininet_topo
| Signature: TopologyDefinition.build_mininet_topo() -> Optional[Topo]
+--------------------------------------------------------------------------------+
  - **Purpose:** Dynamically constructs a Mininet Topo subclass using the .tp definition. Adds switches with OpenFlow 1.3, hosts with default routes, and configured bottleneck links.
  - **Inputs:** None.
  - **Outputs:** Mininet Topo instance (or None if mininet is not installed).

+--------------------------------------------------------------------------------+
| [FUNCTION] validate_tp_extension
| Signature: validate_tp_extension(filepath: str)
+--------------------------------------------------------------------------------+
  - **Purpose:** Enforces that the provided file path ends with '.tp'. Raises InvalidTopologyExtensionError if extension does not match.
  - **Inputs:** filepath (str): File path to validate.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [FUNCTION] load_topology
| Signature: load_topology(filepath: str) -> TopologyDefinition
+--------------------------------------------------------------------------------+
  - **Purpose:** Validates .tp extension, opens and parses JSON file, verifies schema completeness, and returns a validated TopologyDefinition instance.
  - **Inputs:** filepath (str): Path to .tp file.
  - **Outputs:** TopologyDefinition: Validated topology object.

+--------------------------------------------------------------------------------+
| [FUNCTION] save_topology
| Signature: save_topology(topo_def: TopologyDefinition, filepath: str)
+--------------------------------------------------------------------------------+
  - **Purpose:** Serializes a TopologyDefinition instance to a formatted JSON .tp file after verifying .tp extension.
  - **Inputs:** topo_def (TopologyDefinition): Topology object; filepath (str): Output path.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [FUNCTION] get_default_topology_path
| Signature: get_default_topology_path() -> str
+--------------------------------------------------------------------------------+
  - **Purpose:** Locates the default diamond.toponet file in workspace root or source directories.
  - **Inputs:** None.
  - **Outputs:** str: Resolved path to diamond.toponet.

+--------------------------------------------------------------------------------+
| [FUNCTION] get_default_topology
| Signature: get_default_topology() -> TopologyDefinition
+--------------------------------------------------------------------------------+
  - **Purpose:** Loads and returns the default diamond topology from diamond.toponet.
  - **Inputs:** None.
  - **Outputs:** TopologyDefinition: Default diamond topology definition.

---

## 11. `src/benchmark.py`

> **File Description:**  
> Automated comparative benchmark test suite. Executes experiments across Static, Dynamic SDN, and Rate Control modes, compiles 11 performance metrics, and plots evaluation graphs.

### Functions & Methods (3 documented)

+--------------------------------------------------------------------------------+
| [FUNCTION] run_single_experiment
| Signature: run_single_experiment(mode_name: str, adaptive_enabled: bool, enable_rate_adapt: bool = False, total_duration: float = 14.0, congestion_start: float = 3.0, congestion_duration: float = 7.0, ingress_port: int = 9000, main_port: int = 9999, cross_port: int = 9998, feedback_port: int = 9005, progress_callback = None) -> Dict[str, Any]
+--------------------------------------------------------------------------------+
  - **Purpose:** Executes a complete automated test run: launches SDN controller, network emulator, UDP receivers, and main sender; injects scheduled cross-traffic burst at congestion_start; samples real-time metrics; performs clean shutdown; and compiles summary statistics dictionary.
  - **Inputs:** mode_name (str), adaptive_enabled (bool), enable_rate_adapt (bool), total_duration (float), congestion_start (float), congestion_duration (float), port numbers, progress_callback (optional callable).
  - **Outputs:** dict: Complete experiment results including summary metrics, reroute event log, and 500ms time series.

+--------------------------------------------------------------------------------+
| [FUNCTION] plot_benchmark_results
| Signature: plot_benchmark_results(static_res: dict, dynamic_res: dict, rate_res: Optional[dict] = None, output_path: str = 'evaluation_results.png', fig = None, dark_mode: bool = True, run_label: Optional[str] = None) -> matplotlib.figure.Figure
+--------------------------------------------------------------------------------+
  - **Purpose:** Renders a high-resolution 4-panel comparative evaluation chart: 1) Throughput over time (Mbps), 2) Packet loss % over time, 3) One-way latency over time (ms), and 4) Summary bar chart (Avg Thpt, Avg Loss %, Peak Loss %). Supports dark/light themes and exports to PNG.
  - **Inputs:** static_res (dict), dynamic_res (dict), rate_res (dict or None), output_path (str), fig (optional Matplotlib Figure), dark_mode (bool), run_label (str or None).
  - **Outputs:** matplotlib.figure.Figure: The rendered Matplotlib figure object.

+--------------------------------------------------------------------------------+
| [FUNCTION] run_benchmark
| Signature: run_benchmark(total_duration: float = 14.0, congestion_start: float = 3.0, congestion_duration: float = 7.0)
+--------------------------------------------------------------------------------+
  - **Purpose:** Runs the full 3-phase automated benchmark (Experiment A: Static, Experiment B: Dynamic SDN, Experiment C: SDN + Rate Control). Compiles 11-metric side-by-side comparison table, prints grid table to console, generates evaluation plot PNG, and dumps data to benchmark_summary.json.
  - **Inputs:** total_duration (float), congestion_start (float), congestion_duration (float).
  - **Outputs:** None (generates files and stdout summary).

---

## 12. `src/gui_app.py`

> **File Description:**  
> Comprehensive PyQt5 / PyQtGraph GUI application. Implements animated topology canvas, real-time KPI graphs, popout analytics widgets, packet inspection console, automated benchmark tab, and network control sliders.

### Functions & Methods (69 documented)

+--------------------------------------------------------------------------------+
| [METHOD] PacketDot.__init__
| Signature: PacketDot.__init__(path: str, color: QColor, speed: float = 0.04)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes animated packet particle object with target path identifier, drawing color, animation speed, and position parameter t in [0.0, 1.0].
  - **Inputs:** path (str), color (QColor), speed (float).
  - **Outputs:** PacketDot instance.

+--------------------------------------------------------------------------------+
| [METHOD] AnimatedTopologyCanvas.__init__
| Signature: AnimatedTopologyCanvas.__init__(parent=None)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes animated network topology widget, defines node layouts, sets minimum size (520x260), creates particle lists, and sets up 40ms QTimer for 25 FPS animation rendering.
  - **Inputs:** parent (QWidget or None).
  - **Outputs:** AnimatedTopologyCanvas instance.

+--------------------------------------------------------------------------------+
| [METHOD] AnimatedTopologyCanvas.update_state
| Signature: AnimatedTopologyCanvas.update_state(active_path, load_a, load_b, congested, q_occupancy, q_limit, main_active, cross_active)
+--------------------------------------------------------------------------------+
  - **Purpose:** Updates live topology display state: current active path, link loads (Mbps), congestion status, queue depth / limit, and traffic flow particle activity flags.
  - **Inputs:** active_path (str), load_a (float), load_b (float), congested (bool), q_occupancy (float), q_limit (int), main_active (bool), cross_active (bool).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AnimatedTopologyCanvas._step_animation
| Signature: AnimatedTopologyCanvas._step_animation()
+--------------------------------------------------------------------------------+
  - **Purpose:** Timer callback running at 25 FPS. Advances position t of each active packet particle dot, spawns new dots when traffic flows are active, removes completed dots, and triggers widget repaint.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AnimatedTopologyCanvas.paintEvent
| Signature: AnimatedTopologyCanvas.paintEvent(event: QPaintEvent)
+--------------------------------------------------------------------------------+
  - **Purpose:** Custom QPainter rendering loop. Draws diamond topology links, animated particle dots, switch/host nodes, status labels, dynamic queue meter bar, and link throughput metrics.
  - **Inputs:** event (QPaintEvent).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] RealtimePlotContainer.__init__
| Signature: RealtimePlotContainer.__init__(parent=None)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes live PyQtGraph throughput and packet loss strip charts. Sets up bounded ring buffer histories, plot curves, axis labels, autotrack toggle, and view reset buttons.
  - **Inputs:** parent (QWidget or None).
  - **Outputs:** RealtimePlotContainer instance.

+--------------------------------------------------------------------------------+
| [METHOD] RealtimePlotContainer._toggle_autotrack
| Signature: RealtimePlotContainer._toggle_autotrack()
+--------------------------------------------------------------------------------+
  - **Purpose:** Toggles sliding X-axis window auto-tracking on or off and updates button visual styling.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] RealtimePlotContainer._reset_view
| Signature: RealtimePlotContainer._reset_view()
+--------------------------------------------------------------------------------+
  - **Purpose:** Restores auto-tracking and resets plot view ranges to default viewing limits.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] RealtimePlotContainer._apply_auto_range
| Signature: RealtimePlotContainer._apply_auto_range()
+--------------------------------------------------------------------------------+
  - **Purpose:** Invokes autoRange on throughput and loss plot widgets.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] RealtimePlotContainer.update_plot
| Signature: RealtimePlotContainer.update_plot(t: float, thpt: float, loss: float)
+--------------------------------------------------------------------------------+
  - **Purpose:** Appends new time/throughput/loss data point, trims historical points older than sliding window limit, updates PyQtGraph curve datasets, and adjusts visible X range.
  - **Inputs:** t (float): Elapsed time in seconds; thpt (float): Throughput in Mbps; loss (float): Packet loss %.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] LiveSDNReroutingAnalyticsWidget.__init__
| Signature: LiveSDNReroutingAnalyticsWidget.__init__(parent=None)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes 3-panel live SDN analytics widget: 1) Offered Path Load vs Capacity, 2) Switch Queue Depth & Loss %, and 3) End-to-End Latency & Jitter. Creates KPI status badges, autotrack controls, and event log list.
  - **Inputs:** parent (QWidget or None).
  - **Outputs:** LiveSDNReroutingAnalyticsWidget instance.

+--------------------------------------------------------------------------------+
| [METHOD] LiveSDNReroutingAnalyticsWidget._toggle_autotrack
| Signature: LiveSDNReroutingAnalyticsWidget._toggle_autotrack()
+--------------------------------------------------------------------------------+
  - **Purpose:** Toggles auto-scrolling X-axis tracking across all 3 SDN analytics subplots.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] LiveSDNReroutingAnalyticsWidget._reset_view
| Signature: LiveSDNReroutingAnalyticsWidget._reset_view()
+--------------------------------------------------------------------------------+
  - **Purpose:** Resets view boundaries and reenables auto-tracking across all 3 subplots.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] LiveSDNReroutingAnalyticsWidget._apply_auto_range
| Signature: LiveSDNReroutingAnalyticsWidget._apply_auto_range()
+--------------------------------------------------------------------------------+
  - **Purpose:** Forces autoRange recomputation on all 3 analytics plot views.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] LiveSDNReroutingAnalyticsWidget._clear_history
| Signature: LiveSDNReroutingAnalyticsWidget._clear_history()
+--------------------------------------------------------------------------------+
  - **Purpose:** Clears all deque historical data buffers and resets plot curves and event log.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] LiveSDNReroutingAnalyticsWidget.update_sdn_telemetry
| Signature: LiveSDNReroutingAnalyticsWidget.update_sdn_telemetry(t, active_path, load_a, load_b, threshold, capacity, queue_pkts, loss_pct, latency_ms, jitter_ms, failover_latency_sec=None)
+--------------------------------------------------------------------------------+
  - **Purpose:** Pushes live SDN metrics to analytics subplots, trims points outside visible window, updates live curve datasets, logs OpenFlow FlowMod reroute / restoration events to event list, and updates status KPI badges.
  - **Inputs:** t (float), active_path (str), load_a (float), load_b (float), threshold (float), capacity (float), queue_pkts (float), loss_pct (float), latency_ms (float), jitter_ms (float), failover_latency_sec (optional float).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] LivePacketConsoleWidget.__init__
| Signature: LivePacketConsoleWidget.__init__(parent=None)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes live packet inspection console. Sets up bounded ring buffer (500 items), filter checkboxes (Show Main, Show Cross, Show Drops Only), pause/resume buttons, queue drain QTimer (50ms), and popout external terminal button.
  - **Inputs:** parent (QWidget or None).
  - **Outputs:** LivePacketConsoleWidget instance.

+--------------------------------------------------------------------------------+
| [METHOD] LivePacketConsoleWidget.on_packet_event
| Signature: LivePacketConsoleWidget.on_packet_event(evt: dict)
+--------------------------------------------------------------------------------+
  - **Purpose:** Callback invoked by emulator on every packet forwarded or dropped. Appends event to thread-safe pending queue if matching filter criteria.
  - **Inputs:** evt (dict): Packet event record.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] LivePacketConsoleWidget._toggle_pause
| Signature: LivePacketConsoleWidget._toggle_pause()
+--------------------------------------------------------------------------------+
  - **Purpose:** Pauses or resumes live packet console auto-scrolling stream and toggles button styling.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] LivePacketConsoleWidget._clear_console
| Signature: LivePacketConsoleWidget._clear_console()
+--------------------------------------------------------------------------------+
  - **Purpose:** Clears all text from the console display.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] LivePacketConsoleWidget._append_system_msg
| Signature: LivePacketConsoleWidget._append_system_msg(msg: str)
+--------------------------------------------------------------------------------+
  - **Purpose:** Appends a formatted cyan system message into the console output.
  - **Inputs:** msg (str): Message text.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] LivePacketConsoleWidget._launch_external_terminal
| Signature: LivePacketConsoleWidget._launch_external_terminal()
+--------------------------------------------------------------------------------+
  - **Purpose:** Spawns an independent command prompt / PowerShell window running a standalone UDP telemetry packet listener on port 9010.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] LivePacketConsoleWidget._drain_queue
| Signature: LivePacketConsoleWidget._drain_queue()
+--------------------------------------------------------------------------------+
  - **Purpose:** QTimer callback (50ms). Batches pending packet events, generates colored HTML lines (green forwarded, red drops, blue reroutes), appends batch to QTextEdit, and scrolls to bottom if not paused.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] PopoutTabContainer.__init__
| Signature: PopoutTabContainer.__init__(title: str, inner_widget: QWidget, tabs: QTabWidget, watermark: str = '')
+--------------------------------------------------------------------------------+
  - **Purpose:** Wrapper widget supporting bidirectional tab detaching into floating windows and docking back into main tab widget.
  - **Inputs:** title (str), inner_widget (QWidget), tabs (QTabWidget), watermark (str).
  - **Outputs:** PopoutTabContainer instance.

+--------------------------------------------------------------------------------+
| [METHOD] PopoutTabContainer.toggle_popout
| Signature: PopoutTabContainer.toggle_popout()
+--------------------------------------------------------------------------------+
  - **Purpose:** Detaches inner widget into an independent floating desktop window if docked, or redocks it into QTabWidget if floating.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] PopoutTabContainer._on_float_close
| Signature: PopoutTabContainer._on_float_close(event: QCloseEvent)
+--------------------------------------------------------------------------------+
  - **Purpose:** Window close event handler for floating dialog. Intercepts close and automatically docks widget back into parent tab bar.
  - **Inputs:** event (QCloseEvent).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] PopoutTabContainer.dock_back
| Signature: PopoutTabContainer.dock_back()
+--------------------------------------------------------------------------------+
  - **Purpose:** Re-inserts floating widget back into main tab widget at its original index and restores title.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] BenchmarkWorkerThread.__init__
| Signature: BenchmarkWorkerThread.__init__(parent=None, duration=10.0, congestion_start=2.5, congestion_duration=5.0)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes QThread worker for executing multi-phase benchmark without freezing the Qt main GUI thread. Defines progress, status, phase_completed, completed, and error signals.
  - **Inputs:** parent, duration (float), congestion_start (float), congestion_duration (float).
  - **Outputs:** BenchmarkWorkerThread instance.

+--------------------------------------------------------------------------------+
| [METHOD] BenchmarkWorkerThread.run
| Signature: BenchmarkWorkerThread.run()
+--------------------------------------------------------------------------------+
  - **Purpose:** Worker thread execution body. Sequentially runs Experiment A (Static), Experiment B (Dynamic SDN), and Experiment C (SDN + Rate Control). Emits phase completion signals and final completed signal with compiled results.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget.__init__
| Signature: AutomatedBenchmarkWidget.__init__(parent=None)
+--------------------------------------------------------------------------------+
  - **Purpose:** Initializes automated evaluation tab. Builds 11-row comparison QTableWidget, embeds FigureCanvasQTAgg for the 4-panel graph, creates progress bar, export buttons (JSON/PNG), and loads cached results from disk.
  - **Inputs:** parent (QWidget or None).
  - **Outputs:** AutomatedBenchmarkWidget instance.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._load_cached_results
| Signature: AutomatedBenchmarkWidget._load_cached_results()
+--------------------------------------------------------------------------------+
  - **Purpose:** Checks for existing benchmark_summary.json on disk and populates comparison table and graph if found.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._show_placeholder
| Signature: AutomatedBenchmarkWidget._show_placeholder()
+--------------------------------------------------------------------------------+
  - **Purpose:** Renders an empty placeholder graph informing user to click 'Run Full Automated Evaluation Benchmark'.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._set_table_item
| Signature: AutomatedBenchmarkWidget._set_table_item(row: int, col: int, text: str, color_hex: str = '#cdd6f4', bold: bool = False)
+--------------------------------------------------------------------------------+
  - **Purpose:** Helper method creating and configuring a styled QTableWidgetItem with text alignment, foreground color, and font weight.
  - **Inputs:** row (int), col (int), text (str), color_hex (str), bold (bool).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._format_phase_metrics
| Signature: AutomatedBenchmarkWidget._format_phase_metrics(res: dict, is_static: bool = False) -> dict
+--------------------------------------------------------------------------------+
  - **Purpose:** Calculates phase-separated metrics from time series: baseline phase (before congestion), congestion phase (during burst), and post-congestion recovery phase.
  - **Inputs:** res (dict): Experiment results dictionary; is_static (bool): Whether mode is static.
  - **Outputs:** dict: Metrics broken down by phase.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._format_verdicts
| Signature: AutomatedBenchmarkWidget._format_verdicts(s: dict, d: dict, r: dict) -> list
+--------------------------------------------------------------------------------+
  - **Purpose:** Computes relative percentage improvement and textual verdict strings comparing Dynamic SDN and Rate Control against Static baseline across all 11 metrics.
  - **Inputs:** s (dict Static), d (dict Dynamic), r (dict Rate Control).
  - **Outputs:** list of str: Verdict strings for table column 4.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget.populate_table
| Signature: AutomatedBenchmarkWidget.populate_table(s: dict, d: dict, r: dict)
+--------------------------------------------------------------------------------+
  - **Purpose:** Populates all 11 rows and 5 columns of the benchmark evaluation QTableWidget with numerical metrics and colored verdict indicators.
  - **Inputs:** s (dict Static), d (dict Dynamic), r (dict Rate Control).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget.start_benchmark
| Signature: AutomatedBenchmarkWidget.start_benchmark()
+--------------------------------------------------------------------------------+
  - **Purpose:** Disables run button, resets progress bar, instantiates BenchmarkWorkerThread, connects signals, and starts benchmark execution.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._on_phase_completed
| Signature: AutomatedBenchmarkWidget._on_phase_completed(mode: str, res: dict)
+--------------------------------------------------------------------------------+
  - **Purpose:** Slot called when an individual benchmark phase (STATIC, DYNAMIC, or SDN+RATE) completes. Updates table with intermediate data.
  - **Inputs:** mode (str), res (dict).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._on_worker_status
| Signature: AutomatedBenchmarkWidget._on_worker_status(msg: str)
+--------------------------------------------------------------------------------+
  - **Purpose:** Slot updating progress bar label with current execution status text.
  - **Inputs:** msg (str): Status description.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._on_worker_progress
| Signature: AutomatedBenchmarkWidget._on_worker_progress(val: int)
+--------------------------------------------------------------------------------+
  - **Purpose:** Slot updating QProgressBar integer percentage [0, 100].
  - **Inputs:** val (int): Percentage complete.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._on_worker_completed
| Signature: AutomatedBenchmarkWidget._on_worker_completed(s: dict, d: dict, r: dict)
+--------------------------------------------------------------------------------+
  - **Purpose:** Slot called when all 3 experiments finish. Populates comparison table, renders 4-panel graph, re-enables run button, updates benchmark_summary.json, and shows success message.
  - **Inputs:** s (dict Static), d (dict Dynamic), r (dict Rate Control).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._on_worker_error
| Signature: AutomatedBenchmarkWidget._on_worker_error(err: str)
+--------------------------------------------------------------------------------+
  - **Purpose:** Slot handling benchmark worker failure. Displays error modal and resets UI state.
  - **Inputs:** err (str): Error message string.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._export_png
| Signature: AutomatedBenchmarkWidget._export_png()
+--------------------------------------------------------------------------------+
  - **Purpose:** Opens QFileDialog and saves the 4-panel evaluation chart to user-selected PNG file path.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] AutomatedBenchmarkWidget._export_json
| Signature: AutomatedBenchmarkWidget._export_json()
+--------------------------------------------------------------------------------+
  - **Purpose:** Opens QFileDialog and exports full benchmark dataset into a user-selected JSON file.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI.__init__
| Signature: MasterSDNGUI.__init__()
+--------------------------------------------------------------------------------+
  - **Purpose:** Main window constructor. Applies modern dark theme stylesheet, starts SDNController, starts NetworkEmulator, starts primary and cross UDPReceivers, initializes menus, workspaces, and telemetry refresh timer (100ms).
  - **Inputs:** None.
  - **Outputs:** MasterSDNGUI instance.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._init_menu_bar
| Signature: MasterSDNGUI._init_menu_bar()
+--------------------------------------------------------------------------------+
  - **Purpose:** Builds application menu bar: File (Reset, Exit), Simulation (Start Stream, Inject Burst, Reset Topology), View (Dock/Undock tabs, Reset view), and Help (About).
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._init_header_bar
| Signature: MasterSDNGUI._init_header_bar()
+--------------------------------------------------------------------------------+
  - **Purpose:** Builds top header banner displaying project title, active path badge, failover latency badge, and reset button.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._init_main_workspace
| Signature: MasterSDNGUI._init_main_workspace()
+--------------------------------------------------------------------------------+
  - **Purpose:** Assembles central tab widget: Tab 1 (Topology & Live Operations), Tab 2 (Live SDN Analytics), Tab 3 (Packet Console), and Tab 4 (Automated Benchmark Evaluation). Wraps tabs in PopoutTabContainers.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._create_view_topology_operations
| Signature: MasterSDNGUI._create_view_topology_operations() -> QWidget
+--------------------------------------------------------------------------------+
  - **Purpose:** Constructs Tab 1 view combining animated topology canvas, real-time strip charts, network control panel, KPI badges, and flow table box.
  - **Inputs:** None.
  - **Outputs:** QWidget: Tab 1 root widget.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._create_controls_box
| Signature: MasterSDNGUI._create_controls_box() -> QGroupBox
+--------------------------------------------------------------------------------+
  - **Purpose:** Builds control panel: Queue limit slider (10-100), Bottleneck capacity slider (2-10M), Host rate slider (1-10M), Cross burst rate slider (2-12M), Start/Stop Stream button, Inject Congestion button, Auto-SDN toggle button, and Manual Path A/B override buttons.
  - **Inputs:** None.
  - **Outputs:** QGroupBox: Controls container.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._create_telemetry_kpi_box
| Signature: MasterSDNGUI._create_telemetry_kpi_box() -> QGroupBox
+--------------------------------------------------------------------------------+
  - **Purpose:** Builds live KPI dashboard displaying cards for Throughput, Goodput, Packet Loss %, Average Latency, RFC 3550 Jitter, and Packet Counters.
  - **Inputs:** None.
  - **Outputs:** QGroupBox: KPI dashboard container.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._create_flow_table_box
| Signature: MasterSDNGUI._create_flow_table_box() -> QGroupBox
+--------------------------------------------------------------------------------+
  - **Purpose:** Builds OpenFlow flow table monitor box displaying real-time flow rules, priorities, match filters, and output actions for Switch S1.
  - **Inputs:** None.
  - **Outputs:** QGroupBox: Flow table container.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._popout_all_windows
| Signature: MasterSDNGUI._popout_all_windows()
+--------------------------------------------------------------------------------+
  - **Purpose:** Detaches all workspace tabs into independent floating desktop windows.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._dock_all_windows
| Signature: MasterSDNGUI._dock_all_windows()
+--------------------------------------------------------------------------------+
  - **Purpose:** Re-docks all floating windows back into the main application tab widget.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._reset_default_view
| Signature: MasterSDNGUI._reset_default_view()
+--------------------------------------------------------------------------------+
  - **Purpose:** Docks all windows, selects Tab 1, and restores default splitter dimensions.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._launch_external_terminal
| Signature: MasterSDNGUI._launch_external_terminal()
+--------------------------------------------------------------------------------+
  - **Purpose:** Launches external terminal packet monitor from main window menu.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._on_queue_changed
| Signature: MasterSDNGUI._on_queue_changed(val: int)
+--------------------------------------------------------------------------------+
  - **Purpose:** Slider callback. Updates queue depth limit on emulator Path A link and updates GUI label.
  - **Inputs:** val (int): New queue limit.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._on_bw_changed
| Signature: MasterSDNGUI._on_bw_changed(val: int)
+--------------------------------------------------------------------------------+
  - **Purpose:** Slider callback. Updates bandwidth capacity on emulator Path A link and updates GUI label.
  - **Inputs:** val (int): New bandwidth in Mbps.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._on_host_rate_changed
| Signature: MasterSDNGUI._on_host_rate_changed(val: int)
+--------------------------------------------------------------------------------+
  - **Purpose:** Slider callback. Updates transmission rate on active main_sender and updates GUI label.
  - **Inputs:** val (int): New sending rate in Mbps.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._on_cross_rate_changed
| Signature: MasterSDNGUI._on_cross_rate_changed(val: int)
+--------------------------------------------------------------------------------+
  - **Purpose:** Slider callback. Updates cross-traffic injection rate slider label.
  - **Inputs:** val (int): Cross burst rate in Mbps.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._toggle_rate_adapt
| Signature: MasterSDNGUI._toggle_rate_adapt()
+--------------------------------------------------------------------------------+
  - **Purpose:** Toggles application-level rate adaptation on the sender and updates button label and style.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._toggle_main_stream
| Signature: MasterSDNGUI._toggle_main_stream()
+--------------------------------------------------------------------------------+
  - **Purpose:** Starts main UDPSender stream if stopped, or stops active stream if running. Toggles button text and styling.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._inject_congestion
| Signature: MasterSDNGUI._inject_congestion()
+--------------------------------------------------------------------------------+
  - **Purpose:** Fires a 9.0-second background cross-traffic burst at the configured slider rate on Path A using CongestionGenerator in a daemon thread.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._manual_reroute
| Signature: MasterSDNGUI._manual_reroute(to_path: str)
+--------------------------------------------------------------------------------+
  - **Purpose:** Forces manual operator reroute to PATH_PRIMARY or PATH_ALTERNATE via controller._trigger_reroute.
  - **Inputs:** to_path (str): Requested target path.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._toggle_sdn_mode
| Signature: MasterSDNGUI._toggle_sdn_mode()
+--------------------------------------------------------------------------------+
  - **Purpose:** Toggles controller.adaptive_routing_enabled between Dynamic SDN Rerouting and Static Routing.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._reset_topology
| Signature: MasterSDNGUI._reset_topology()
+--------------------------------------------------------------------------------+
  - **Purpose:** Stops sender, resets controller active path to Path A, clears breach counters, and displays confirmation modal.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI._refresh_telemetry
| Signature: MasterSDNGUI._refresh_telemetry()
+--------------------------------------------------------------------------------+
  - **Purpose:** Primary 100ms QTimer tick callback. Queries receiver stats and controller status, updates KPI labels, updates topology canvas, pushes data to strip charts, updates SDN analytics widget, and refreshes flow table text.
  - **Inputs:** None.
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [METHOD] MasterSDNGUI.closeEvent
| Signature: MasterSDNGUI.closeEvent(event: QCloseEvent)
+--------------------------------------------------------------------------------+
  - **Purpose:** Application exit cleanup handler. Stops QTimer, stops main sender, stops receivers, stops network emulator, stops SDN controller, and accepts window close.
  - **Inputs:** event (QCloseEvent).
  - **Outputs:** None.

+--------------------------------------------------------------------------------+
| [FUNCTION] gui_app.main
| Signature: main()
+--------------------------------------------------------------------------------+
  - **Purpose:** Application startup entry point. Configures high-DPI scaling policy, creates QApplication, initializes MasterSDNGUI, displays main window, and enters Qt application event loop.
  - **Inputs:** None.
  - **Outputs:** None (GUI application process).

---
