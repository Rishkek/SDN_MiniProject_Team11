"""
Topology Handler Engine for Dynamic SDN Topologies.
Topic 27: Congestion Detection and Dynamic Traffic Rerouting.

Manages how every element of the network topology (cables/links, bottlenecks,
senders, queues) reacts in real-time to administrative controls and SDN rerouting.
Bridges the loaded TopologyDefinition (.toponet), NetworkEmulator, senders,
and GUI sidebar controls.
"""

import logging
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger("TopologyHandler")


class CableElement:
    """Represents a physical or virtual cable/link in the network topology."""

    def __init__(
        self,
        cable_id: str,
        name: str,
        cable_type: str,
        src: str,
        dst: str,
        capacity_mbps: float = 10.0,
        delay_ms: float = 5.0,
        queue_limit: int = 100,
        path_segment: str = ""
    ):
        self.cable_id = cable_id
        self.name = name
        self.cable_type = cable_type  # 'primary_bottleneck', 'alternate_bottleneck', 'host_edge'
        self.src = src
        self.dst = dst
        self.capacity_mbps = float(capacity_mbps)
        self.delay_ms = float(delay_ms)
        self.queue_limit = int(queue_limit)
        self.path_segment = path_segment
        self.is_active = True
        self.is_congested = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cable_id": self.cable_id,
            "name": self.name,
            "cable_type": self.cable_type,
            "src": self.src,
            "dst": self.dst,
            "capacity_mbps": self.capacity_mbps,
            "delay_ms": self.delay_ms,
            "queue_limit": self.queue_limit,
            "path_segment": self.path_segment,
            "is_active": self.is_active,
            "is_congested": self.is_congested
        }


class SenderElement:
    """Represents an active or configurable traffic sender in the topology."""

    def __init__(
        self,
        sender_id: str,
        name: str,
        host_id: str,
        target_ip: str,
        target_port: int,
        rate_mbps: float = 6.0,
        role: str = "main_sender"
    ):
        self.sender_id = sender_id
        self.name = name
        self.host_id = host_id
        self.target_ip = target_ip
        self.target_port = int(target_port)
        self.rate_mbps = float(rate_mbps)
        self.role = role  # 'main_sender' or 'cross_sender'
        self.is_running = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sender_id": self.sender_id,
            "name": self.name,
            "host_id": self.host_id,
            "target_ip": self.target_ip,
            "target_port": self.target_port,
            "rate_mbps": self.rate_mbps,
            "role": self.role,
            "is_running": self.is_running
        }


class TopologyHandler:
    """
    Central manager for dynamic topology interactions.
    Coordinates cable bottleneck adjustments, queue constraints, sender pacing rates,
    and runtime reactions across the network emulator and GUI sidebar.
    """

    def __init__(self, topo_def=None, emulator=None, sdn_controller=None):
        self.topo_def = topo_def
        self.emulator = emulator
        self.sdn_controller = sdn_controller

        self.main_sender = None
        self.congestion_gen = None

        self.cables: Dict[str, CableElement] = {}
        self.senders: Dict[str, SenderElement] = {}
        self._change_listeners: List[Callable[[str, str, Any], None]] = []

        if topo_def:
            self.load_from_definition(topo_def)

    def attach_subsystems(self, emulator=None, sdn_controller=None, main_sender=None, congestion_gen=None):
        """Binds backend network execution components to this topology handler."""
        if emulator:
            self.emulator = emulator
        if sdn_controller:
            self.sdn_controller = sdn_controller
        if main_sender:
            self.main_sender = main_sender
        if congestion_gen:
            self.congestion_gen = congestion_gen

    def register_change_listener(self, cb: Callable[[str, str, Any], None]):
        """Registers a callback for topology element state changes: cb(element_type, element_id, value)."""
        if cb not in self._change_listeners:
            self._change_listeners.append(cb)

    def _notify_listeners(self, element_type: str, element_id: str, value: Any):
        for cb in self._change_listeners:
            try:
                cb(element_type, element_id, value)
            except Exception as e:
                logger.error(f"[TopologyHandler] Listener notification error: {e}")

    def load_from_definition(self, topo_def):
        """Populates managed cables and senders from a parsed TopologyDefinition."""
        self.topo_def = topo_def
        self.cables.clear()
        self.senders.clear()

        # Build cable elements from links and paths
        path_a_info = topo_def.get_path("path_a") or {}
        path_b_info = topo_def.get_path("path_b") or {}

        # 1. Primary bottleneck cable (Path A)
        cap_a = float(path_a_info.get("capacity_mbps", 10.0))
        del_a = float(path_a_info.get("delay_ms", 5.0))
        q_a = int(path_a_info.get("queue_limit", 100))
        self.cables["cable_path_a"] = CableElement(
            cable_id="cable_path_a",
            name="Path-A Cable (S1->S2->S4)",
            cable_type="primary_bottleneck",
            src="s1",
            dst="s4",
            capacity_mbps=cap_a,
            delay_ms=del_a,
            queue_limit=q_a,
            path_segment="path_a"
        )

        # 2. Alternate bottleneck cable (Path B)
        cap_b = float(path_b_info.get("capacity_mbps", 10.0))
        del_b = float(path_b_info.get("delay_ms", 15.0))
        q_b = int(path_b_info.get("queue_limit", 100))
        self.cables["cable_path_b"] = CableElement(
            cable_id="cable_path_b",
            name="Path-B Cable (S1->S3->S4)",
            cable_type="alternate_bottleneck",
            src="s1",
            dst="s4",
            capacity_mbps=cap_b,
            delay_ms=del_b,
            queue_limit=q_b,
            path_segment="path_b"
        )

        # 3. Host Edge Cables
        for lk in topo_def.links:
            if lk.get("type") == "host_edge":
                lk_id = lk.get("id", f"{lk['src']}_{lk['dst']}")
                self.cables[lk_id] = CableElement(
                    cable_id=lk_id,
                    name=lk.get("label", lk_id),
                    cable_type="host_edge",
                    src=lk["src"],
                    dst=lk["dst"],
                    capacity_mbps=float(lk.get("bw_mbps", 100.0)),
                    delay_ms=float(lk.get("delay_ms", 1.0)),
                    queue_limit=int(lk.get("max_queue", 1000)),
                    path_segment=""
                )

        # 4. Senders from traffic profile
        prof = topo_def.traffic_profile or {}
        main_prof = prof.get("main_stream", {})
        self.senders["main_sender"] = SenderElement(
            sender_id="main_sender",
            name="Main Stream Sender (H1)",
            host_id=main_prof.get("src_host", "h1"),
            target_ip="127.0.0.1",
            target_port=main_prof.get("dst_port", 9999),
            rate_mbps=float(main_prof.get("nominal_rate_mbps", 6.0)),
            role="main_sender"
        )

        cross_prof = prof.get("cross_traffic", {})
        self.senders["cross_sender"] = SenderElement(
            sender_id="cross_sender",
            name="Cross Congestion Burst (H3)",
            host_id=cross_prof.get("src_host", "h3"),
            target_ip="127.0.0.1",
            target_port=cross_prof.get("dst_port", 9998),
            rate_mbps=float(cross_prof.get("burst_rate_mbps", 7.0)),
            role="cross_sender"
        )

        # Apply to emulator if attached
        if self.emulator:
            self.emulator.apply_topology(topo_def)

        self._notify_listeners("topology", "reloaded", topo_def)
        logger.info(f"[TopologyHandler] Initialized {len(self.cables)} cables and {len(self.senders)} senders.")

    # -------------------------------------------------------------------------
    # Cable Bottleneck Controls & Real-Time Reactions
    # -------------------------------------------------------------------------
    def get_cable(self, cable_id: str) -> Optional[CableElement]:
        """Returns cable element by ID."""
        return self.cables.get(cable_id)

    def set_cable_bottleneck(self, cable_id: str, capacity_mbps: float):
        """
        Dynamically adjusts bottleneck bandwidth for a specific cable.
        Reacts immediately on the underlying network emulator links.
        """
        cable = self.cables.get(cable_id)
        if not cable:
            # Check shortcut alias
            if cable_id.lower() in ("path_a", "a"):
                cable = self.cables.get("cable_path_a")
            elif cable_id.lower() in ("path_b", "b"):
                cable = self.cables.get("cable_path_b")

        if not cable:
            logger.warning(f"[TopologyHandler] Cable '{cable_id}' not found.")
            return

        capacity_mbps = max(1.0, min(50.0, float(capacity_mbps)))
        cable.capacity_mbps = capacity_mbps

        # Apply to emulator
        if self.emulator:
            if cable.cable_id == "cable_path_a" or cable.path_segment == "path_a":
                self.emulator.link_path_a.set_capacity_mbps(capacity_mbps)
            elif cable.cable_id == "cable_path_b" or cable.path_segment == "path_b":
                self.emulator.link_path_b.set_capacity_mbps(capacity_mbps)

        self._notify_listeners("cable_bottleneck", cable.cable_id, capacity_mbps)
        logger.info(f"[TopologyHandler] Cable '{cable.name}' bottleneck set to {capacity_mbps:.1f} Mbps.")

    def set_cable_queue_limit(self, cable_id: str, queue_limit: int):
        """Dynamically adjusts the queue buffer limit of a cable."""
        cable = self.cables.get(cable_id)
        if not cable:
            if cable_id.lower() in ("path_a", "a"):
                cable = self.cables.get("cable_path_a")
            elif cable_id.lower() in ("path_b", "b"):
                cable = self.cables.get("cable_path_b")

        limit = max(10, min(500, int(queue_limit)))
        if cable:
            cable.queue_limit = limit

        if self.emulator:
            if cable_id in ("all", "both"):
                self.emulator.link_path_a.set_max_queue(limit)
                self.emulator.link_path_b.set_max_queue(limit)
                if "cable_path_a" in self.cables:
                    self.cables["cable_path_a"].queue_limit = limit
                if "cable_path_b" in self.cables:
                    self.cables["cable_path_b"].queue_limit = limit
            elif cable and (cable.cable_id == "cable_path_a" or cable.path_segment == "path_a"):
                self.emulator.link_path_a.set_max_queue(limit)
            elif cable and (cable.cable_id == "cable_path_b" or cable.path_segment == "path_b"):
                self.emulator.link_path_b.set_max_queue(limit)

        self._notify_listeners("cable_queue", cable_id, limit)

    def set_cable_delay(self, cable_id: str, delay_ms: float):
        """Dynamically adjusts propagation delay of a cable."""
        cable = self.cables.get(cable_id)
        if not cable:
            if cable_id.lower() in ("path_a", "a"):
                cable = self.cables.get("cable_path_a")
            elif cable_id.lower() in ("path_b", "b"):
                cable = self.cables.get("cable_path_b")

        if not cable:
            return

        delay_ms = max(0.1, float(delay_ms))
        cable.delay_ms = delay_ms

        if self.emulator:
            if cable.cable_id == "cable_path_a" or cable.path_segment == "path_a":
                self.emulator.link_path_a.set_delay_ms(delay_ms)
            elif cable.cable_id == "cable_path_b" or cable.path_segment == "path_b":
                self.emulator.link_path_b.set_delay_ms(delay_ms)

        self._notify_listeners("cable_delay", cable.cable_id, delay_ms)

    # -------------------------------------------------------------------------
    # Sender Controls & Real-Time Reactions
    # -------------------------------------------------------------------------
    def get_sender(self, sender_id: str) -> Optional[SenderElement]:
        """Returns sender element by ID."""
        return self.senders.get(sender_id)

    def set_sender_rate(self, sender_id: str, rate_mbps: float):
        """
        Dynamically adjusts sending rate of a specific traffic sender.
        Immediately updates running socket sender instances.
        """
        sender = self.senders.get(sender_id)
        if not sender:
            # Check shortcut aliases
            if sender_id.lower() in ("main", "h1"):
                sender = self.senders.get("main_sender")
            elif sender_id.lower() in ("cross", "h3"):
                sender = self.senders.get("cross_sender")

        if not sender:
            logger.warning(f"[TopologyHandler] Sender '{sender_id}' not found.")
            return

        rate_mbps = max(0.5, min(30.0, float(rate_mbps)))
        sender.rate_mbps = rate_mbps

        # Apply to active sender instance
        if sender.sender_id == "main_sender" and self.main_sender:
            self.main_sender.set_rate(rate_mbps)
        elif sender.sender_id == "cross_sender" and self.congestion_gen:
            self.congestion_gen.rate_mbps = rate_mbps

        self._notify_listeners("sender_rate", sender.sender_id, rate_mbps)
        logger.info(f"[TopologyHandler] Sender '{sender.name}' sending rate set to {rate_mbps:.1f} Mbps.")

    def on_reroute(self, active_path: str):
        """Reacts to SDN rerouting decisions by marking cable active/inactive states."""
        is_path_a = (active_path.lower() in ("path_a", "a", "primary"))
        if "cable_path_a" in self.cables:
            self.cables["cable_path_a"].is_active = is_path_a
        if "cable_path_b" in self.cables:
            self.cables["cable_path_b"].is_active = not is_path_a
        self._notify_listeners("path_reroute", active_path, is_path_a)

    def reset_defaults(self):
        """Restores default capacities, delays, queues, and send rates."""
        if self.topo_def:
            self.load_from_definition(self.topo_def)
        else:
            self.set_cable_bottleneck("cable_path_a", 10.0)
            self.set_cable_bottleneck("cable_path_b", 10.0)
            self.set_cable_queue_limit("all", 100)
            self.set_sender_rate("main_sender", 6.0)
            self.set_sender_rate("cross_sender", 7.0)
