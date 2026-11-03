"""
Semantic Analyzer for Prototype.pol AST.
Performs symbol resolution, type checking, unit calculation, macro expansion,
constraint validation (--unique, max counts), and synthesizes network intermediate representation.
"""

from typing import Dict, List, Any, Optional, Tuple, Set
import re
from pol_compiler.ast_nodes import (
    ProgramNode, DefineNode, DetailNode, MacroDefNode, MacroCallNode,
    SpawnNode, SpawnsBlockNode, ConnectionsBlockNode, UnitDefNode,
    DataDeclNode, DataOpNode, FieldAssignNode, InstanceNode, DeployNode
)


class SemanticError(Exception):
    """Raised when semantic validation fails (type error, unique violation, etc.)."""
    pass


class Symbol:
    """Represents a defined entity, type, or alias in Prototype.pol."""
    def __init__(
        self,
        name: str,
        kind: str,  # 'type', 'alias', 'unit', 'macro'
        base_type: str = "",
        is_unique: bool = False,
        is_common: bool = False,
        max_count: Optional[int] = None
    ):
        self.name = name
        self.kind = kind
        self.base_type = base_type
        self.is_unique = is_unique
        self.is_common = is_common
        self.max_count = max_count  # None if 'var' or unlimited
        self.used_count = 0
        self.properties: Dict[str, Any] = {}
        self.sub_instances: Dict[str, Symbol] = {}

    def __repr__(self):
        return f"<Symbol {self.name} kind={self.kind} base={self.base_type}>"


class TopologyIR:
    """Intermediate Representation of the compiled topology before JSON emission."""
    def __init__(self, name: str = "Prototype.pol Topology"):
        self.name = name
        self.description = "Synthesized from Prototype.pol source"
        self.switches: Dict[str, Dict[str, Any]] = {}
        self.hosts: Dict[str, Dict[str, Any]] = {}
        self.links: List[Dict[str, Any]] = []
        self.grid_enabled = False


class SemanticAnalyzer:
    """
    Validates AST and builds the intermediate network topology representation.
    """

    def __init__(self):
        self.symbols: Dict[str, Symbol] = {}
        self.units: Dict[str, float] = {
            "bit": 1.0,
            "byte": 8.0,
            "kilo": 1024.0,
            "mega": 1048576.0,
            "giga": 1073741824.0,
            "milli": 1.0,
            "sec": 1000.0,
        }
        self.macros: Dict[str, MacroDefNode] = {}
        self.spawns: Dict[str, Symbol] = {}
        self.ir = TopologyIR()
        self._init_builtins()

    def _init_builtins(self):
        """Pre-populate core machine and wire library definitions."""
        self.symbols["machine.host"] = Symbol("machine.host", "type", is_common=True)
        self.symbols["machine.host.sender"] = Symbol("machine.host.sender", "type", base_type="machine.host", is_common=True)
        self.symbols["machine.host.reciever"] = Symbol("machine.host.reciever", "type", base_type="machine.host", is_common=True)
        self.symbols["machine.host.receiver"] = Symbol("machine.host.receiver", "type", base_type="machine.host", is_common=True)
        self.symbols["machine.switch"] = Symbol("machine.switch", "type", is_common=True)
        self.symbols["wire"] = Symbol("wire", "type", is_common=True)

    def eval_expr(self, expr: Any, local_vars: Optional[Dict[str, Any]] = None) -> Any:
        """Evaluates arithmetic expressions and resolves unit scaling (@kilo, @mega)."""
        if local_vars is None:
            local_vars = {}

        if isinstance(expr, (int, float)):
            return expr

        if isinstance(expr, str):
            # Check string literal
            if expr.startswith('"') and expr.endswith('"'):
                return expr.strip('"')

            # Check unit multiplier e.g. "100@kilo" or "10@mega"
            if "@" in expr:
                parts = expr.split("@")
                if len(parts) == 2:
                    try:
                        base = float(parts[0]) if parts[0] else 1.0
                        unit_str = parts[1].strip()
                        multiplier = self.units.get(unit_str, 1.0)
                        return base * multiplier
                    except ValueError:
                        pass

            # Check variable lookup
            if expr in local_vars:
                return local_vars[expr]

            # Check unit table
            clean_expr = expr.lstrip("@")
            if clean_expr in self.units:
                return self.units[clean_expr]

            return expr

        if isinstance(expr, tuple) and len(expr) == 4 and expr[0] == "BIN_OP":
            _, op, left, right = expr
            val_left = self.eval_expr(left, local_vars)
            val_right = self.eval_expr(right, local_vars)
            try:
                if op == "PLUS":
                    return val_left + val_right
                elif op == "MINUS":
                    return val_left - val_right
                elif op == "STAR":
                    return val_left * val_right
                elif op == "SLASH":
                    return val_left / val_right
            except Exception as e:
                raise SemanticError(f"Failed evaluating arithmetic expression ({val_left} {op} {val_right}): {e}")

        return expr

    def analyze(self, ast: ProgramNode) -> TopologyIR:
        """Runs two-pass semantic analysis over the program AST."""
        # Pass 1: Types, Units, Details, Macros
        for stmt in ast.statements:
            self._analyze_statement_pass1(stmt)

        # Pass 2: Spawns, Connections, and Layout Deployment
        for stmt in ast.statements:
            self._analyze_statement_pass2(stmt)

        return self.ir

    def _analyze_statement_pass1(self, stmt: Any):
        if isinstance(stmt, UnitDefNode):
            val = self.eval_expr(stmt.value_expr)
            self.units[stmt.unit_name] = float(val)

        elif isinstance(stmt, DefineNode):
            self._handle_define(stmt)

        elif isinstance(stmt, MacroDefNode):
            self.macros[stmt.name] = stmt

        elif isinstance(stmt, DetailNode):
            self._handle_detail(stmt)

    def _handle_define(self, node: DefineNode):
        sym_name = node.symbol.lstrip("&")
        target = node.target_type

        # Check unique constraint if re-defined
        if sym_name in self.symbols and self.symbols[sym_name].is_unique and node.is_unique:
            raise SemanticError(f"Duplicate definition of unique symbol '{sym_name}' at {node.line}:{node.col}")

        sym = Symbol(
            name=sym_name,
            kind="type",
            base_type=target,
            is_unique=node.is_unique,
            is_common=node.is_common
        )
        self.symbols[sym_name] = sym
        self.symbols[node.symbol] = sym

    def _handle_detail(self, node: DetailNode):
        target_name = node.target.lstrip("&")
        # Check if target is a known symbol or instance (e.g. 'cable.high_speed')
        sym = None
        if target_name in self.symbols:
            sym = self.symbols[target_name]
        elif node.target in self.symbols:
            sym = self.symbols[node.target]
        elif "." in target_name:
            parent_name, sub_name = target_name.rsplit(".", 1)
            if parent_name in self.symbols and sub_name in self.symbols[parent_name].sub_instances:
                sym = self.symbols[parent_name].sub_instances[sub_name]
        
        # If detail declares instances (e.g. detail cable: instance high_speed)
        if sym and node.instances:
            for inst_name in node.instances:
                inst_sym = Symbol(
                    name=f"{target_name}.{inst_name}",
                    kind="instance",
                    base_type=target_name,
                    is_common=True
                )
                sym.sub_instances[inst_name] = inst_sym
                # Also expose directly as 'cable.high_speed'
                self.symbols[f"{target_name}.{inst_name}"] = inst_sym

        local_vars: Dict[str, Any] = {}

        for item in node.body:
            if isinstance(item, DataDeclNode):
                local_vars[item.var_name] = 0
            elif isinstance(item, DataOpNode):
                val = self.eval_expr(item.value_expr, local_vars)
                local_vars[item.var_name] = val
                if sym:
                    if item.op in ("out", "in", "flow"):
                        sym.properties["rate"] = val
            elif isinstance(item, FieldAssignNode):
                val = self.eval_expr(item.value_expr, local_vars)
                if sym:
                    if item.field_name == "ports":
                        port_key = f"ports_{item.arg}" if item.arg else "ports"
                        sym.properties[port_key] = val
                    elif item.field_name in ("rate", "field.rate"):
                        rate_key = f"rate_{item.arg}" if item.arg else "rate"
                        sym.properties[rate_key] = val
                        sym.properties["rate"] = val
                    else:
                        clean_field = item.field_name.replace("field.", "")
                        sym.properties[clean_field] = val
            elif isinstance(item, MacroCallNode):
                self._execute_macro(item, sym)

    def _execute_macro(self, call: MacroCallNode, target_sym: Optional[Symbol]):
        if call.name not in self.macros:
            return  # Undefined macro or external

        macro_def = self.macros[call.name]
        # Bind arguments to macro params
        env: Dict[str, Any] = {}
        for param, arg in zip(macro_def.params, call.args):
            env[param.param_name] = self.eval_expr(arg)

        # Run macro statements
        for stmt in macro_def.body:
            if isinstance(stmt, FieldAssignNode):
                val = self.eval_expr(stmt.value_expr, env)
                if target_sym:
                    if stmt.field_name == "ports":
                        port_key = f"ports_{stmt.arg}" if stmt.arg else "ports"
                        target_sym.properties[port_key] = val
                    else:
                        clean_field = stmt.field_name.replace("field.", "")
                        target_sym.properties[clean_field] = val

    def _analyze_statement_pass2(self, stmt: Any):
        """Pass 2 processes machine.topology.layout details, spawns, and connections."""
        if isinstance(stmt, DetailNode) and "topology" in stmt.target:
            self._analyze_topology_block(stmt)
        elif isinstance(stmt, SpawnsBlockNode):
            self._handle_spawns(stmt)
        elif isinstance(stmt, ConnectionsBlockNode):
            self._handle_connections(stmt)

    def _analyze_topology_block(self, node: DetailNode):
        for item in node.body:
            if isinstance(item, SpawnsBlockNode):
                self._handle_spawns(item)
            elif isinstance(item, ConnectionsBlockNode):
                self._handle_connections(item)

    def _handle_spawns(self, block: SpawnsBlockNode):
        for spawn in block.spawns:
            type_name = spawn.type_name
            alias = spawn.alias

            # Find matching symbol
            sym = self._resolve_type(type_name)
            if not sym:
                # Default fallback symbol
                sym = Symbol(type_name, "type", is_common=True)

            max_c = None
            if spawn.count != "var":
                try:
                    max_c = int(spawn.count)
                except (ValueError, TypeError):
                    max_c = None

            # Enforce --unique constraint
            if sym.is_unique:
                if max_c is not None and max_c > 1:
                    raise SemanticError(
                        f"Type '{type_name}' is declared as --unique but spawned with count {max_c} at {spawn.line}:{spawn.col}"
                    )
                # Check if already spawned
                for existing_alias, existing_sym in self.spawns.items():
                    if existing_sym.base_type == sym.name or existing_sym.name == sym.name:
                        raise SemanticError(
                            f"Unique entity '{type_name}' already spawned under alias '{existing_alias}'. Cannot spawn again at {spawn.line}:{spawn.col}"
                        )

            spawn_sym = Symbol(
                name=alias,
                kind="alias",
                base_type=sym.name,
                is_unique=sym.is_unique,
                is_common=sym.is_common,
                max_count=max_c
            )
            spawn_sym.properties = dict(sym.properties)
            self.spawns[alias] = spawn_sym

    def _resolve_type(self, type_name: str) -> Optional[Symbol]:
        clean = type_name.lstrip("&")
        if clean in self.symbols:
            return self.symbols[clean]
        if type_name in self.symbols:
            return self.symbols[type_name]
        # Check alias in symbols
        for sym in self.symbols.values():
            if sym.name.lstrip("&") == clean or sym.base_type == type_name:
                return sym
        return None

    def _handle_connections(self, block: ConnectionsBlockNode):
        """Processes connection tuples (src, cable, dst) and instantiates nodes/links."""
        host_counter = 1
        switch_counter = 1

        # Track instantiated node IDs
        alias_to_node_id: Dict[str, str] = {}

        for conn in block.connections:
            src_alias = conn.src
            cable_alias = conn.cable
            dst_alias = conn.dst

            # 1. Validate cable
            cable_sym = self.spawns.get(cable_alias) or self.symbols.get(cable_alias)
            if not cable_sym:
                # Fallback to cable alias name
                cable_sym = Symbol(cable_alias, "instance")
            else:
                if cable_sym.max_count is not None and cable_sym.used_count >= cable_sym.max_count:
                    raise SemanticError(
                        f"Cable alias '{cable_alias}' exceeded its maximum instance limit of {cable_sym.max_count} at {conn.line}:{conn.col}"
                    )
                cable_sym.used_count += 1

            # 2. Resolve or instantiate src and dst nodes
            src_id = self._resolve_or_create_node(src_alias, alias_to_node_id, is_src=True)
            dst_id = self._resolve_or_create_node(dst_alias, alias_to_node_id, is_src=False)

            # 3. Create Link IR
            link_id = f"link_{src_id}_{dst_id}"
            
            # Rate translation: 10@mega -> 10.0, 1000@kilo -> 1.0 (or 100.0 for host edges)
            raw_rate = cable_sym.properties.get("rate")
            is_host_edge = src_id.startswith("h") or dst_id.startswith("h")
            
            bw_mbps = self._compute_bw_mbps(raw_rate, is_host_edge)
            delay_ms = self._compute_delay(cable_sym.properties.get("delay"), is_host_edge, src_id, dst_id)
            queue_limit = int(cable_sym.properties.get("queue", 1000 if is_host_edge else 100))

            link_entry = {
                "id": link_id,
                "src": src_id,
                "dst": dst_id,
                "label": f"{src_id.upper()}->{dst_id.upper()}",
                "bw_mbps": bw_mbps,
                "delay_ms": delay_ms,
                "max_queue": queue_limit,
                "type": "host_edge" if is_host_edge else "switch_edge",
                "cable_alias": cable_alias
            }
            self.ir.links.append(link_entry)

    def _resolve_or_create_node(self, alias: str, alias_map: Dict[str, str], is_src: bool) -> str:
        # If already mapped in this session, reuse
        if alias in alias_map:
            return alias_map[alias]

        # Check explicit naming like 'h1', 's1', 'h2', 's4'
        if re.match(r"^[hs]\d+$", alias.lower()):
            node_id = alias.lower()
            alias_map[alias] = node_id
            if node_id.startswith("s"):
                self._ensure_switch(node_id, alias)
            else:
                self._ensure_host(node_id, alias)
            return node_id

        # Check spawn metadata
        spawn_sym = self.spawns.get(alias)
        base = spawn_sym.base_type.lower() if spawn_sym else alias.lower()

        # Classify as host or switch
        if any(k in base for k in ("sender", "receiver", "reciever", "host")):
            # It's a host
            h_idx = len(self.ir.hosts) + 1
            node_id = f"h{h_idx}"
            alias_map[alias] = node_id
            self._ensure_host(node_id, alias, spawn_sym)
            return node_id

        elif any(k in base for k in ("ingress", "egress", "switch")):
            # It's a switch
            s_idx = len(self.ir.switches) + 1
            node_id = f"s{s_idx}"
            alias_map[alias] = node_id
            self._ensure_switch(node_id, alias, spawn_sym)
            return node_id

        # Fallback default: treats as switch if starts with 's' or 'sw', else host
        if alias.startswith("s"):
            s_idx = len(self.ir.switches) + 1
            node_id = f"s{s_idx}"
            alias_map[alias] = node_id
            self._ensure_switch(node_id, alias)
            return node_id
        else:
            h_idx = len(self.ir.hosts) + 1
            node_id = f"h{h_idx}"
            alias_map[alias] = node_id
            self._ensure_host(node_id, alias)
            return node_id

    def _ensure_switch(self, s_id: str, alias: str, spawn_sym: Optional[Symbol] = None):
        if s_id in self.ir.switches:
            return

        dpid = int(s_id[1:]) if s_id[1:].isdigit() else len(self.ir.switches) + 1
        name = s_id.upper()

        if spawn_sym is None:
            spawn_sym = self.spawns.get(alias)

        role = "core"
        alias_l = alias.lower()
        base_l = spawn_sym.base_type.lower() if spawn_sym else ""
        if "ing" in alias_l or "ingress" in base_l or s_id == "s1":
            role = "ingress"
        elif "egr" in alias_l or "egress" in base_l:
            role = "egress"

        self.ir.switches[s_id] = {
            "id": s_id,
            "dpid": dpid,
            "name": name,
            "role": role,
            "protocols": "OpenFlow13",
            "subtext": role.capitalize()
        }

    def _ensure_host(self, h_id: str, alias: str, spawn_sym: Optional[Symbol] = None):
        if h_id in self.ir.hosts:
            return

        idx = int(h_id[1:]) if h_id[1:].isdigit() else len(self.ir.hosts) + 1
        ip = f"10.0.0.{idx}"
        name = h_id.upper()

        role = "main_sender" if idx == 1 else ("main_receiver" if idx == 2 else ("cross_sender" if idx == 3 else "cross_receiver"))
        if "sen" in alias.lower():
            role = "main_sender" if idx <= 2 else "cross_sender"
        elif "rec" in alias.lower():
            role = "main_receiver" if idx <= 2 else "cross_receiver"

        colors = {
            "main_sender": "#1e66f5",
            "main_receiver": "#a6e3a1",
            "cross_sender": "#f38ba8",
            "cross_receiver": "#df8e1d"
        }

        self.ir.hosts[h_id] = {
            "id": h_id,
            "name": name,
            "ip": ip,
            "role": role,
            "subtext": ip,
            "color": colors.get(role, "#1e66f5"),
            "connected_to": ""  # populated during link synthesis
        }

    def _compute_bw_mbps(self, raw_rate: Any, is_host_edge: bool) -> float:
        if raw_rate is None or raw_rate == 0:
            return 100.0 if is_host_edge else 10.0

        try:
            val = float(raw_rate)
            if val >= 1_000_000:
                return round(val / 1_000_000.0, 1) if val % 1_000_000 == 0 else round(val / 1_048_576.0, 1)
            elif val >= 1_000:
                # e.g. 1000@kilo -> 1.0 Mbps or 10.0 Mbps
                return round(val / 1000.0, 1) if val < 10_000 else round(val / 1024.0, 1)
            elif val > 0:
                return float(val)
        except (ValueError, TypeError):
            pass

        return 100.0 if is_host_edge else 10.0

    def _compute_delay(self, raw_delay: Any, is_host_edge: bool, src: str, dst: str) -> float:
        if raw_delay is not None:
            try:
                return float(raw_delay)
            except (ValueError, TypeError):
                pass

        if is_host_edge:
            return 1.0

        # Alternate path delay distinction
        if "s3" in (src, dst):
            return 15.0
        return 5.0
