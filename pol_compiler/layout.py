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
    Supports Diamond, Star, Bus, Ring, Mesh, and general graphs.
    """
    node_positions: Dict[str, Tuple[float, float]] = {}

    # 1. Canonical Diamond Topology Check (s1..s4, h1..h4)
    sw_set = set(switches)
    host_set = set(hosts)
    if sw_set == {"s1", "s2", "s3", "s4"} and host_set == {"h1", "h2", "h3", "h4"}:
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

    # 2. Star Topology: single central switch with peripheral nodes
    if len(switches) == 1 and hosts:
        center_sw = switches[0]
        node_positions[center_sw] = (0.50, 0.50)
        n = len(hosts)
        for i, h in enumerate(hosts):
            angle = (2.0 * math.pi * i) / n - (math.pi / 2.0)
            radius = 0.36
            x = 0.50 + radius * math.cos(angle)
            y = 0.50 + radius * math.sin(angle)
            node_positions[h] = (round(x, 2), round(y, 2))
        return node_positions

    # 3. Ring Topology: circular layout for switches, hosts positioned outward
    if topology_type == "ring" or (len(switches) >= 3 and len(edges) >= len(switches)):
        n_sw = len(switches)
        radius_sw = 0.28
        sw_angles: Dict[str, float] = {}
        for i, s in enumerate(switches):
            angle = (2.0 * math.pi * i) / n_sw - (math.pi / 2.0)
            sw_angles[s] = angle
            x = 0.50 + radius_sw * math.cos(angle)
            y = 0.50 + radius_sw * math.sin(angle)
            node_positions[s] = (round(x, 2), round(y, 2))

        # Position hosts radiating outside their connected switch
        host_count_per_sw: Dict[str, int] = {}
        for h in hosts:
            # find connected switch
            target_sw = switches[0]
            for u, v in edges:
                if u == h and v in sw_set:
                    target_sw = v
                    break
                elif v == h and u in sw_set:
                    target_sw = u
                    break
            idx = host_count_per_sw.get(target_sw, 0)
            host_count_per_sw[target_sw] = idx + 1
            sw_ang = sw_angles.get(target_sw, 0.0)
            h_ang = sw_ang + (idx * 0.25 - 0.12)
            h_radius = 0.42
            hx = 0.50 + h_radius * math.cos(h_ang)
            hy = 0.50 + h_radius * math.sin(h_ang)
            node_positions[h] = (round(max(0.08, min(0.92, hx)), 2), round(max(0.12, min(0.88, hy)), 2))
        return node_positions

    # 4. Bus / Linear Backbone Topology
    if topology_type == "bus" or (len(switches) >= 2 and all(s.startswith("s") for s in switches)):
        # Order switches linearly
        ordered_switches = sorted(switches)
        n_sw = len(ordered_switches)
        step_x = 0.70 / max(1, (n_sw - 1)) if n_sw > 1 else 0.5
        for i, s in enumerate(ordered_switches):
            sx = 0.15 + i * step_x
            node_positions[s] = (round(sx, 2), 0.50)

        # Hosts alternated above and below backbone
        for i, h in enumerate(sorted(hosts)):
            # find closest switch
            assigned_sw = ordered_switches[i % n_sw]
            sx, _ = node_positions[assigned_sw]
            sy = 0.22 if (i % 2 == 0) else 0.78
            node_positions[h] = (round(sx, 2), sy)
        return node_positions

    # 5. General Fallback: NetworkX Force-Directed Spring Layout
    G = nx.Graph()
    for s in switches:
        G.add_node(s, node_type="switch")
    for h in hosts:
        G.add_node(h, node_type="host")
    for u, v in edges:
        G.add_edge(u, v)

    raw_pos = nx.spring_layout(G, seed=42, iterations=80)
    # Normalize coordinates into [0.10, 0.90] x [0.15, 0.85]
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
