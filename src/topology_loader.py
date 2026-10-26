"""
Topology Loader Engine for Topologia (.toponet) Files.
Topic 27: SDN-Socket Programming & Custom Network Topology Loading.

Supports loading, validating, and translating custom .toponet topology files
exported by Topologia for use in emulation, visualization, and Mininet.
"""

import os
import sys
import json
import logging
import argparse
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("TopologyLoader")

TOPOLOGY_FILE_EXTENSION = ".toponet"


class InvalidTopologyExtensionError(ValueError):
    """Raised when an attempt is made to load a file without the required .toponet extension."""
    pass


class CorruptTopologyFileError(ValueError):
    """Raised when a .toponet file is unreadable, malformed, or missing required topology schema."""
    pass


class TopologyDefinition:
    """
    Structured representation of a parsed .toponet network topology.
    Encapsulates switches, hosts, links, path routing constraints,
    visualization coordinates, and SDN policies.
    """

    def __init__(self, data: Dict[str, Any], filepath: str = ""):
        self.raw_data = data
        self.filepath = filepath
        self.format = data.get("format", "topologia-network")
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
        Dynamically constructs a Mininet Topo subclass using the .toponet definition.
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
    """
    Enforces that the specified path ends with the required .toponet extension.
    Accepts .toponet.
    """
    if not filepath or not filepath.lower().endswith(TOPOLOGY_FILE_EXTENSION):
        _, ext = os.path.splitext(filepath)
        raise InvalidTopologyExtensionError(
            f"Invalid file extension '{ext or '<none>'}'. Only {TOPOLOGY_FILE_EXTENSION} topology files are supported."
        )


def load_topology(filepath: str) -> TopologyDefinition:
    """
    Loads and validates a .toponet topology definition file.

    Parameters:
      filepath (str): Absolute or relative path to a .toponet file.

    Returns:
      TopologyDefinition: Parsed and validated topology object.

    Raises:
      InvalidTopologyExtensionError: If filename does not end in .toponet.
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
        raise CorruptTopologyFileError(f"Failed to parse .toponet file as JSON: {e}")

    # Validate essential schema
    if not isinstance(data, dict):
        raise CorruptTopologyFileError("Topologia (.toponet) file must be a JSON object.")

    if "switches" not in data or not isinstance(data["switches"], list):
        raise CorruptTopologyFileError("Invalid .toponet schema: missing 'switches' list.")

    if "hosts" not in data or not isinstance(data["hosts"], list):
        raise CorruptTopologyFileError("Invalid .toponet schema: missing 'hosts' list.")

    if "links" not in data or not isinstance(data["links"], list):
        raise CorruptTopologyFileError("Invalid .toponet schema: missing 'links' list.")

    topo = TopologyDefinition(data, filepath=os.path.abspath(filepath))
    logger.info(
        f"Loaded topology '{topo.name}' from {filepath} "
        f"({len(topo.switches)} switches, {len(topo.hosts)} hosts, {len(topo.links)} links)"
    )
    return topo


def save_topology(topo_def: TopologyDefinition, filepath: str):
    """Saves a TopologyDefinition object to a .toponet file."""
    validate_tp_extension(filepath)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(topo_def.to_dict(), f, indent=2)
    logger.info(f"Saved topology '{topo_def.name}' to {filepath}")


def get_default_topology_path() -> str:
    """Finds the default diamond.toponet file path in workspace or source directories."""
    candidates = [
        "diamond.toponet",
        os.path.join(os.path.dirname(__file__), "..", "diamond.toponet"),
        os.path.join(os.path.dirname(__file__), "diamond.toponet"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return "diamond.toponet"


def get_default_topology() -> TopologyDefinition:
    """Loads default diamond topology from diamond.toponet."""
    path = get_default_topology_path()
    if os.path.exists(path):
        return load_topology(path)
    raise FileNotFoundError(f"Default diamond.toponet not found at {path}")


def run_mininet_cli(tp_path: str = ""):
    """Runs Mininet environment using loaded .toponet topology file on Linux."""
    try:
        from mininet.net import Mininet
        from mininet.node import OVSKernelSwitch
        from mininet.link import TCLink
        from mininet.cli import CLI
        from mininet.log import setLogLevel, info
    except ImportError:
        print("[!] Mininet is not available in this environment. Please run inside an Ubuntu VM.")
        return

    path = tp_path or get_default_topology_path()
    print(f"[*] Loading Mininet topology from: {path}")
    topo_def = load_topology(path)
    topo = topo_def.build_mininet_topo()
    if not topo:
        print("[!] Failed to build Mininet Topo.")
        return

    setLogLevel("info")
    net = Mininet(topo=topo, switch=OVSKernelSwitch, link=TCLink, controller=None)
    net.start()
    info(f"[+] Mininet topology online with {len(topo_def.switches)} switches and {len(topo_def.hosts)} hosts.\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Topologia (.toponet) Topology Loader & Mininet CLI")
    parser.add_argument("file", nargs="?", default="", help="Path to .toponet topology file")
    parser.add_argument("--cli", action="store_true", help="Launch interactive Mininet CLI on Linux")
    args = parser.parse_args()

    target_file = args.file or get_default_topology_path()
    if args.cli:
        run_mininet_cli(target_file)
    else:
        try:
            t = load_topology(target_file)
            print(f"[OK] Successfully loaded '{t.name}' from {target_file}")
            print(f"     Switches: {[s['id'] for s in t.switches]}")
            print(f"     Hosts:    {[h['id'] for h in t.hosts]}")
            print(f"     Links:    {len(t.links)} total links")
        except Exception as err:
            print(f"[ERROR] Failed to load topology: {err}", file=sys.stderr)
            sys.exit(1)
