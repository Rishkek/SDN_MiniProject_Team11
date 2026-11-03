"""
2D Layout coordinate generator for compiled topologies.
Provides normalized (x, y) coordinates for PyQt6 canvas visualization.
"""

from typing import Dict, List, Tuple
import math
import networkx as nx


def compute_topology_layout(
    switches: List[str],
    hosts: List[str],
    edges: List[Tuple[str, str]],
    topology_type: str = "auto"
) -> Dict[str, Tuple[float, float]]:
    """
    Computes normalized (x, y) coordinates in [0.08, 0.92] for canvas rendering.
    Supports distinct layouts for Diamond, Star, Bus, Ring, Mesh, and general graphs.
    """
    node_positions: Dict[str, Tuple[float, float]] = {}
    sw_set = set(switches)
    topo_type = topology_type.lower()

    # Helper: find which switch a host connects to
    def get_host_switch(h_id: str) -> str:
        for u, v in edges:
            if u == h_id and v in sw_set:
                return v
            elif v == h_id and u in sw_set:
                return u
        return switches[0] if switches else "s1"

    # 1. Star Topology: single central switch with peripheral nodes
    if topo_type == "star" or (len(switches) == 1 and hosts):
        center_sw = switches[0]
        node_positions[center_sw] = (0.50, 0.50)
        n = len(hosts)
        radius = 0.33
        for i, h in enumerate(sorted(hosts)):
            angle = (2.0 * math.pi * i) / n - (math.pi / 2.0)
            x = 0.50 + radius * math.cos(angle)
            y = 0.50 + radius * math.sin(angle)
            node_positions[h] = (round(x, 2), round(y, 2))
        return node_positions

    # 2. Bus / Linear Backbone Topology
    if topo_type == "bus":
        ordered_switches = sorted(switches)
        n_sw = len(ordered_switches)
        step_x = 0.62 / max(1, (n_sw - 1)) if n_sw > 1 else 0.5
        for i, s in enumerate(ordered_switches):
            sx = 0.19 + i * step_x
            node_positions[s] = (round(sx, 2), 0.50)

        # Map hosts to their connected switches, alternating above/below the bus
        for i, h in enumerate(sorted(hosts)):
            target_sw = get_host_switch(h)
            sx, _ = node_positions[target_sw]
            # Alternate top (0.22) and bottom (0.78) across the bus
            sy = 0.22 if (i % 2 == 0) else 0.78
            node_positions[h] = (round(sx, 2), sy)
        return node_positions

    # 3. Ring Topology: circular loop of switches following link order
    if topo_type == "ring":
        G_ring = nx.Graph()
        for u, v in edges:
            if u in sw_set and v in sw_set:
                G_ring.add_edge(u, v)

        ordered_switches = []
        try:
            cycle_edges = nx.find_cycle(G_ring)
            ordered_switches = [e[0] for e in cycle_edges]
        except Exception:
            ordered_switches = sorted(switches)

        n_sw = len(ordered_switches)
        radius_x = 0.22
        radius_y = 0.18
        for i, s in enumerate(ordered_switches):
            # Angles starting at top-left: -3pi/4, -pi/4, pi/4, 3pi/4
            angle = (2.0 * math.pi * i) / n_sw - (3.0 * math.pi / 4.0)
            sx = 0.50 + radius_x * math.cos(angle) * 1.3
            sy = 0.50 + radius_y * math.sin(angle) * 1.3
            node_positions[s] = (round(sx, 2), round(sy, 2))

        # Position hosts radiating outwards from their parent switch
        for h in sorted(hosts):
            parent_sw = get_host_switch(h)
            psx, psy = node_positions[parent_sw]
            vx = psx - 0.50
            vy = psy - 0.50
            mag = math.hypot(vx, vy) or 1.0
            hx = 0.50 + (vx / mag) * 0.44
            hy = 0.50 + (vy / mag) * 0.38
            node_positions[h] = (round(max(0.08, min(0.92, hx)), 2), round(max(0.12, min(0.88, hy)), 2))
        return node_positions

    # 4. Mesh Topology: 4-corner box with cross diagonals
    if topo_type == "mesh":
        node_positions["s1"] = (0.35, 0.32)
        node_positions["s2"] = (0.65, 0.32)
        node_positions["s3"] = (0.35, 0.68)
        node_positions["s4"] = (0.65, 0.68)
        node_positions["h1"] = (0.10, 0.28)
        node_positions["h3"] = (0.10, 0.72)
        node_positions["h2"] = (0.90, 0.28)
        node_positions["h4"] = (0.90, 0.72)
        return node_positions

    # 5. Canonical Diamond Topology
    if topo_type == "diamond" or (sw_set == {"s1", "s2", "s3", "s4"} and set(hosts) == {"h1", "h2", "h3", "h4"}):
        return {
            "h1": (0.08, 0.28),
            "h3": (0.08, 0.72),
            "s1": (0.26, 0.50),
            "s2": (0.50, 0.22),
            "s3": (0.50, 0.78),
            "s4": (0.74, 0.50),
            "h2": (0.92, 0.28),
            "h4": (0.92, 0.72),
        }

    # 6. General Fallback: NetworkX Force-Directed Spring Layout
    G = nx.Graph()
    for s in switches:
        G.add_node(s, node_type="switch")
    for h in hosts:
        G.add_node(h, node_type="host")
    for u, v in edges:
        G.add_edge(u, v)

    raw_pos = nx.spring_layout(G, seed=42, iterations=80)
    xs = [coord[0] for coord in raw_pos.values()]
    ys = [coord[1] for coord in raw_pos.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = (max_x - min_x) if max_x > min_x else 1.0
    span_y = (max_y - min_y) if max_y > min_y else 1.0

    for node, (x, y) in raw_pos.items():
        norm_x = 0.10 + 0.80 * ((x - min_x) / span_x)
        norm_y = 0.15 + 0.70 * ((y - min_y) / span_y)
        node_positions[node] = (round(norm_x, 2), round(norm_y, 2))

    return node_positions
