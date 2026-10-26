"""
Topology Loader Engine for Topologia (.tp) Files.
Topic 27: SDN-Socket Programming & Custom Network Topology Loading.

Supports loading, validating, and translating custom .tp topology files
exported by Topologia for use in emulation, visualization, and Mininet.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("TopologyLoader")


class InvalidTopologyExtensionError(ValueError):
    """Raised when an attempt is made to load a file without the required .tp extension."""
    pass


class CorruptTopologyFileError(ValueError):
    """Raised when a .tp file is unreadable, malformed, or missing required topology schema."""
    pass


class TopologyDefinition:
    """
    Structured representation of a parsed .tp network topology.
    Encapsulates switches, hosts, links, path routing constraints,
    visualization coordinates, and SDN policies.
    """

    def __init__(self, data: Dict[str, Any], filepath: str = ""):
        self.raw_data = data
        self.filepath = filepath
        self.format = data.get("format", "topologia-tp")
        self.version = data.get("version", "1.0")
        self.name = data.get("topology_name", "Custom Topology")
        self.description = data.get("description", "")

        self.switches: List[Dict[str, Any]] = data.get("switches", [])
        self.hosts: List[Dict[str, Any]] = data.get("hosts", [])
        self.links: List[Dict[str, Any]] = data.get("links", [])
        self.paths: Dict[str, Any] = data.get("paths", {})
        self.traffic_profile: Dict[str, Any] = data.get("traffic_profile", {})
        self.sdn_policy: Dict[str, Any] = data.get("sdn_policy", {})

        # Fast lookup maps
        self._node_map: Dict[str, Dict[str, Any]] = {}
        for s in self.switches:
            s_id = s.get("id", "").lower()
            if s_id:
                self._node_map[s_id] = s
        for h in self.hosts:
            h_id = h.get("id", "").lower()
            if h_id:
                self._node_map[h_id] = h

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves node configuration dictionary by ID (e.g. 's1', 'h1')."""
        return self._node_map.get(node_id.lower())

    def get_node_pos(self, node_id: str, default: Tuple[float, float] = (0.5, 0.5)) -> Tuple[float, float]:
        """Returns normalized (x, y) coordinates in [0.0, 1.0] for canvas rendering."""
        node = self.get_node(node_id)
        if node and "x" in node and "y" in node:
            return float(node["x"]), float(node["y"])
        return default

    def get_path(self, path_key: str) -> Optional[Dict[str, Any]]:
        """Retrieves path specification by key ('path_a', 'path_b')."""
        return self.paths.get(path_key)

    def to_dict(self) -> Dict[str, Any]:
        """Exports definition back to serializable dictionary."""
        return self.raw_data

    def build_mininet_topo(self):
        """
        Dynamically constructs a Mininet Topo subclass using the .tp definition.
        Returns Topo instance if Mininet is installed, otherwise None.
        """
        try:
            from mininet.topo import Topo
        except ImportError:
            logger.warning("[TopologyLoader] Mininet library not available in current environment.")
            return None

        topo_self = self

        class DynamicLoadedTopo(Topo):
            def build(inner_self):
                # Add switches
                for sw in topo_self.switches:
                    sw_id = sw["id"]
                    proto = sw.get("protocols", "OpenFlow13")
                    inner_self.addSwitch(sw_id, protocols=proto)

                # Add hosts
                for h in topo_self.hosts:
                    h_id = h["id"]
                    ip = h.get("ip", "10.0.0.1")
                    inner_self.addHost(h_id, ip=f"{ip}/24", defaultRoute="via 10.0.0.254")

                # Add links
                for lk in topo_self.links:
                    src = lk["src"]
                    dst = lk["dst"]
                    bw = lk.get("bw_mbps", 10.0)
                    delay = f"{lk.get('delay_ms', 5.0)}ms"
                    q_max = lk.get("max_queue", 100)
                    inner_self.addLink(src, dst, bw=bw, delay=delay, max_queue_size=q_max)

        return DynamicLoadedTopo()


def validate_tp_extension(filepath: str):
    """Enforces that the specified path ends with the required .tp extension."""
    if not filepath or not filepath.lower().endswith(".tp"):
        _, ext = os.path.splitext(filepath)
        raise InvalidTopologyExtensionError(
            f"Invalid file extension '{ext or '<none>'}'. Only .tp topology files are supported."
        )


def load_topology(filepath: str) -> TopologyDefinition:
    """
    Loads and validates a .tp topology definition file.

    Parameters:
      filepath (str): Absolute or relative path to a .tp file.

    Returns:
      TopologyDefinition: Parsed and validated topology object.

    Raises:
      InvalidTopologyExtensionError: If filename does not end in .tp.
      FileNotFoundError: If file cannot be found.
      CorruptTopologyFileError: If JSON parsing fails or required fields are missing.
    """
    validate_tp_extension(filepath)

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Topology file not found: {filepath}")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise CorruptTopologyFileError(f"Failed to parse .tp file as JSON: {e}")

    # Validate essential schema
    if not isinstance(data, dict):
        raise CorruptTopologyFileError("Topologia (.tp) file must be a JSON object.")

    if "switches" not in data or not isinstance(data["switches"], list):
        raise CorruptTopologyFileError("Invalid .tp schema: missing 'switches' list.")

    if "hosts" not in data or not isinstance(data["hosts"], list):
        raise CorruptTopologyFileError("Invalid .tp schema: missing 'hosts' list.")

    if "links" not in data or not isinstance(data["links"], list):
        raise CorruptTopologyFileError("Invalid .tp schema: missing 'links' list.")

    topo = TopologyDefinition(data, filepath=os.path.abspath(filepath))
    logger.info(f"Loaded topology '{topo.name}' from {filepath} ({len(topo.switches)} switches, {len(topo.hosts)} hosts, {len(topo.links)} links)")
    return topo


def save_topology(topo_def: TopologyDefinition, filepath: str):
    """Saves a TopologyDefinition object to a .tp file."""
    validate_tp_extension(filepath)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(topo_def.to_dict(), f, indent=2)
    logger.info(f"Saved topology '{topo_def.name}' to {filepath}")


def get_default_topology_path() -> str:
    """Finds the default diamond.tp file path in workspace or source directories."""
    candidates = [
        "diamond.tp",
        os.path.join(os.path.dirname(__file__), "..", "diamond.tp"),
        os.path.join(os.path.dirname(__file__), "diamond.tp"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return "diamond.tp"


def get_default_topology() -> TopologyDefinition:
    """Loads default diamond topology from diamond.tp."""
    path = get_default_topology_path()
    if os.path.exists(path):
        return load_topology(path)
    # If not created on disk yet, raise or fallback
    raise FileNotFoundError(f"Default diamond.tp not found at {path}")
