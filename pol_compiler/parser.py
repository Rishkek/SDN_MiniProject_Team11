"""
Syntactic parser for Prototype.pol and .pollib languages.
Constructs an Abstract Syntax Tree (AST) from token streams.
"""

from typing import List, Optional, Any, Dict
from pol_compiler.lexer import Token, Lexer
from pol_compiler.ast_nodes import (
    ProgramNode, IncludeNode, DefineNode, GridDirectiveNode,
    UnitDefNode, DataDeclNode, DataOpNode, FieldAssignNode,
    MacroDefNode, MacroCallNode, MacroParam, InstanceNode,
    DetailNode, BundleDeclNode, SpawnNode, SpawnsBlockNode,
    ConnectTupleNode, ConnectionsBlockNode, DeployNode, ASTNode
)


class ParserError(ValueError):
    """Raised when a syntax or parsing error occurs."""
    pass


class Parser:
    """Parses Prototype.pol token streams into an AST."""

    def __init__(self, tokens: List[Token], filepath: str = ""):
        self.tokens = tokens
        self.filepath = filepath
        self.pos = 0
        self.total = len(tokens)

    def current(self) -> Token:
        return self.tokens[self.pos] if self.pos < self.total else self.tokens[-1]

    def peek(self, offset: int = 1) -> Token:
        idx = self.pos + offset
        return self.tokens[idx] if idx < self.total else self.tokens[-1]

    def match(self, *types: str) -> bool:
        if self.current().type in types:
            self.pos += 1
            return True
        return False

    def expect(self, token_type: str, message: str = "") -> Token:
        tok = self.current()
        if tok.type != token_type:
            msg = message or f"Expected token {token_type}, got {tok.type} ('{tok.value}')"
            raise ParserError(f"{msg} at {self.filepath}:{tok.line}:{tok.column}")
        self.pos += 1
        return tok

    def parse(self) -> ProgramNode:
        statements: List[ASTNode] = []
        while not self.match("EOF"):
            stmt = self.parse_top_level_statement()
            if isinstance(stmt, list):
                statements.extend(stmt)
            elif stmt:
                statements.append(stmt)
        return ProgramNode(statements=statements)

    def parse_top_level_statement(self) -> Optional[Any]:
        tok = self.current()

        # Optional extra semicolons
        if self.match("SEMICOLON"):
            return None

        # include
        if self.match("INCLUDE"):
            target_tok = self.current()
            if target_tok.type in ("IDENT", "STRING"):
                self.pos += 1
                target = target_tok.value
                self.match("SEMICOLON")
                return IncludeNode(target=target, line=tok.line, col=tok.column)
            raise ParserError(f"Expected include target path at {tok.line}:{tok.column}")

        # pull (pull@"lib", pull@<header>, pull::lib, pull std)
        if self.match("PULL"):
            return self.parse_pull_statement(tok)

        # define_multi { ... }
        if self.match("DEFINE_MULTI"):
            return self.parse_define_multi(tok)

        # define
        if self.match("DEFINE"):
            return self.parse_define_statement(tok)

        # topology <Name>:
        if self.match("TOPOLOGY"):
            return self.parse_topology_block(tok)

        # top-level spawns or __SPAWNS__
        if (tok.type == "DIRECTIVE" and tok.value == "__SPAWNS__") or tok.type == "SPAWNS" or (tok.type == "IDENT" and tok.value.lower() == "spawns"):
            return self.parse_spawns_block()

        # top-level connections or __CONNECTIONS__
        if (tok.type == "DIRECTIVE" and tok.value == "__CONNECTIONS__") or tok.type == "CONNECTIONS" or (tok.type == "IDENT" and tok.value.lower() == "connections"):
            return self.parse_connections_block()

        # grid ON/OFF
        if self.match("GRID"):
            state_tok = self.current()
            if state_tok.type == "IDENT" and state_tok.value.upper() in ("ON", "OFF"):
                self.pos += 1
                self.match("SEMICOLON")
                return GridDirectiveNode(state=state_tok.value.upper(), line=tok.line, col=tok.column)
            raise ParserError(f"Expected 'ON' or 'OFF' after 'grid' at {tok.line}:{tok.column}")

        # unit definitions: @kilo = 1024 or @mega = 1024@kilo
        if tok.type == "AT_IDENT" and self.peek(1).type == "EQUALS":
            self.pos += 2  # consume AT_IDENT and EQUALS
            val_expr = self.parse_expression()
            self.match("SEMICOLON")
            return UnitDefNode(unit_name=tok.value[1:], value_expr=val_expr, line=tok.line, col=tok.column)

        # macro
        if self.match("MACRO"):
            return self.parse_macro_definition(tok)

        # detail
        if self.match("DETAIL"):
            return self.parse_detail_block(tok)

        # deploy: <target>;
        if self.match("DEPLOY"):
            self.expect("COLON", "Expected ':' after 'deploy'")
            target_tok = self.expect("IDENT", "Expected layout target identifier after 'deploy:'")
            self.match("SEMICOLON")
            return DeployNode(layout_target=target_tok.value, line=tok.line, col=tok.column)

        # If unknown top-level token, consume and warn/raise
        raise ParserError(f"Unexpected top-level token {tok.type} ('{tok.value}') at {tok.line}:{tok.column}")

    def parse_pull_statement(self, start_tok: Token) -> IncludeNode:
        # Optional @ or ::
        if self.match("AT"):
            pass
        elif self.match("DOUBLE_COLON"):
            pass

        target = ""
        # Check if angle bracket: <header> or <header files>
        if self.match("LANGLE"):
            parts = []
            while not self.match("RANGLE") and not self.match("EOF"):
                parts.append(self.current().value)
                self.pos += 1
            target = " ".join(parts).strip()
        elif self.current().type in ("STRING", "IDENT"):
            target_tok = self.current()
            self.pos += 1
            target = target_tok.value
            # If followed by .ext (like data.polh)
            while self.match("DOT"):
                if self.current().type == "IDENT":
                    target += "." + self.current().value
                    self.pos += 1
                else:
                    break
        else:
            raise ParserError(f"Expected header or target path after 'pull' at {start_tok.line}:{start_tok.column}")

        self.match("SEMICOLON")
        return IncludeNode(target=target, line=start_tok.line, col=start_tok.column)

    def parse_define_multi(self, start_tok: Token) -> List[DefineNode]:
        self.expect("LBRACE", "Expected '{' after 'define_multi'")
        defs: List[DefineNode] = []

        while not self.match("RBRACE") and not self.match("EOF"):
            if self.match("SEMICOLON"):
                continue

            # Check for group definition: (&)(sender, reciever) { ... }
            # Or &(sender, reciever) { ... }
            # Or (sender, reciever) { ... }
            if self.current().type in ("AMP", "LPAREN") or (self.current().type == "AMP_IDENT" and self.current().value == "&"):
                if self.current().type == "AMP":
                    self.pos += 1

                # Check for (&)
                if self.current().type == "LPAREN" and self.peek(1).type == "AMP" and self.peek(2).type == "RPAREN":
                    self.pos += 3

                # Expect LPAREN for identifier list
                self.expect("LPAREN", "Expected '(' for symbol tuple in define_multi")
                symbols: List[str] = []
                while not self.match("RPAREN"):
                    s_tok = self.current()
                    if s_tok.type in ("IDENT", "AMP_IDENT"):
                        self.pos += 1
                        val = s_tok.value if s_tok.value.startswith("&") else f"&{s_tok.value}"
                        symbols.append(val)
                    if not self.match("COMMA"):
                        self.expect("RPAREN", "Expected ')' or ',' in define_multi symbol list")
                        break

                self.expect("LBRACE", "Expected '{' for group definition body")
                entries: List[Tuple[str, bool, bool]] = []
                while not self.match("RBRACE") and not self.match("EOF"):
                    if self.match("SEMICOLON"):
                        continue
                    t_tok = self.expect("IDENT", "Expected target type inside define_multi group")
                    target_type = t_tok.value
                    is_unique = False
                    is_common = False
                    while self.current().type == "MODIFIER":
                        mod = self.current().value.lower()
                        self.pos += 1
                        if mod == "--unique":
                            is_unique = True
                        elif mod == "--common":
                            is_common = True
                    self.match("SEMICOLON")
                    entries.append((target_type, is_unique, is_common))

                if len(entries) == 1:
                    ttype, u, c = entries[0]
                    for s in symbols:
                        defs.append(DefineNode(symbol=s, target_type=ttype, is_unique=u, is_common=c, line=start_tok.line, col=start_tok.column))
                elif len(entries) == len(symbols):
                    for s, (ttype, u, c) in zip(symbols, entries):
                        defs.append(DefineNode(symbol=s, target_type=ttype, is_unique=u, is_common=c, line=start_tok.line, col=start_tok.column))
                else:
                    for i, s in enumerate(symbols):
                        entry = entries[i] if i < len(entries) else entries[-1]
                        defs.append(DefineNode(symbol=s, target_type=entry[0], is_unique=entry[1], is_common=entry[2], line=start_tok.line, col=start_tok.column))
                continue

            # Check for inline define statement: define &switch ...
            if self.match("DEFINE"):
                d = self.parse_define_statement(self.tokens[self.pos - 1])
                defs.append(d)
                continue

            # Inline without keyword define: &switch machine.switch --common
            if self.current().type in ("IDENT", "AMP_IDENT"):
                d = self.parse_define_statement(self.current())
                defs.append(d)
                continue

            raise ParserError(f"Unexpected token {self.current().type} ('{self.current().value}') in define_multi at {self.current().line}:{self.current().column}")

        return defs

    def parse_topology_block(self, start_tok: Token) -> DetailNode:
        topo_name = ""
        if self.current().type == "IDENT":
            topo_name = self.current().value
            self.pos += 1
        self.expect("COLON", "Expected ':' after 'topology'")

        body: List[ASTNode] = []
        while self.pos < self.total and self.current().type not in ("EOF", "DEFINE", "DEFINE_MULTI", "DEPLOY", "PULL", "INCLUDE", "TOPOLOGY"):
            if self.match("SEMICOLON"):
                continue
            stmt = self.parse_block_statement()
            if stmt:
                body.append(stmt)
            else:
                break

        target = f"machine.topology.{topo_name.lower()}" if topo_name else "machine.topology.layout"
        return DetailNode(target=target, body=body, line=start_tok.line, col=start_tok.column)

    def parse_define_statement(self, start_tok: Token) -> DefineNode:
        symbol_tok = self.current()
        if symbol_tok.type not in ("IDENT", "AMP_IDENT"):
            raise ParserError(f"Expected identifier in define statement, got {symbol_tok.type} at {symbol_tok.line}:{symbol_tok.column}")
        self.pos += 1
        symbol = symbol_tok.value

        target_type = ""
        is_unique = False
        is_common = False

        # Next could be target_type (e.g. machine.host.sender) or modifier
        if self.current().type == "IDENT":
            target_type = self.current().value
            self.pos += 1

        # Check for trailing modifiers (--unique, --common)
        while self.current().type == "MODIFIER":
            mod = self.current().value.lower()
            self.pos += 1
            if mod == "--unique":
                is_unique = True
            elif mod == "--common":
                is_common = True

        self.match("SEMICOLON")
        return DefineNode(
            symbol=symbol,
            target_type=target_type,
            is_unique=is_unique,
            is_common=is_common,
            line=start_tok.line,
            col=start_tok.column
        )

    def parse_macro_definition(self, start_tok: Token) -> MacroDefNode:
        # e.g. macro @switch switch_define(switch @switch_t, int a, int b, int packet_size, int buffer_size):
        ret_type_tok = self.current()
        ret_type = ""
        if ret_type_tok.type in ("AT_IDENT", "IDENT"):
            ret_type = ret_type_tok.value
            self.pos += 1

        name_tok = self.expect("IDENT", "Expected macro name identifier")
        name = name_tok.value

        self.expect("LPAREN", "Expected '(' after macro name")
        params: List[MacroParam] = []

        while not self.match("RPAREN"):
            type_tok = self.current()
            if type_tok.type in ("IDENT", "AT_IDENT"):
                self.pos += 1
                param_type = type_tok.value
                pname_tok = self.current()
                if pname_tok.type in ("IDENT", "AT_IDENT"):
                    self.pos += 1
                    params.append(MacroParam(type_name=param_type, param_name=pname_tok.value))
                else:
                    params.append(MacroParam(type_name="", param_name=param_type))
            if not self.match("COMMA"):
                self.expect("RPAREN", "Expected ')' or ',' in macro parameter list")
                break

        self.expect("COLON", "Expected ':' after macro header")

        # Parse body statements until 'return'
        body: List[ASTNode] = []
        while not self.match("EOF"):
            if self.current().type == "RETURN":
                self.pos += 1
                # consume return expr
                while self.current().type not in ("SEMICOLON", "EOF"):
                    self.pos += 1
                self.match("SEMICOLON")
                break
            stmt = self.parse_block_statement()
            if stmt:
                body.append(stmt)
            else:
                break

        return MacroDefNode(return_type=ret_type, name=name, params=params, body=body, line=start_tok.line, col=start_tok.column)

    def parse_detail_block(self, start_tok: Token) -> DetailNode:
        target_tok = self.current()
        if target_tok.type not in ("IDENT", "AMP_IDENT"):
            raise ParserError(f"Expected target identifier after 'detail', got {target_tok.type} at {target_tok.line}:{target_tok.column}")
        self.pos += 1
        target = target_tok.value

        self.expect("COLON", "Expected ':' after detail target")

        body: List[ASTNode] = []
        instances: List[str] = []

        # Parse inside detail block until next top-level keyword
        while self.pos < self.total and self.current().type not in ("EOF", "DEFINE", "MACRO", "DEPLOY", "GRID"):
            # Check if encountering a detail keyword
            if self.current().type == "DETAIL":
                next_tok = self.peek(1)
                if next_tok.value in instances:
                    # Nested instance detail block
                    det_tok = self.current()
                    self.pos += 1  # consume 'detail'
                    nested_det = self.parse_detail_block(det_tok)
                    body.append(nested_det)
                    continue
                else:
                    # Reached next top-level detail block
                    break

            # instance <name>
            if self.match("INSTANCE"):
                name_tok = self.expect("IDENT", "Expected instance name")
                instances.append(name_tok.value)
                self.match("SEMICOLON")
                body.append(InstanceNode(name=name_tok.value, line=name_tok.line, col=name_tok.column))
                continue

            stmt = self.parse_block_statement()
            if stmt:
                body.append(stmt)
            else:
                break

        return DetailNode(target=target, body=body, instances=instances, line=start_tok.line, col=start_tok.column)

    def parse_block_statement(self) -> Optional[ASTNode]:
        tok = self.current()

        if self.match("SEMICOLON"):
            return None

        # machine bundle[16];
        if self.match("MACHINE"):
            if self.match("BUNDLE"):
                self.expect("LBRACKET", "Expected '[' after 'bundle'")
                num_tok = self.expect("NUMBER", "Expected bundle capacity integer")
                self.expect("RBRACKET", "Expected ']'")
                self.match("SEMICOLON")
                return BundleDeclNode(element_type="machine", name="bundle", capacity=int(num_tok.value), line=tok.line, col=tok.column)

        # __SPAWNS__ or spawns { ... }@bundle #padding=0
        if (tok.type == "DIRECTIVE" and tok.value == "__SPAWNS__") or tok.type == "SPAWNS" or (tok.type == "IDENT" and tok.value.lower() == "spawns"):
            return self.parse_spawns_block()

        # __CONNECTIONS__ or connections { unpack bundle; connect_multi { ... } }
        if (tok.type == "DIRECTIVE" and tok.value == "__CONNECTIONS__") or tok.type == "CONNECTIONS" or (tok.type == "IDENT" and tok.value.lower() == "connections"):
            return self.parse_connections_block()

        # data declaration: data <name>; or data <name>[size];
        if self.match("DATA"):
            return self.parse_data_statement(tok)

        # data operation: data.define(...), data.in(...), data.out(...), data.flow(...)
        if tok.type == "IDENT" and tok.value.startswith("data.") and self.peek(1).type == "LPAREN":
            op_name = tok.value.split(".", 1)[1]
            self.pos += 2  # consume IDENT and LPAREN
            var_tok = self.expect("IDENT", "Expected variable identifier in data operation")
            self.expect("COMMA", "Expected ',' after variable in data operation")
            val_expr = self.parse_expression()
            self.expect("RPAREN", "Expected ')' closing data operation")
            self.match("SEMICOLON")
            return DataOpNode(op=op_name, var_name=var_tok.value, value_expr=val_expr, line=tok.line, col=tok.column)

        # Field assignment or method call on an identifier:
        # e.g. machine.host::field.rate("out") = send_rate;
        # wire::field.delay = delay;
        # switch_t::ports("in") = a;
        if tok.type in ("IDENT", "AMP_IDENT", "AT_IDENT") and self.peek(1).type == "DOUBLE_COLON":
            return self.parse_field_assignment()

        # Macro call in block: e.g. switch_define(ingress, 1, 2, 1, 256);
        if tok.type == "IDENT" and self.peek(1).type == "LPAREN":
            name = tok.value
            self.pos += 2  # consume IDENT and LPAREN
            args = []
            while not self.match("RPAREN"):
                arg_expr = self.parse_expression()
                args.append(arg_expr)
                if not self.match("COMMA"):
                    self.expect("RPAREN", "Expected ')' or ',' in macro call")
                    break
            self.match("SEMICOLON")
            return MacroCallNode(name=name, args=args, line=tok.line, col=tok.column)

        return None

    def parse_data_statement(self, start_tok: Token) -> ASTNode:
        # Check if it's data.<op>(var, val)
        if self.match("DOT"):
            op_tok = self.expect("IDENT", "Expected data operation name (define, in, out, flow)")
            op_name = op_tok.value
            self.expect("LPAREN", "Expected '(' after data operation")
            var_tok = self.expect("IDENT", "Expected variable identifier in data operation")
            self.expect("COMMA", "Expected ',' after variable in data operation")
            val_expr = self.parse_expression()
            self.expect("RPAREN", "Expected ')'")
            self.match("SEMICOLON")
            return DataOpNode(op=op_name, var_name=var_tok.value, value_expr=val_expr, line=start_tok.line, col=start_tok.column)

        # Standard data variable declaration: data <name>;
        var_tok = self.expect("IDENT", "Expected variable name after 'data'")
        cap_expr = None
        if self.match("LBRACKET"):
            cap_expr = self.parse_expression()
            self.expect("RBRACKET", "Expected ']'")
        self.match("SEMICOLON")
        return DataDeclNode(var_name=var_tok.value, capacity_expr=cap_expr, line=start_tok.line, col=start_tok.column)

    def parse_field_assignment(self) -> FieldAssignNode:
        target_tok = self.current()
        self.pos += 2  # consume target and '::'
        target = target_tok.value

        field_name_tok = self.current()
        if field_name_tok.type not in ("IDENT", "PORTS"):
            raise ParserError(f"Expected field name after '::', got {field_name_tok.type} at {field_name_tok.line}:{field_name_tok.column}")
        field_name = field_name_tok.value
        self.pos += 1

        arg = None
        # Check for method argument: ports("in") or field.rate("out")
        if self.match("LPAREN"):
            arg_tok = self.current()
            if arg_tok.type in ("STRING", "IDENT"):
                arg = arg_tok.value
                self.pos += 1
            self.expect("RPAREN", "Expected ')' after field argument")

        self.expect("EQUALS", "Expected '=' in field assignment")
        val_expr = self.parse_expression()
        self.match("SEMICOLON")

        return FieldAssignNode(target=target, field_name=field_name, arg=arg, value_expr=val_expr, line=target_tok.line, col=target_tok.column)

    def parse_spawns_block(self) -> SpawnsBlockNode:
        start_tok = self.current()
        self.pos += 1  # consume __SPAWNS__ or spawns
        self.expect("LBRACE", "Expected '{' after spawns block header")

        spawns: List[SpawnNode] = []
        while not self.match("RBRACE") and not self.match("EOF"):
            if self.match("SPAWN"):
                type_tok = self.expect("IDENT", "Expected component type after 'spawn'")
                type_name = type_tok.value

                count: Any = 1
                curr = self.current()
                if curr.type == "NUMBER":
                    count = int(curr.value)
                    self.pos += 1
                elif curr.type == "VAR":
                    count = "var"
                    self.pos += 1
                elif curr.type in ("ALIAS", "AS") or (curr.type == "IDENT" and curr.value.lower() in ("alias", "as")):
                    count = "var"

                # Expect alias or as
                alias_kw_tok = self.current()
                if alias_kw_tok.type in ("ALIAS", "AS") or (alias_kw_tok.type == "IDENT" and alias_kw_tok.value.lower() in ("alias", "as")):
                    self.pos += 1
                else:
                    raise ParserError(f"Expected 'alias' or 'as' in spawn declaration, got {alias_kw_tok.type} at {alias_kw_tok.line}:{alias_kw_tok.column}")

                # Comma-separated list of aliases
                aliases: List[str] = []
                first_alias = self.expect("IDENT", "Expected alias identifier")
                aliases.append(first_alias.value)
                while self.match("COMMA"):
                    next_alias = self.expect("IDENT", "Expected alias identifier after comma")
                    aliases.append(next_alias.value)
                self.match("SEMICOLON")

                for a in aliases:
                    spawns.append(SpawnNode(type_name=type_name, count=count, alias=a, line=type_tok.line, col=type_tok.column))
            elif self.match("SEMICOLON"):
                continue
            else:
                # Unexpected token in spawns
                raise ParserError(f"Unexpected token {self.current().type} ('{self.current().value}') in spawns block at {self.current().line}:{self.current().column}")

        # Check for optional trailing }@bundle #padding=0
        bundle_target = None
        padding = 0
        if self.match("AT_IDENT"):
            bundle_target = self.tokens[self.pos - 1].value[1:]

        if self.match("PADDING_DIRECTIVE"):
            padding = int(self.tokens[self.pos - 1].value)

        return SpawnsBlockNode(spawns=spawns, bundle_target=bundle_target, padding=padding, line=start_tok.line, col=start_tok.column)

    def parse_connections_block(self) -> ConnectionsBlockNode:
        start_tok = self.current()
        self.pos += 1  # consume __CONNECTIONS__ or connections
        self.expect("LBRACE", "Expected '{' after connections block header")

        unpack_target = None
        connections: List[ConnectTupleNode] = []

        while not self.match("RBRACE") and not self.match("EOF"):
            if self.match("UNPACK"):
                t_tok = self.current()
                if t_tok.type in ("IDENT", "BUNDLE"):
                    self.pos += 1
                    unpack_target = t_tok.value
                else:
                    raise ParserError(f"Expected bundle target identifier after 'unpack', got {t_tok.type} at {t_tok.line}:{t_tok.column}")
                self.match("SEMICOLON")
                continue

            if self.match("CONNECT_MULTI"):
                self.expect("LBRACE", "Expected '{' after 'connect_multi'")
                while not self.match("RBRACE") and not self.match("EOF"):
                    if self.match("LPAREN"):
                        # (src, cable, dst)
                        src_tok = self.expect("IDENT", "Expected source node in connection tuple")
                        self.expect("COMMA", "Expected ',' after source node")
                        cable_tok = self.expect("IDENT", "Expected cable identifier in connection tuple")
                        self.expect("COMMA", "Expected ',' after cable")
                        dst_tok = self.expect("IDENT", "Expected destination node in connection tuple")
                        self.expect("RPAREN", "Expected ')' closing connection tuple")
                        self.match("SEMICOLON")

                        connections.append(ConnectTupleNode(
                            src=src_tok.value,
                            cable=cable_tok.value,
                            dst=dst_tok.value,
                            line=src_tok.line,
                            col=src_tok.column
                        ))
                    elif self.match("SEMICOLON"):
                        continue
                    else:
                        raise ParserError(f"Unexpected token in connect_multi: {self.current().type} at {self.current().line}:{self.current().column}")
                continue

            # Direct connection tuple: (src, cable, dst);
            if self.match("LPAREN"):
                src_tok = self.expect("IDENT", "Expected source node in connection tuple")
                self.expect("COMMA", "Expected ',' after source node")
                cable_tok = self.expect("IDENT", "Expected cable identifier in connection tuple")
                self.expect("COMMA", "Expected ',' after cable")
                dst_tok = self.expect("IDENT", "Expected destination node in connection tuple")
                self.expect("RPAREN", "Expected ')' closing connection tuple")
                self.match("SEMICOLON")

                connections.append(ConnectTupleNode(
                    src=src_tok.value,
                    cable=cable_tok.value,
                    dst=dst_tok.value,
                    line=src_tok.line,
                    col=src_tok.column
                ))
                continue

            if self.match("SEMICOLON"):
                continue

            raise ParserError(f"Unexpected token in connections block: {self.current().type} at {self.current().line}:{self.current().column}")

        return ConnectionsBlockNode(unpack_target=unpack_target, connections=connections, line=start_tok.line, col=start_tok.column)

    def parse_expression(self) -> Any:
        """Parses atomic or arithmetic expression (literals, units, identifiers)."""
        tok = self.current()

        if tok.type == "NUMBER_WITH_UNIT":
            self.pos += 1
            return tok.value  # e.g. "100@kilo", "10@mega"

        if tok.type == "NUMBER":
            self.pos += 1
            num = float(tok.value) if "." in tok.value else int(tok.value)
            # check for immediately following @unit on same line (e.g. 100@kilo if split)
            if self.current().type == "AT_IDENT" and self.current().line == tok.line:
                unit_tok = self.current()
                self.pos += 1
                num = ("BIN_OP", "STAR", num, unit_tok.value)
            # check for binary arithmetic (+, -, *, /)
            if self.current().type in ("PLUS", "MINUS", "STAR", "SLASH"):
                op = self.current().type
                self.pos += 1
                right = self.parse_expression()
                return ("BIN_OP", op, num, right)
            return num

        if tok.type == "STRING":
            self.pos += 1
            return tok.value

        if tok.type in ("IDENT", "AMP_IDENT", "AT_IDENT"):
            self.pos += 1
            ident = tok.value
            # check if followed by @unit on same line, e.g. packet_size@kilo
            if self.current().type == "AT_IDENT" and self.current().line == tok.line:
                unit_tok = self.current()
                self.pos += 1
                ident = ("BIN_OP", "STAR", ident, unit_tok.value)

            # check for multiplication with units, e.g. buffer_size*packet
            if self.current().type in ("PLUS", "MINUS", "STAR", "SLASH"):
                op = self.current().type
                self.pos += 1
                right = self.parse_expression()
                return ("BIN_OP", op, ident, right)
            return ident

        raise ParserError(f"Expected expression, got {tok.type} ('{tok.value}') at {tok.line}:{tok.column}")
