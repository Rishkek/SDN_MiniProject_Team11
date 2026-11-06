"""
Main Compiler for Prototype.pol.
Coordinates:
  1. Preprocessing (resolving lib.machine, lib.wire, lib.data, custom includes)
  2. Lexical & Syntax Parsing into AST
  3. Semantic Analysis (symbol table, type checks, unit scaling, constraint verification)
  4. 2D Coordinate Layout Engine
  5. Graph Synthesis (paths, SDN policy, traffic profile)
  6. Code Generation (standard .json output compatible with TopologyDefinition & Mininet)
"""

import os
import json
from typing import Dict, Any, Optional, List, Tuple
import networkx as nx

from pol_compiler.preprocessor import Preprocessor
from pol_compiler.semantic import SemanticAnalyzer, TopologyIR, SemanticError
from pol_compiler.layout import compute_topology_layout


class PolCompiler:
    """End-to-end compiler from .pol source files to .json topology definitions."""

    def __init__(self, search_paths: Optional[List[str]] = None):
        self.search_paths = search_paths or ["lib", ".", "pol_src"]

    def compile_source(
        self,
        source_code: str,
        filepath: str = "inline.pol",
        topology_type: str = "auto"
    ) -> Dict[str, Any]:
        """Compiles raw Prototype.pol source text to a dictionary topology."""
        # For inline source, save to a temporary location or parse directly
        from pol_compiler.lexer import Lexer
        from pol_compiler.parser import Parser

        lexer = Lexer(source_code, filepath=filepath)
        tokens = lexer.tokenize()
        parser = Parser(tokens, filepath=filepath)
        ast = parser.parse()

        analyzer = SemanticAnalyzer()
        ir = analyzer.analyze(ast)
        return self._synthesize_json(ir, filepath, topology_type)

    def compile_file(
        self,
        filepath: str,
        output_path: Optional[str] = None,
        topology_type: str = "auto"
    ) -> Dict[str, Any]:
        """
        Compiles a .pol file on disk into a topology dictionary,
        and optionally writes it to output_path.
        """
        preprocessor = Preprocessor(search_paths=self.search_paths)
        merged_ast = preprocessor.load_and_preprocess(filepath)

        analyzer = SemanticAnalyzer()
        ir = analyzer.analyze(merged_ast)

        # Infer topology name and type from file name if auto
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        if ir.name == "Prototype.pol Topology":
            ir.name = f"{base_name.capitalize()} Topology"

        if topology_type == "auto":
            inferred = (base_name + " " + ir.name).lower()
            if any(t in inferred for t in ("diamond", "star", "ring", "bus", "mesh")):
                for t in ("diamond", "star", "ring", "bus", "mesh"):
                    if t in inferred:
                        topology_type = t
                        break

        data = self._synthesize_json(ir, filepath, topology_type)

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        return data

    def _synthesize_json(
        self,
        ir: TopologyIR,
        source_file: str,
        topology_type: str
    ) -> Dict[str, Any]:
        # 1. Update host connected_to based on host-switch links
        for link in ir.links:
            s = link["src"]
            d = link["dst"]
            if s.startswith("h") and d.startswith("s"):
                if s in ir.hosts:
                    ir.hosts[s]["connected_to"] = d
            elif d.startswith("h") and s.startswith("s"):
                if d in ir.hosts:
                    ir.hosts[d]["connected_to"] = s

        # 2. Compute 2D visualization layout
        switch_ids = sorted(list(ir.switches.keys()))
        host_ids = sorted(list(ir.hosts.keys()))
        edges = [(l["src"], l["dst"]) for l in ir.links]

        coords = compute_topology_layout(switch_ids, host_ids, edges, topology_type=topology_type)

        for s_id, s_obj in ir.switches.items():
            pos = coords.get(s_id, (0.5, 0.5))
            s_obj["x"] = pos[0]
            s_obj["y"] = pos[1]

        for h_id, h_obj in ir.hosts.items():
            pos = coords.get(h_id, (0.1, 0.3))
            h_obj["x"] = pos[0]
            h_obj["y"] = pos[1]

        # 3. Path synthesis and link classification
        G_switches = nx.Graph()
        for s_id in switch_ids:
            G_switches.add_node(s_id)
        for link in ir.links:
            s, d = link["src"], link["dst"]
            if s.startswith("s") and d.startswith("s"):
                G_switches.add_edge(s, d, link=link)

        # Identify Ingress and Egress switches
        ingress_id = None
        egress_id = None
        for s_id, s_data in ir.switches.items():
            if s_data.get("role") == "ingress":
                ingress_id = s_id
            elif s_data.get("role") == "egress":
                egress_id = s_id

        if not ingress_id and switch_ids:
            ingress_id = switch_ids[0]
        if not egress_id and switch_ids:
            egress_id = switch_ids[-1]

        paths: Dict[str, Any] = {}
        if ingress_id and egress_id and ingress_id != egress_id and nx.has_path(G_switches, ingress_id, egress_id):
            simple_paths = list(nx.all_simple_paths(G_switches, ingress_id, egress_id))
            if simple_paths:
                # Primary path
                path_a_hops = simple_paths[0]
                paths["path_a"] = {
                    "id": "path_a",
                    "name": f"Path-A ({' -> '.join(h.upper() for h in path_a_hops)})",
                    "role": "primary",
                    "hops": path_a_hops,
                    "delay_ms": 5.0,
                    "capacity_mbps": 10.0,
                    "queue_limit": 100,
                    "s1_output_port": 2
                }

                # Mark switches in path_a as primary if not ingress/egress
                for hop in path_a_hops[1:-1]:
                    if hop in ir.switches and ir.switches[hop]["role"] == "core":
                        ir.switches[hop]["role"] = "primary"
                        ir.switches[hop]["subtext"] = "Primary"

                # Mark links along path_a
                path_a_pairs = list(zip(path_a_hops[:-1], path_a_hops[1:]))
                for link in ir.links:
                    s, d = link["src"], link["dst"]
                    if (s, d) in path_a_pairs or (d, s) in path_a_pairs:
                        link["path_segment"] = "path_a"
                        link["is_bottleneck"] = True
                        if s == ingress_id:
                            link["label"] = "Path A"
                        else:
                            link["label"] = "Path A (egress)"

            if len(simple_paths) > 1:
                # Alternate path
                path_b_hops = simple_paths[1]
                paths["path_b"] = {
                    "id": "path_b",
                    "name": f"Path-B ({' -> '.join(h.upper() for h in path_b_hops)})",
                    "role": "alternate",
                    "hops": path_b_hops,
                    "delay_ms": 15.0,
                    "capacity_mbps": 10.0,
                    "queue_limit": 100,
                    "s1_output_port": 3
                }

                # Mark switches in path_b as backup
                for hop in path_b_hops[1:-1]:
                    if hop in ir.switches and ir.switches[hop]["role"] == "core":
                        ir.switches[hop]["role"] = "backup"
                        ir.switches[hop]["subtext"] = "Backup"

                # Mark links along path_b
                path_b_pairs = list(zip(path_b_hops[:-1], path_b_hops[1:]))
                for link in ir.links:
                    s, d = link["src"], link["dst"]
                    if (s, d) in path_b_pairs or (d, s) in path_b_pairs:
                        link["path_segment"] = "path_b"
                        link["is_bottleneck"] = True
                        if s == ingress_id:
                            link["label"] = "Path B"
                        else:
                            link["label"] = "Path B (egress)"
        elif switch_ids:
            # Single-switch or star topology path
            paths["path_a"] = {
                "id": "path_a",
                "name": f"Direct ({switch_ids[0].upper()})",
                "role": "primary",
                "hops": [switch_ids[0]],
                "delay_ms": 1.0,
                "capacity_mbps": 100.0,
                "queue_limit": 1000,
                "s1_output_port": 1
            }

        # Style host edge links
        for link in ir.links:
            s, d = link["src"], link["dst"]
            if link["type"] == "host_edge":
                if "h1" in (s, d) or "h2" in (s, d):
                    link["pen_color"] = "#89b4fa"
                elif "h3" in (s, d) or "h4" in (s, d):
                    link["pen_color"] = "#f38ba8"
                else:
                    link["pen_color"] = "#a6adc8"

        # 4. Synthesize Traffic Profile
        traffic_profile: Dict[str, Any] = {}
        if "h1" in ir.hosts and "h2" in ir.hosts:
            traffic_profile["main_stream"] = {
                "src_host": "h1",
                "dst_host": "h2",
                "dst_port": 9999,
                "nominal_rate_mbps": 6.0,
                "packet_size_bytes": 1024
            }
        elif len(host_ids) >= 2:
            traffic_profile["main_stream"] = {
                "src_host": host_ids[0],
                "dst_host": host_ids[1],
                "dst_port": 9999,
                "nominal_rate_mbps": 6.0,
                "packet_size_bytes": 1024
            }

        if "h3" in ir.hosts and "h4" in ir.hosts:
            traffic_profile["cross_traffic"] = {
                "src_host": "h3",
                "dst_host": "h4",
                "dst_port": 9998,
                "burst_rate_mbps": 7.0,
                "burst_duration_sec": 9.0,
                "target_path": "path_a"
            }
        elif len(host_ids) >= 4:
            traffic_profile["cross_traffic"] = {
                "src_host": host_ids[2],
                "dst_host": host_ids[3],
                "dst_port": 9998,
                "burst_rate_mbps": 7.0,
                "burst_duration_sec": 9.0,
                "target_path": "path_a"
            }

        # 5. SDN Policy
        sdn_policy = {
            "congestion_threshold_mbps": 8.0,
            "congestion_loss_threshold_pct": 3.0,
            "hysteresis_recovery_mbps": 4.5,
            "poll_interval_sec": 0.5,
            "consecutive_triggers_required": 2,
            "consecutive_recoveries_required": 4
        }

        # Construct final JSON topology schema
        result = {
            "format": "network-topology",
            "version": "1.0",
            "topology_name": ir.name,
            "description": f"Generated from {os.path.basename(source_file)} via TopoNet Compiler",
            "switches": [ir.switches[s_id] for s_id in switch_ids],
            "hosts": [ir.hosts[h_id] for h_id in host_ids],
            "links": ir.links,
            "paths": paths,
            "traffic_profile": traffic_profile,
            "sdn_policy": sdn_policy
        }

        return result


def compile_pol_file(
    source_path: str,
    output_path: Optional[str] = None,
    topology_type: str = "auto"
) -> Dict[str, Any]:
    """Convenience helper to compile a .pol source file to .json."""
    compiler = PolCompiler()
    return compiler.compile_file(source_path, output_path=output_path, topology_type=topology_type)
