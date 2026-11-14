"""
Topology Loader Engine for JSON (.json) Files.
Topic 27: SDN-Socket Programming & Custom Network Topology Loading.

Supports loading, validating, and translating standard .json topology files
for use in emulation, visualization, and Mininet.
"""

import os
import sys
import json
import logging
import argparse
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("TopologyLoader")

TOPOLOGY_FILE_EXTENSION = ".json"


class InvalidTopologyExtensionError(ValueError):
    """Raised when an attempt is made to load a file without the required .json extension."""
    pass


class CorruptTopologyFileError(ValueError):
    """Raised when a .json file is unreadable, malformed, or missing required topology schema."""
    pass


def discover_all_simple_paths(
    switches: List[Dict[str, Any]],
    hosts: List[Dict[str, Any]],
    links: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Discovers all unique loop-free simple paths between Ingress and Egress switches
    using Depth-First Search (DFS) graph traversal.
    """
    if not switches:
        return {}

    sw_ids = {str(s.get("id", "")).lower(): s for s in switches if s.get("id")}
    if not sw_ids:
        return {}

    ingress_id = None
    egress_id = None

    for s in switches:
        role = str(s.get("role", "")).lower()
        if role == "ingress" and not ingress_id:
            ingress_id = str(s.get("id", "")).lower()
        elif role == "egress":
            egress_id = str(s.get("id", "")).lower()

    # Fallback to connected hosts
    if not ingress_id or not egress_id:
        for lk in links:
            src = str(lk.get("src", "")).lower()
            dst = str(lk.get("dst", "")).lower()
            if src in ("h1", "sender") and dst in sw_ids and not ingress_id:
                ingress_id = dst
            if dst in ("h2", "receiver", "reciever") and src in sw_ids and not egress_id:
                egress_id = src

    if not ingress_id:
        ingress_id = list(sw_ids.keys())[0]
    if not egress_id:
        egress_id = list(sw_ids.keys())[-1]

    if ingress_id == egress_id or len(sw_ids) == 1:
        sw_name = sw_ids[ingress_id].get("name", ingress_id.upper())
        return {
            "path_a": {
                "id": "path_a",
                "name": f"Direct ({sw_name})",
                "role": "primary",
                "hops": [ingress_id],
                "delay_ms": 1.0,
                "capacity_mbps": 100.0,
                "queue_limit": 1000,
                "s1_output_port": 1
            }
        }

    # Adjacency list
    adj: Dict[str, List[str]] = {s_id: [] for s_id in sw_ids}
    for lk in links:
        u = str(lk.get("src", "")).lower()
        v = str(lk.get("dst", "")).lower()
        if u in sw_ids and v in sw_ids and u != v:
            if v not in adj[u]:
                adj[u].append(v)
            if u not in adj[v]:
                adj[v].append(u)

    # DFS backtracking
    all_paths: List[List[str]] = []
    visited = set([ingress_id])

    def dfs(curr: str, target: str, path: List[str]):
        if curr == target:
            if len(path) >= 2:
                all_paths.append(list(path))
            return
        for nxt in adj.get(curr, []):
            if nxt not in visited:
                visited.add(nxt)
                path.append(nxt)
                dfs(nxt, target, path)
                path.pop()
                visited.remove(nxt)

    dfs(ingress_id, egress_id, [ingress_id])

    # Direct paths (shortest possible direct link between ingress and egress)
    direct_paths = [p for p in all_paths if len(p) == 2 or (len(p) > 1 and p[1] == egress_id)]
    indirect_paths = [p for p in all_paths if p not in direct_paths]

    # Group indirect paths by the outgoing switch cable leaving ingress
    from collections import defaultdict
    by_first_hop = defaultdict(list)
    for p in indirect_paths:
        first_hop = p[1]
        by_first_hop[first_hop].append(p)

    # Sort each group by length ascending so cleaner, shorter paths come first
    for fh in by_first_hop:
        by_first_hop[fh].sort(key=len)

    # Round-robin interleave across all unique first-hop cables to guarantee physical cable diversity
    ordered_paths = list(direct_paths)
    round_idx = 0
    first_hop_keys = sorted(by_first_hop.keys())
    while len(ordered_paths) < 32:
        added_any = False
        for fh in first_hop_keys:
            group = by_first_hop[fh]
            if round_idx < len(group):
                ordered_paths.append(group[round_idx])
                added_any = True
                if len(ordered_paths) >= 32:
                    break
        if not added_any:
            break
        round_idx += 1

    paths_dict: Dict[str, Any] = {}
    for idx, hops in enumerate(ordered_paths):
        p_id = f"path_{chr(ord('a') + idx)}" if idx < 26 else f"path_{idx + 1}"
        p_label = f"Path-{chr(ord('A') + idx)}" if idx < 26 else f"Path-{idx + 1}"
        role = "primary" if idx == 0 else ("alternate" if idx == 1 else "backup")
        hop_names = [sw_ids[h].get("name", h.upper()) for h in hops if h in sw_ids]
        path_name = f"{p_label} ({' -> '.join(hop_names)})"
        delay = 5.0 * max(1, len(hops) - 1)
        paths_dict[p_id] = {
            "id": p_id,
            "name": path_name,
            "role": role,
            "hops": hops,
            "delay_ms": delay,
            "capacity_mbps": 10.0,
            "queue_limit": 100,
            "s1_output_port": idx + 2
        }

    return paths_dict


class TopologyDefinition:
    """
    Structured representation of a parsed .json network topology.
    Encapsulates switches, hosts, links, path routing constraints,
    visualization coordinates, and SDN policies.
    """

    def __init__(self, data: Dict[str, Any], filepath: str = ""):
        self.raw_data = data
        self.filepath = filepath
        self.format = data.get("format", "network-topology")
        self.version = data.get("version", "1.0")
        self.name = data.get("topology_name", "Custom Topology")
        self.description = data.get("description", "")

        self.switches: List[Dict[str, Any]] = data.get("switches", [])
        self.hosts: List[Dict[str, Any]] = data.get("hosts", [])
        self.links: List[Dict[str, Any]] = data.get("links", [])
        self.paths: Dict[str, Any] = data.get("paths", {})
        self.traffic_profile: Dict[str, Any] = data.get("traffic_profile", {})
        self.sdn_policy: Dict[str, Any] = data.get("sdn_policy", {})

        # Dynamic path discovery if paths are missing, incomplete, or lack cable diversity
        needs_discovery = False
        if not self.paths or len(self.paths) < 2:
            needs_discovery = True
        else:
            # Check if ingress switch has multiple outgoing cables, but loaded paths ignore them
            ingress_id = self.get_ingress_id()
            if ingress_id:
                sw_ids = {str(s.get("id", "")).lower() for s in self.switches if s.get("id")}
                ingress_neighbors = set()
                for lk in self.links:
                    u = str(lk.get("src", "")).lower()
                    v = str(lk.get("dst", "")).lower()
                    if u == ingress_id and v in sw_ids:
                        ingress_neighbors.add(v)
                    elif v == ingress_id and u in sw_ids:
                        ingress_neighbors.add(u)

                path_first_hops = set()
                for p_info in self.paths.values():
                    hops = p_info.get("hops", [])
                    if len(hops) > 1:
                        path_first_hops.add(str(hops[1]).lower())

                # If ingress connects to 3+ switches, but loaded paths only cover <= 2 of them, rediscover
                if len(ingress_neighbors) > len(path_first_hops) and len(ingress_neighbors) >= 3:
                    needs_discovery = True

        if needs_discovery:
            discovered = discover_all_simple_paths(self.switches, self.hosts, self.links)
            if discovered and len(discovered) >= len(self.paths):
                self.paths = discovered

        # Tag links with path segments if missing
        for p_id, p_info in self.paths.items():
            hops = p_info.get("hops", [])
            for i in range(len(hops) - 1):
                u, v = hops[i].lower(), hops[i + 1].lower()
                for lk in self.links:
                    l_src = lk.get("src", "").lower()
                    l_dst = lk.get("dst", "").lower()
                    if (l_src == u and l_dst == v) or (l_src == v and l_dst == u):
                        if not lk.get("path_segment"):
                            lk["path_segment"] = p_id
                            lk["is_bottleneck"] = True

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

    def get_ingress_id(self) -> Optional[str]:
        """Finds ID of ingress switch from switch roles, connected senders, or fallback."""
        for s in self.switches:
            if str(s.get("role", "")).lower() == "ingress":
                return str(s.get("id", "")).lower()
        for lk in self.links:
            src = str(lk.get("src", "")).lower()
            dst = str(lk.get("dst", "")).lower()
            if src in ("h1", "sender"):
                return dst
        if self.switches:
            return str(self.switches[0].get("id", "")).lower()
        return None

    def get_egress_id(self) -> Optional[str]:
        """Finds ID of egress switch from switch roles, connected receivers, or fallback."""
        for s in self.switches:
            if str(s.get("role", "")).lower() == "egress":
                return str(s.get("id", "")).lower()
        for lk in self.links:
            src = str(lk.get("src", "")).lower()
            dst = str(lk.get("dst", "")).lower()
            if dst in ("h2", "receiver", "reciever"):
                return src
        if self.switches:
            return str(self.switches[-1].get("id", "")).lower()
        return None

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves node configuration dictionary by ID (e.g. 's1', 'h1')."""
        return self._node_map.get(node_id.lower())

    def get_node_pos(self, node_id: str, default: Tuple[float, float] = (0.5, 0.5)) -> Tuple[float, float]:
        """Returns normalized (x, y) coordinates in [0.0, 1.0] for canvas rendering."""
        node = self.get_node(node_id)
        if node and "x" in node and "y" in node:
            return float(node["x"]), float(node["y"])
        return default

    def get_path(self, path_key: str, default: Any = None) -> Any:
        """Retrieves path specification by key ('path_a', 'path_b', etc.) with alias and case-insensitive fallback."""
        if not self.paths:
            return default
        val = self.paths.get(path_key)
        if val is not None:
            return val
        key_lower = str(path_key).lower()
        for k, v in self.paths.items():
            if k.lower() == key_lower:
                return v
        if key_lower in ("path_a", "primary", "path-a"):
            for k in ("path_a", "PATH_A", "primary"):
                if k in self.paths:
                    return self.paths[k]
        elif key_lower in ("path_b", "alternate", "path-b"):
            for k in ("path_b", "PATH_B", "alternate"):
                if k in self.paths:
                    return self.paths[k]
        return default

    def to_dict(self) -> Dict[str, Any]:
        """Exports definition back to serializable dictionary."""
        return self.raw_data

    def build_mininet_topo(self):
        """
        Dynamically constructs a Mininet Topo subclass using the .json definition.
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


def validate_topology_extension(filepath: str):
    """
    Enforces that the specified path ends with the required .json extension.
    """
    if not filepath or not filepath.lower().endswith(TOPOLOGY_FILE_EXTENSION):
        _, ext = os.path.splitext(filepath)
        raise InvalidTopologyExtensionError(
            f"Invalid file extension '{ext or '<none>'}'. Only {TOPOLOGY_FILE_EXTENSION} topology files are supported."
        )


# Backward compatibility alias
validate_tp_extension = validate_topology_extension


def load_topology(filepath: str) -> TopologyDefinition:
    """
    Loads and validates a .json topology definition file.

    Parameters:
      filepath (str): Absolute or relative path to a .json file.

    Returns:
      TopologyDefinition: Parsed and validated topology object.

    Raises:
      InvalidTopologyExtensionError: If filename does not end in .json.
      FileNotFoundError: If file cannot be found.
      CorruptTopologyFileError: If JSON parsing fails or required fields are missing.
    """
    validate_topology_extension(filepath)

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Topology file not found: {filepath}")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise CorruptTopologyFileError(f"Failed to parse .json file as JSON: {e}")

    # Validate essential schema
    if not isinstance(data, dict):
        raise CorruptTopologyFileError("Topology (.json) file must be a JSON object.")

    if "switches" not in data or not isinstance(data["switches"], list):
        raise CorruptTopologyFileError("Invalid .json schema: missing 'switches' list.")

    if "hosts" not in data or not isinstance(data["hosts"], list):
        raise CorruptTopologyFileError("Invalid .json schema: missing 'hosts' list.")

    if "links" not in data or not isinstance(data["links"], list):
        raise CorruptTopologyFileError("Invalid .json schema: missing 'links' list.")

    topo = TopologyDefinition(data, filepath=os.path.abspath(filepath))
    logger.info(
        f"Loaded topology '{topo.name}' from {filepath} "
        f"({len(topo.switches)} switches, {len(topo.hosts)} hosts, {len(topo.links)} links)"
    )
    return topo


def save_topology(topo_def: TopologyDefinition, filepath: str):
    """Saves a TopologyDefinition object to a .json file."""
    validate_topology_extension(filepath)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(topo_def.to_dict(), f, indent=2)
    logger.info(f"Saved topology '{topo_def.name}' to {filepath}")


def get_default_topology_path() -> str:
    """Finds the default diamond.json file path in workspace or source directories."""
    candidates = [
        "diamond.json",
        os.path.join(os.path.dirname(__file__), "..", "diamond.json"),
        os.path.join(os.path.dirname(__file__), "diamond.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return "diamond.json"


def get_default_topology() -> TopologyDefinition:
    """Loads default diamond topology from diamond.json."""
    path = get_default_topology_path()
    if os.path.exists(path):
        return load_topology(path)
    raise FileNotFoundError(f"Default diamond.json not found at {path}")


def run_mininet_cli(tp_path: str = ""):
    """Runs Mininet environment using loaded .json topology file on Linux."""
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
    parser = argparse.ArgumentParser(description="Topology (.json) Loader & Mininet CLI")
    parser.add_argument("file", nargs="?", default="", help="Path to .json topology file")
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
