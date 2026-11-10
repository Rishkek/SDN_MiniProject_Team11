"""
Unit and integration tests for the Native C TopoNet Prototype.pol Compiler (polc).
Validates end-to-end compilation of all topologies (.pol / .polh) into standard JSON
topology definitions and ensures seamless integration with TopologyDefinition.
"""

import os
import subprocess
import pytest
from src.topology_loader import load_topology, TopologyDefinition


POLC_BIN = "polc.exe" if os.name == "nt" else "./polc"


class TestNativePolCompiler:
    """Verifies that the native C compiler (polc) operates properly."""

    def test_native_c_binary_exists(self):
        assert os.path.exists(POLC_BIN), f"Native compiler binary {POLC_BIN} must exist"

    def test_native_c_help_flag(self):
        res = subprocess.run([POLC_BIN, "--help"], capture_output=True, text=True)
        assert res.returncode == 0
        assert "Usage: polc" in res.stdout

    @pytest.mark.parametrize("topo_name,expected_switches,expected_hosts,expected_links", [
        ("diamond", 4, 4, 8),
        ("star", 1, 4, 4),
        ("bus", 4, 4, 7),
        ("ring", 4, 4, 8),
        ("mesh", 4, 4, 10),
        ("test", 5, 2, 7),
    ])
    def test_compile_topologies_native(self, topo_name, expected_switches, expected_hosts, expected_links, tmp_path):
        pol_file = f"pol_src/{topo_name}.pol"
        out_json = str(tmp_path / f"{topo_name}.json")

        assert os.path.exists(pol_file), f"Source file {pol_file} missing"

        res = subprocess.run([POLC_BIN, pol_file, "-o", out_json], capture_output=True, text=True)
        assert res.returncode == 0, f"Compilation failed: {res.stderr}"
        assert os.path.exists(out_json), f"Target JSON {out_json} was not created"

        topo = load_topology(out_json)
        assert isinstance(topo, TopologyDefinition)
        assert len(topo.switches) == expected_switches
        assert len(topo.hosts) == expected_hosts
        assert len(topo.links) == expected_links
        assert len(topo.paths) >= 1

    def test_compile_all_flag(self, tmp_path):
        res = subprocess.run([POLC_BIN, "--all"], capture_output=True, text=True)
        assert res.returncode == 0
        assert "[SUCCESS] Compiled" in res.stdout

        for name in ("diamond", "star", "bus", "ring", "mesh", "test"):
            json_file = f"topology_src/{name}.json"
            assert os.path.exists(json_file)
            topo = load_topology(json_file)
            assert isinstance(topo, TopologyDefinition)

    def test_polh_include_resolution(self, tmp_path):
        # Create a test .pol file pulling std.polh
        test_pol = tmp_path / "custom_diamond.pol"
        test_pol.write_text(
            'pull "std.polh"\n\n'
            'topology Custom:\n'
            '    spawns {\n'
            '        spawn cable.high_speed as hi;\n'
            '        spawn switch as s1, s2;\n'
            '        spawn sender as h1;\n'
            '        spawn reciever as h2;\n'
            '    }\n'
            '    connections {\n'
            '        (h1, hi, s1);\n'
            '        (s1, hi, s2);\n'
            '        (s2, hi, h2);\n'
            '    }\n',
            encoding="utf-8"
        )
        out_json = str(tmp_path / "custom_diamond.json")
        res = subprocess.run([POLC_BIN, str(test_pol), "-o", out_json], capture_output=True, text=True)
        assert res.returncode == 0
        topo = load_topology(out_json)
        assert len(topo.switches) == 2
        assert len(topo.hosts) == 2
        assert len(topo.links) == 3

    def test_nonexistent_file_handling(self):
        res = subprocess.run([POLC_BIN, "nonexistent_file_xyz.pol"], capture_output=True, text=True)
        assert res.returncode != 0
        assert "[ERROR]" in res.stderr or "[ERROR]" in res.stdout
