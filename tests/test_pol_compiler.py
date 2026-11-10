"""
Unit and integration tests for the TopoNet Prototype.pol Compiler (pol_compiler).
Tests lexing, parsing, preprocessing, semantic validation (--unique, max counts),
and end-to-end compilation of all 5 topologies into standard .json files.
"""

import os
import pytest
from pol_compiler.lexer import Lexer, LexerError
from pol_compiler.parser import Parser, ParserError
from pol_compiler.preprocessor import Preprocessor, PreprocessorError
from pol_compiler.semantic import SemanticAnalyzer, SemanticError
from pol_compiler.compiler import PolCompiler, compile_pol_file
from src.topology_loader import load_topology, TopologyDefinition


class TestLexer:
    """Verifies tokenization of Prototype.pol DSL tokens."""

    def test_basic_tokens(self):
        code = "define &sender machine.host.sender --unique"
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        types = [t.type for t in tokens]
        assert "DEFINE" in types
        assert "AMP_IDENT" in types
        assert "IDENT" in types
        assert "MODIFIER" in types

    def test_units_and_directives(self):
        code = "@mega = 1024@kilo\n__SPAWNS__ { spawn cable.high_speed 2 alias hi; }@bundle #padding=0"
        lexer = Lexer(code)
        tokens = lexer.tokenize()
        types = [t.type for t in tokens]
        assert "AT_IDENT" in types
        assert "EQUALS" in types
        assert "NUMBER_WITH_UNIT" in types
        assert "DIRECTIVE" in types
        assert "PADDING_DIRECTIVE" in types


class TestPreprocessor:
    """Verifies include resolution and circular dependency rejection."""

    def test_standard_library_include(self):
        preprocessor = Preprocessor(search_paths=["lib", "."])
        path = preprocessor.resolve_target_path("lib.machine")
        assert os.path.isfile(path)
        assert path.endswith("machine.pollib")

    def test_circular_include_detection(self, tmp_path):
        f1 = tmp_path / "a.pol"
        f2 = tmp_path / "b.pol"
        f1.write_text("include b.pol\n", encoding="utf-8")
        f2.write_text("include a.pol\n", encoding="utf-8")

        pre = Preprocessor(search_paths=[str(tmp_path)])
        with pytest.raises(PreprocessorError, match="Circular include detected"):
            pre.load_and_preprocess(str(f1))


class TestParser:
    """Verifies AST construction from tokens."""

    def test_parse_simple_program(self):
        code = """
        include lib.machine
        define &ingress machine.switch --unique
        grid OFF
        deploy: machine.topology.layout;
        """
        lexer = Lexer(code)
        parser = Parser(lexer.tokenize())
        ast = parser.parse()
        assert len(ast.statements) == 4

    def test_syntax_error_unclosed_block(self):
        code = "detail sender { data rate;"
        lexer = Lexer(code)
        parser = Parser(lexer.tokenize())
        with pytest.raises(ParserError):
            parser.parse()


class TestSemanticAnalyzer:
    """Verifies symbol table, unit evaluation, and semantic constraint enforcement."""

    def test_unit_and_expr_evaluation(self):
        analyzer = SemanticAnalyzer()
        assert analyzer.eval_expr("10@mega") == 10 * 1048576.0
        assert analyzer.eval_expr("100@kilo") == 100 * 1024.0

    def test_unique_constraint_enforcement(self):
        code = """
        define &ingress machine.switch --unique
        detail machine.topology.layout:
            __SPAWNS__ {
                spawn ingress 2 alias ing;
            }
        """
        lexer = Lexer(code)
        ast = Parser(lexer.tokenize()).parse()
        analyzer = SemanticAnalyzer()
        with pytest.raises(SemanticError, match="declared as --unique"):
            analyzer.analyze(ast)

    def test_max_instance_limit_enforcement(self):
        code = """
        define &switch machine.switch --common
        define &cable wire --common
        detail cable:
            instance lo
        detail machine.topology.layout:
            __SPAWNS__ {
                spawn cable.lo 1 alias lo;
                spawn switch alias s1;
                spawn switch alias s2;
                spawn switch alias s3;
            }
            __CONNECTIONS__ {
                connect_multi {
                    (s1, lo, s2);
                    (s2, lo, s3);
                }
            }
        """
        lexer = Lexer(code)
        ast = Parser(lexer.tokenize()).parse()
        analyzer = SemanticAnalyzer()
        with pytest.raises(SemanticError, match="exceeded its maximum instance limit"):
            analyzer.analyze(ast)


class TestEndToEndCompilation:
    """Verifies compilation of all 5 topologies into standard .json and TopologyDefinition."""

    @pytest.mark.parametrize("topo_name,expected_switches,expected_hosts", [
        ("diamond", 4, 4),
        ("star", 1, 4),
        ("mesh", 4, 4),
        ("bus", 4, 4),
        ("ring", 4, 4),
    ])
    def test_compile_and_load_topologies(self, topo_name, expected_switches, expected_hosts):
        pol_file = f"pol_src/{topo_name}.pol"
        out_json = f"topology_src/{topo_name}.json"

        assert os.path.exists(pol_file), f"Source file {pol_file} missing"

        compiler = PolCompiler()
        data = compiler.compile_file(pol_file, output_path=out_json)

        assert data["format"] == "network-topology"
        assert len(data["switches"]) == expected_switches
        assert len(data["hosts"]) == expected_hosts
        assert "paths" in data
        assert "traffic_profile" in data
        assert "sdn_policy" in data

        # Load with TopologyDefinition
        topo_def = load_topology(out_json)
        assert isinstance(topo_def, TopologyDefinition)
        assert len(topo_def.switches) == expected_switches
        assert len(topo_def.hosts) == expected_hosts
        assert len(topo_def.links) > 0


class TestSimplifiedSyntaxFeatures:
    """Verifies simplified Prototype.pol language enhancements."""

    def test_simplified_pull_directives(self):
        preprocessor = Preprocessor()
        p1 = preprocessor.resolve_target_path("std")
        p2 = preprocessor.resolve_target_path('"std.polh"')
        p3 = preprocessor.resolve_target_path("<std.polh>")
        assert os.path.isfile(p1) and p1.endswith("std.polh")
        assert os.path.abspath(p1) == os.path.abspath(p2) == os.path.abspath(p3)

    def test_define_multi_pairwise_and_broadcast(self):
        code = """
        define_multi {
            (&)(s_node, r_node) {
                machine.host.sender;
                machine.host.reciever
            }
            (&)(ing, egr) {
                machine.switch --unique
            }
            &core machine.switch --common
        }
        """
        tokens = Lexer(code).tokenize()
        ast = Parser(tokens).parse()
        defines = [s for s in ast.statements if hasattr(s, "symbol")]
        assert len(defines) == 5

        by_symbol = {d.symbol: d for d in defines}
        assert by_symbol["&s_node"].target_type == "machine.host.sender"
        assert by_symbol["&r_node"].target_type == "machine.host.reciever"
        assert by_symbol["&ing"].target_type == "machine.switch" and by_symbol["&ing"].is_unique
        assert by_symbol["&egr"].target_type == "machine.switch" and by_symbol["&egr"].is_unique
        assert by_symbol["&core"].target_type == "machine.switch" and by_symbol["&core"].is_common

    def test_simplified_diamond_compilation(self):
        compiler = PolCompiler()
        data = compiler.compile_file(
            "pol_src/simplified_diamond.pol",
            output_path="topology_src/simplified_diamond.json"
        )
        assert data["format"] == "network-topology"
        assert len(data["switches"]) == 4
        assert len(data["hosts"]) == 4
        assert len(data["links"]) == 8
        assert "path_a" in data["paths"]

        topo_def = load_topology("topology_src/simplified_diamond.json")
        assert len(topo_def.switches) == 4
        assert len(topo_def.hosts) == 4

    def test_comments_support(self):
        code = """
        // Single-line C++ comment
        /* Multi-line
           block comment */
        # Shell comment
        pull std
        """
        tokens = Lexer(code).tokenize()
        ast = Parser(tokens).parse()
        assert len(ast.statements) == 1


class TestNativeCCompiler:
    """Verifies that the native C compiler (polc.exe) builds and compiles valid topologies."""

    def test_native_c_binary_exists(self):
        polc_exe = "polc.exe" if os.name == "nt" else "./polc"
        assert os.path.exists(polc_exe), f"Native compiler {polc_exe} should exist"

    def test_native_c_compile_diamond(self, tmp_path):
        out_json = str(tmp_path / "diamond_c.json")
        cmd = f"polc.exe pol_src/diamond.pol -o \"{out_json}\""
        ret = os.system(cmd)
        assert ret == 0
        assert os.path.exists(out_json)
        topo = load_topology(out_json)
        assert len(topo.switches) == 4
        assert len(topo.hosts) == 4
        assert len(topo.links) == 8

    def test_native_c_compile_test_david(self, tmp_path):
        out_json = str(tmp_path / "test_c.json")
        cmd = f"polc.exe pol_src/test.pol -o \"{out_json}\""
        ret = os.system(cmd)
        assert ret == 0
        assert os.path.exists(out_json)
        topo = load_topology(out_json)
        assert len(topo.switches) == 5
        assert len(topo.hosts) == 2
