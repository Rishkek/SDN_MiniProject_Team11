"""
TopoEditor — Topology Data Model, Validation, and Undo/Redo Engine.
Manages network graph state, device parameters, links, and history.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set
import re

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QUndoStack, QUndoCommand


@dataclass
class HostData:
    id: str
    name: str = ""
    ip: str = "10.0.0.1"
    role: str = "both"  # "sender", "receiver", "both", "main_sender", "cross_sender", etc.
    x: float = 0.5
    y: float = 0.5
    subtext: str = ""
    color: str = "#1e66f5"
    connected_to: str = ""
    send_rate_mbps: float = 6.0
    max_receive_rate_mbps: float = 10.0
    packet_size_bytes: int = 1024
    send_to: str = ""
    receive_from: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            self.name = self.id.upper()
        if not self.subtext:
            self.subtext = self.ip

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "name": self.name,
            "ip": self.ip,
            "role": self.role,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "subtext": self.subtext,
            "color": self.color,
            "connected_to": self.connected_to,
            "send_rate_mbps": self.send_rate_mbps,
            "max_receive_rate_mbps": self.max_receive_rate_mbps,
            "packet_size_bytes": self.packet_size_bytes,
            "send_to": self.send_to,
            "receive_from": self.receive_from
        }
        for k, v in self.extra.items():
            if k not in d:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HostData":
        known = {
            "id", "name", "ip", "role", "x", "y", "subtext", "color",
            "connected_to", "send_rate_mbps", "max_receive_rate_mbps",
            "packet_size_bytes", "send_to", "receive_from"
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            id=str(data.get("id", "")).strip(),
            name=str(data.get("name", "")).strip(),
            ip=str(data.get("ip", "10.0.0.1")).strip(),
            role=str(data.get("role", "both")).strip(),
            x=float(data.get("x", 0.5)),
            y=float(data.get("y", 0.5)),
            subtext=str(data.get("subtext", "")).strip(),
            color=str(data.get("color", "#1e66f5")).strip(),
            connected_to=str(data.get("connected_to", "")).strip(),
            send_rate_mbps=float(data.get("send_rate_mbps", 6.0)),
            max_receive_rate_mbps=float(data.get("max_receive_rate_mbps", 10.0)),
            packet_size_bytes=int(data.get("packet_size_bytes", 1024)),
            send_to=str(data.get("send_to", "")).strip(),
            receive_from=str(data.get("receive_from", "")).strip(),
            extra=extra
        )


@dataclass
class SwitchData:
    id: str
    dpid: int = 1
    name: str = ""
    role: str = "normal"  # "ingress", "primary", "backup", "egress", "normal", "core", "edge"
    protocols: str = "OpenFlow13"
    x: float = 0.5
    y: float = 0.5
    subtext: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            self.name = self.id.upper()
        if not self.subtext:
            self.subtext = self.role.capitalize() if self.role else "Switch"

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "dpid": self.dpid,
            "name": self.name,
            "role": self.role,
            "protocols": self.protocols,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "subtext": self.subtext
        }
        for k, v in self.extra.items():
            if k not in d:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SwitchData":
        known = {"id", "dpid", "name", "role", "protocols", "x", "y", "subtext"}
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            id=str(data.get("id", "")).strip(),
            dpid=int(data.get("dpid", 1)),
            name=str(data.get("name", "")).strip(),
            role=str(data.get("role", "normal")).strip(),
            protocols=str(data.get("protocols", "OpenFlow13")).strip(),
            x=float(data.get("x", 0.5)),
            y=float(data.get("y", 0.5)),
            subtext=str(data.get("subtext", "")).strip(),
            extra=extra
        )


@dataclass
class LinkData:
    id: str
    src: str
    dst: str
    bw_mbps: float = 10.0
    delay_ms: float = 5.0
    max_queue: int = 100
    loss_pct: float = 0.0
    label: str = ""
    type: str = "switch_link"  # "host_edge", "switch_link", "bottleneck"
    pen_color: str = "#89b4fa"
    path_segment: str = ""  # "path_a", "path_b", etc.
    is_bottleneck: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.label:
            self.label = f"{self.bw_mbps:.1f} Mbps"

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "src": self.src,
            "dst": self.dst,
            "label": self.label,
            "bw_mbps": self.bw_mbps,
            "delay_ms": self.delay_ms,
            "max_queue": self.max_queue,
            "loss_pct": self.loss_pct,
            "type": self.type,
            "pen_color": self.pen_color,
            "path_segment": self.path_segment,
            "is_bottleneck": self.is_bottleneck
        }
        for k, v in self.extra.items():
            if k not in d:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LinkData":
        known = {
            "id", "src", "dst", "bw_mbps", "delay_ms", "max_queue",
            "loss_pct", "label", "type", "pen_color", "path_segment", "is_bottleneck"
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            id=str(data.get("id", "")).strip(),
            src=str(data.get("src", "")).strip(),
            dst=str(data.get("dst", "")).strip(),
            bw_mbps=float(data.get("bw_mbps", 10.0)),
            delay_ms=float(data.get("delay_ms", 5.0)),
            max_queue=int(data.get("max_queue", 100)),
            loss_pct=float(data.get("loss_pct", 0.0)),
            label=str(data.get("label", "")).strip(),
            type=str(data.get("type", "switch_link")).strip(),
            pen_color=str(data.get("pen_color", "#89b4fa")).strip(),
            path_segment=str(data.get("path_segment", "")).strip(),
            is_bottleneck=bool(data.get("is_bottleneck", False)),
            extra=extra
        )


class AddHostCommand(QUndoCommand):
    def __init__(self, model: "TopologyModel", host: HostData):
        super().__init__(f"Add Host {host.id.upper()}")
        self.model = model
        self.host = host

    def redo(self):
        self.model._raw_add_host(self.host)

    def undo(self):
        self.model._raw_remove_host(self.host.id)


class AddSwitchCommand(QUndoCommand):
    def __init__(self, model: "TopologyModel", sw: SwitchData):
        super().__init__(f"Add Switch {sw.id.upper()}")
        self.model = model
        self.sw = sw

    def redo(self):
        self.model._raw_add_switch(self.sw)

    def undo(self):
        self.model._raw_remove_switch(self.sw.id)


class DeleteDeviceCommand(QUndoCommand):
    def __init__(self, model: "TopologyModel", device_id: str):
        super().__init__(f"Delete Device {device_id.upper()}")
        self.model = model
        self.device_id = device_id
        self.is_host = device_id in model.hosts
        self.device_data = model.hosts.get(device_id) if self.is_host else model.switches.get(device_id)
        # Record all links connected to this device so undo restores them
        self.connected_links = [lk for lk in model.links.values() if lk.src == device_id or lk.dst == device_id]

    def redo(self):
        for lk in self.connected_links:
            self.model._raw_remove_link(lk.id)
        if self.is_host:
            self.model._raw_remove_host(self.device_id)
        else:
            self.model._raw_remove_switch(self.device_id)

    def undo(self):
        if self.is_host and self.device_data:
            self.model._raw_add_host(self.device_data)
        elif self.device_data:
            self.model._raw_add_switch(self.device_data)
        for lk in self.connected_links:
            self.model._raw_add_link(lk)


class MoveDeviceCommand(QUndoCommand):
    def __init__(self, model: "TopologyModel", moves: List[Tuple[str, float, float, float, float]]):
        """moves: list of (device_id, old_x, old_y, new_x, new_y)"""
        super().__init__("Move Devices")
        self.model = model
        self.moves = moves

    def redo(self):
        for dev_id, _, _, nx, ny in self.moves:
            self.model._raw_set_pos(dev_id, nx, ny)

    def undo(self):
        for dev_id, ox, oy, _, _ in self.moves:
            self.model._raw_set_pos(dev_id, ox, oy)


class AddLinkCommand(QUndoCommand):
    def __init__(self, model: "TopologyModel", link: LinkData):
        super().__init__(f"Add Link {link.src}->{link.dst}")
        self.model = model
        self.link = link

    def redo(self):
        self.model._raw_add_link(self.link)

    def undo(self):
        self.model._raw_remove_link(self.link.id)


class DeleteLinkCommand(QUndoCommand):
    def __init__(self, model: "TopologyModel", link_id: str):
        super().__init__(f"Delete Link {link_id}")
        self.model = model
        self.link_id = link_id
        self.link_data = model.links.get(link_id)

    def redo(self):
        self.model._raw_remove_link(self.link_id)

    def undo(self):
        if self.link_data:
            self.model._raw_add_link(self.link_data)


class UpdateHostCommand(QUndoCommand):
    def __init__(self, model: "TopologyModel", host_id: str, new_data: HostData):
        super().__init__(f"Edit Host {host_id.upper()}")
        self.model = model
        self.host_id = host_id
        self.old_data = model.hosts.get(host_id)
        self.new_data = new_data

    def redo(self):
        self.model._raw_update_host(self.host_id, self.new_data)

    def undo(self):
        if self.old_data:
            self.model._raw_update_host(self.new_data.id, self.old_data)


class UpdateSwitchCommand(QUndoCommand):
    def __init__(self, model: "TopologyModel", switch_id: str, new_data: SwitchData):
        super().__init__(f"Edit Switch {switch_id.upper()}")
        self.model = model
        self.switch_id = switch_id
        self.old_data = model.switches.get(switch_id)
        self.new_data = new_data

    def redo(self):
        self.model._raw_update_switch(self.switch_id, self.new_data)

    def undo(self):
        if self.old_data:
            self.model._raw_update_switch(self.new_data.id, self.old_data)


class UpdateLinkCommand(QUndoCommand):
    def __init__(self, model: "TopologyModel", link_id: str, new_data: LinkData):
        super().__init__(f"Edit Link {link_id}")
        self.model = model
        self.link_id = link_id
        self.old_data = model.links.get(link_id)
        self.new_data = new_data

    def redo(self):
        self.model._raw_update_link(self.link_id, self.new_data)

    def undo(self):
        if self.old_data:
            self.model._raw_update_link(self.link_id, self.old_data)


class TopologyModel(QObject):
    """
    Central topology graph model.
    Maintains hosts, switches, links, metadata, undo/redo stack, and dirty state.
    """
    # Signals
    structure_changed = pyqtSignal()
    device_added = pyqtSignal(str)     # device_id
    device_removed = pyqtSignal(str)   # device_id
    device_updated = pyqtSignal(str)   # device_id
    device_moved = pyqtSignal(str, float, float)  # device_id, x, y
    link_added = pyqtSignal(str)       # link_id
    link_removed = pyqtSignal(str)     # link_id
    link_updated = pyqtSignal(str)     # link_id
    dirty_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.topology_name = "Untitled Topology"
        self.description = ""
        self.format = "topologia-network"
        self.version = "1.0"
        self.current_filepath: Optional[str] = None

        self.hosts: Dict[str, HostData] = {}
        self.switches: Dict[str, SwitchData] = {}
        self.links: Dict[str, LinkData] = {}

        self.paths: Dict[str, Any] = {}
        self.traffic_profile: Dict[str, Any] = {}
        self.sdn_policy: Dict[str, Any] = {}
        self.extra_fields: Dict[str, Any] = {}

        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)

    def _on_clean_changed(self, is_clean: bool):
        self.dirty_changed.emit(not is_clean)

    @property
    def is_dirty(self) -> bool:
        return not self.undo_stack.isClean()

    def set_clean(self):
        self.undo_stack.setClean()

    def clear(self):
        """Resets the model to a completely empty state."""
        self.hosts.clear()
        self.switches.clear()
        self.links.clear()
        self.paths.clear()
        self.traffic_profile.clear()
        self.sdn_policy.clear()
        self.extra_fields.clear()
        self.topology_name = "Untitled Topology"
        self.description = ""
        self.current_filepath = None
        self.undo_stack.clear()
        self.structure_changed.emit()

    # -------------------------------------------------------------------------
    # ID Generation & Lookups
    # -------------------------------------------------------------------------
    def generate_next_host_id(self) -> str:
        """Finds next available Host ID: H1, H2, H3, ..."""
        existing_nums = set()
        for hid in self.hosts.keys():
            m = re.match(r"^h(\d+)$", hid, re.IGNORECASE)
            if m:
                existing_nums.add(int(m.group(1)))
        next_num = 1
        while next_num in existing_nums:
            next_num += 1
        return f"h{next_num}"

    def generate_next_switch_id(self) -> str:
        """Finds next available Switch ID: S1, S2, S3, ..."""
        existing_nums = set()
        for sid in self.switches.keys():
            m = re.match(r"^s(\d+)$", sid, re.IGNORECASE)
            if m:
                existing_nums.add(int(m.group(1)))
        next_num = 1
        while next_num in existing_nums:
            next_num += 1
        return f"s{next_num}"

    def generate_next_link_id(self, src: str, dst: str) -> str:
        """Generates standard link ID, e.g. link_h1_s1 or link_s1_s2."""
        base_id = f"link_{src.lower()}_{dst.lower()}"
        if base_id not in self.links:
            return base_id
        # Disambiguate if needed
        c = 2
        while f"{base_id}_{c}" in self.links:
            c += 1
        return f"{base_id}_{c}"

    def get_device(self, dev_id: str) -> Optional[Any]:
        dev_id = dev_id.lower()
        if dev_id in self.hosts:
            return self.hosts[dev_id]
        if dev_id in self.switches:
            return self.switches[dev_id]
        return None

    def get_connected_links(self, dev_id: str) -> List[LinkData]:
        dev_id = dev_id.lower()
        return [lk for lk in self.links.values() if lk.src.lower() == dev_id or lk.dst.lower() == dev_id]

    def find_link_between(self, dev_a: str, dev_b: str) -> Optional[LinkData]:
        """Finds an existing undirected link between dev_a and dev_b."""
        a, b = dev_a.lower(), dev_b.lower()
        for lk in self.links.values():
            s, d = lk.src.lower(), lk.dst.lower()
            if (s == a and d == b) or (s == b and d == a):
                return lk
        return None

    # -------------------------------------------------------------------------
    # High-level undoable commands
    # -------------------------------------------------------------------------
    def add_host(self, host: HostData):
        self.undo_stack.push(AddHostCommand(self, host))

    def add_switch(self, sw: SwitchData):
        self.undo_stack.push(AddSwitchCommand(self, sw))

    def delete_device(self, device_id: str):
        if device_id.lower() in self.hosts or device_id.lower() in self.switches:
            self.undo_stack.push(DeleteDeviceCommand(self, device_id.lower()))

    def move_devices(self, moves: List[Tuple[str, float, float, float, float]]):
        if moves:
            self.undo_stack.push(MoveDeviceCommand(self, moves))

    def add_link(self, link: LinkData):
        self.undo_stack.push(AddLinkCommand(self, link))

    def delete_link(self, link_id: str):
        if link_id in self.links:
            self.undo_stack.push(DeleteLinkCommand(self, link_id))

    def update_host(self, host_id: str, new_data: HostData):
        self.undo_stack.push(UpdateHostCommand(self, host_id, new_data))

    def update_switch(self, switch_id: str, new_data: SwitchData):
        self.undo_stack.push(UpdateSwitchCommand(self, switch_id, new_data))

    def update_link(self, link_id: str, new_data: LinkData):
        self.undo_stack.push(UpdateLinkCommand(self, link_id, new_data))

    # -------------------------------------------------------------------------
    # Low-level primitives (used by undo commands and loader)
    # -------------------------------------------------------------------------
    def _raw_add_host(self, host: HostData):
        hid = host.id.lower()
        self.hosts[hid] = host
        self.device_added.emit(hid)
        self.structure_changed.emit()

    def _raw_remove_host(self, host_id: str):
        hid = host_id.lower()
        if hid in self.hosts:
            del self.hosts[hid]
            self.device_removed.emit(hid)
            self.structure_changed.emit()

    def _raw_update_host(self, old_id: str, new_data: HostData):
        old_id = old_id.lower()
        new_id = new_data.id.lower()
        if old_id in self.hosts:
            del self.hosts[old_id]
        self.hosts[new_id] = new_data
        # If ID changed, update connected links
        if old_id != new_id:
            for lk in self.links.values():
                if lk.src.lower() == old_id:
                    lk.src = new_id
                if lk.dst.lower() == old_id:
                    lk.dst = new_id
        self.device_updated.emit(new_id)
        self.structure_changed.emit()

    def _raw_add_switch(self, sw: SwitchData):
        sid = sw.id.lower()
        self.switches[sid] = sw
        self.device_added.emit(sid)
        self.structure_changed.emit()

    def _raw_remove_switch(self, switch_id: str):
        sid = switch_id.lower()
        if sid in self.switches:
            del self.switches[sid]
            self.device_removed.emit(sid)
            self.structure_changed.emit()

    def _raw_update_switch(self, old_id: str, new_data: SwitchData):
        old_id = old_id.lower()
        new_id = new_data.id.lower()
        if old_id in self.switches:
            del self.switches[old_id]
        self.switches[new_id] = new_data
        if old_id != new_id:
            for lk in self.links.values():
                if lk.src.lower() == old_id:
                    lk.src = new_id
                if lk.dst.lower() == old_id:
                    lk.dst = new_id
        self.device_updated.emit(new_id)
        self.structure_changed.emit()

    def _raw_set_pos(self, dev_id: str, x: float, y: float):
        dev = self.get_device(dev_id)
        if dev:
            dev.x = max(0.02, min(0.98, x))
            dev.y = max(0.02, min(0.98, y))
            self.device_moved.emit(dev_id.lower(), dev.x, dev.y)

    def _raw_add_link(self, link: LinkData):
        self.links[link.id] = link
        # If host connected to switch, update host's connected_to
        if link.src.lower() in self.hosts and link.dst.lower() in self.switches:
            self.hosts[link.src.lower()].connected_to = link.dst.lower()
        elif link.dst.lower() in self.hosts and link.src.lower() in self.switches:
            self.hosts[link.dst.lower()].connected_to = link.src.lower()

        self.link_added.emit(link.id)
        self.structure_changed.emit()

    def _raw_remove_link(self, link_id: str):
        if link_id in self.links:
            lk = self.links[link_id]
            # Reset connected_to if applicable
            if lk.src.lower() in self.hosts and self.hosts[lk.src.lower()].connected_to == lk.dst.lower():
                self.hosts[lk.src.lower()].connected_to = ""
            if lk.dst.lower() in self.hosts and self.hosts[lk.dst.lower()].connected_to == lk.src.lower():
                self.hosts[lk.dst.lower()].connected_to = ""
            del self.links[link_id]
            self.link_removed.emit(link_id)
            self.structure_changed.emit()

    def _raw_update_link(self, link_id: str, new_data: LinkData):
        self.links[link_id] = new_data
        self.link_updated.emit(link_id)
        self.structure_changed.emit()

    # -------------------------------------------------------------------------
    # Import / Export
    # -------------------------------------------------------------------------
    def load_from_dict(self, data: Dict[str, Any]):
        """Populates the model from parsed toponet dictionary."""
        self.clear()
        self.topology_name = data.get("topology_name", "Untitled Topology")
        self.description = data.get("description", "")
        self.format = data.get("format", "topologia-network")
        self.version = data.get("version", "1.0")
        self.current_filepath = data.get("filepath", None)
        self.paths = data.get("paths", {})
        self.traffic_profile = data.get("traffic_profile", {})
        self.sdn_policy = data.get("sdn_policy", {})
        self.extra_fields = data.get("extra_fields", {})

        for s_dict in data.get("switches", []):
            sw = SwitchData.from_dict(s_dict)
            self._raw_add_switch(sw)

        for h_dict in data.get("hosts", []):
            h = HostData.from_dict(h_dict)
            self._raw_add_host(h)

        for l_dict in data.get("links", []):
            lk = LinkData.from_dict(l_dict)
            self._raw_add_link(lk)

        self.undo_stack.clear()
        self.set_clean()
        self.structure_changed.emit()

    def to_dict(self) -> Dict[str, Any]:
        """Exports the model to a complete toponet-compatible dictionary."""
        # Auto-synchronize traffic profile with host configuration
        traffic_prof = dict(self.traffic_profile)
        # Find main sender/receiver
        main_senders = [h for h in self.hosts.values() if h.role in ("sender", "main_sender", "both") and h.send_to]
        if main_senders:
            primary_sender = main_senders[0]
            traffic_prof["main_stream"] = {
                "src_host": primary_sender.id,
                "dst_host": primary_sender.send_to,
                "dst_port": 9999,
                "nominal_rate_mbps": primary_sender.send_rate_mbps,
                "packet_size_bytes": primary_sender.packet_size_bytes
            }

        return {
            "format": self.format,
            "version": self.version,
            "topology_name": self.topology_name,
            "description": self.description,
            "switches": [s.to_dict() for s in self.switches.values()],
            "hosts": [h.to_dict() for h in self.hosts.values()],
            "links": [lk.to_dict() for lk in self.links.values()],
            "paths": self.paths,
            "traffic_profile": traffic_prof,
            "sdn_policy": self.sdn_policy,
            "extra_fields": self.extra_fields
        }

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------
    def validate(self) -> List[str]:
        """
        Validates the topology according to project specification Section 9:
          - Duplicate device IDs
          - Invalid link endpoints / missing endpoints
          - Duplicate links
          - Self-links
          - Invalid bandwidth values (<= 0)
          - Negative traffic rates
          - Invalid communication destinations (cannot send to self)
        Returns a list of human-readable error messages. An empty list means valid.
        """
        errors = []

        # 1. Device ID Collisions between Hosts and Switches
        host_ids = set(self.hosts.keys())
        switch_ids = set(self.switches.keys())
        overlap = host_ids.intersection(switch_ids)
        if overlap:
            for dup in overlap:
                errors.append(f"Device ID collision: '{dup}' is used for both a Host and a Switch.")

        # 2. Link Validations
        seen_pairs: Set[Tuple[str, str]] = set()
        all_device_ids = host_ids.union(switch_ids)

        for lk in self.links.values():
            s = lk.src.lower()
            d = lk.dst.lower()

            # Endpoints exist
            if not s or s not in all_device_ids:
                errors.append(f"Link '{lk.id}': Source endpoint '{lk.src}' does not exist.")
            if not d or d not in all_device_ids:
                errors.append(f"Link '{lk.id}': Destination endpoint '{lk.dst}' does not exist.")

            # Self-loops
            if s == d:
                errors.append(f"Link '{lk.id}': Connecting device '{s}' to itself is not permitted.")

            # Duplicate links between same device pair
            pair = tuple(sorted([s, d]))
            if pair in seen_pairs:
                errors.append(f"Duplicate connection: Multiple links exist between '{pair[0]}' and '{pair[1]}'.")
            else:
                seen_pairs.add(pair)

            # Bandwidth > 0
            if lk.bw_mbps <= 0:
                errors.append(f"Link '{lk.id}': Maximum link rate must be greater than 0 Mbps (got {lk.bw_mbps}).")

            # Delay >= 0
            if lk.delay_ms < 0:
                errors.append(f"Link '{lk.id}': Delay cannot be negative (got {lk.delay_ms} ms).")

            # Loss percent 0 to 100
            if lk.loss_pct < 0 or lk.loss_pct > 100:
                errors.append(f"Link '{lk.id}': Packet loss must be between 0% and 100% (got {lk.loss_pct}%).")

        # 3. Host Traffic & Communication Configurations
        for h in self.hosts.values():
            if h.send_rate_mbps < 0:
                errors.append(f"Host '{h.id}': Send rate cannot be negative (got {h.send_rate_mbps} Mbps).")
            if h.max_receive_rate_mbps < 0:
                errors.append(f"Host '{h.id}': Max receive rate cannot be negative (got {h.max_receive_rate_mbps} Mbps).")

            # Send To checks
            if h.send_to:
                if h.send_to.lower() == h.id.lower():
                    errors.append(f"Host '{h.id}': A host cannot set itself as its communication destination ('Send To').")
                elif h.send_to.lower() not in host_ids:
                    errors.append(f"Host '{h.id}': Destination host '{h.send_to}' does not exist.")

            # Receive From checks
            if h.receive_from:
                if h.receive_from.lower() == h.id.lower():
                    errors.append(f"Host '{h.id}': A host cannot set itself as its source ('Receive From').")
                elif h.receive_from.lower() not in host_ids:
                    errors.append(f"Host '{h.id}': Source host '{h.receive_from}' does not exist.")

        return errors
