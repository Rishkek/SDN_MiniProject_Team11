"""
Unit and Integration Test Suite for TopoEditor.
Verifies file format compatibility, data model operations, validation rules,
undo/redo stack, and companion simulator interoperability.
"""

import os
import tempfile
import pytest
from PyQt6.QtWidgets import QApplication

from topo_editor.toponet_parser import ToponetParser, ToponetFormatError
from topo_editor.topology_manager import (
    TopologyModel, HostData, SwitchData, LinkData
)
from src.topology_loader import load_topology as simulator_load_topology


# ---------------------------------------------------------------------------
# Test 1: Parser File Validation & Round-Trip
# ---------------------------------------------------------------------------
def test_toponet_parser_loading_and_simulator_compat():
    """Verify loading diamond.toponet, saving, and verifying simulator reads it identically."""
    diamond_path = os.path.abspath("diamond.toponet")
    assert os.path.exists(diamond_path), "diamond.toponet must exist"

    # 1. Load via ToponetParser
    parsed = ToponetParser.load(diamond_path)
    assert parsed["format"] == "topologia-network"
    assert len(parsed["switches"]) == 4
    assert len(parsed["hosts"]) == 4
    assert len(parsed["links"]) == 8
    assert "paths" in parsed
    assert "traffic_profile" in parsed

    # 2. Save to temporary file
    with tempfile.NamedTemporaryFile(suffix=".toponet", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        ToponetParser.save(parsed, tmp_path)

        # 3. Reload via ToponetParser
        reloaded = ToponetParser.load(tmp_path)
        assert len(reloaded["switches"]) == 4
        assert len(reloaded["hosts"]) == 4
        assert len(reloaded["links"]) == 8

        # 4. Critical Compatibility Check: Load via existing simulator's loader!
        sim_topo = simulator_load_topology(tmp_path)
        assert sim_topo is not None
        assert len(sim_topo.switches) == 4
        assert len(sim_topo.hosts) == 4
        assert len(sim_topo.links) == 8
        assert sim_topo.get_node("s1") is not None
        assert sim_topo.get_node("h1") is not None
        assert sim_topo.get_path("path_a") is not None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_toponet_extension_enforcement():
    """Verify parser rejects non-.toponet files."""
    with pytest.raises(ToponetFormatError):
        ToponetParser.validate_extension("network.tp")
    with pytest.raises(ToponetFormatError):
        ToponetParser.validate_extension("network.json")
    with pytest.raises(ToponetFormatError):
        ToponetParser.validate_extension("network.vsd")
    with pytest.raises(ToponetFormatError):
        ToponetParser.validate_extension("")

    # Must accept valid extension
    ToponetParser.validate_extension("custom_topology.toponet")
    ToponetParser.validate_extension("PATH/TO/TEST.TOPONET")


# ---------------------------------------------------------------------------
# Test 2: Model Operations, IDs, and Undo / Redo
# ---------------------------------------------------------------------------
def test_topology_model_operations_and_undo():
    """Verify adding, updating, deleting devices, and undo/redo state."""
    model = TopologyModel()

    # Initial state
    assert len(model.hosts) == 0
    assert len(model.switches) == 0
    assert len(model.links) == 0
    assert not model.is_dirty

    # ID Generation
    assert model.generate_next_host_id() == "h1"
    assert model.generate_next_switch_id() == "s1"

    # Add Switch S1
    sw1 = SwitchData(id="s1", name="S1 Ingress", role="ingress", x=0.2, y=0.5)
    model.add_switch(sw1)
    assert "s1" in model.switches
    assert model.generate_next_switch_id() == "s2"
    assert model.is_dirty

    # Add Switch S2
    sw2 = SwitchData(id="s2", name="S2 Core", role="primary", x=0.5, y=0.2)
    model.add_switch(sw2)
    assert len(model.switches) == 2

    # Add Host H1
    h1 = HostData(id="h1", name="Host 1", ip="10.0.0.1", role="sender", x=0.1, y=0.2)
    model.add_host(h1)
    assert "h1" in model.hosts
    assert model.generate_next_host_id() == "h2"

    # Add Link H1 -> S1
    link1 = LinkData(id="link_h1_s1", src="h1", dst="s1", bw_mbps=100.0)
    model.add_link(link1)
    assert "link_h1_s1" in model.links
    assert len(model.get_connected_links("s1")) == 1
    assert model.hosts["h1"].connected_to == "s1"

    # Add Link S1 -> S2
    link2 = LinkData(id="link_s1_s2", src="s1", dst="s2", bw_mbps=10.0, is_bottleneck=True)
    model.add_link(link2)
    assert len(model.links) == 2
    assert len(model.get_connected_links("s1")) == 2

    # Delete Switch S1: Should remove S1 AND both links connected to S1
    model.delete_device("s1")
    assert "s1" not in model.switches
    assert "link_h1_s1" not in model.links
    assert "link_s1_s2" not in model.links

    # Undo deletion: S1 and both links must be restored!
    model.undo_stack.undo()
    assert "s1" in model.switches
    assert "link_h1_s1" in model.links
    assert "link_s1_s2" in model.links
    assert len(model.get_connected_links("s1")) == 2

    # Redo deletion
    model.undo_stack.redo()
    assert "s1" not in model.switches
    assert len(model.links) == 0


# ---------------------------------------------------------------------------
# Test 3: Validation Engine
# ---------------------------------------------------------------------------
def test_topology_validation_rules():
    """Verify validation detects duplicate IDs, invalid links, negative rates, and self loops."""
    model = TopologyModel()

    # 1. Valid basic network
    model.add_switch(SwitchData(id="s1"))
    model.add_switch(SwitchData(id="s2"))
    model.add_host(HostData(id="h1", send_to="h2"))
    model.add_host(HostData(id="h2"))
    model.add_link(LinkData(id="l1", src="h1", dst="s1", bw_mbps=100.0))
    model.add_link(LinkData(id="l2", src="s1", dst="s2", bw_mbps=10.0))
    model.add_link(LinkData(id="l3", src="s2", dst="h2", bw_mbps=100.0))

    errors = model.validate()
    assert len(errors) == 0, f"Expected 0 errors, got: {errors}"

    # 2. Self-loop error
    model.add_link(LinkData(id="l_self", src="s1", dst="s1", bw_mbps=10.0))
    errs = model.validate()
    assert any("itself" in e for e in errs)
    model.delete_link("l_self")

    # 3. Duplicate link between same pair
    model.add_link(LinkData(id="l2_dup", src="s2", dst="s1", bw_mbps=10.0))
    errs = model.validate()
    assert any("Duplicate connection" in e for e in errs)
    model.delete_link("l2_dup")

    # 4. Invalid bandwidth (<= 0)
    model.add_link(LinkData(id="l_bad_bw", src="s1", dst="s2", bw_mbps=-5.0))
    errs = model.validate()
    assert any("greater than 0" in e for e in errs)
    model.delete_link("l_bad_bw")

    # 5. Missing endpoint
    model.add_link(LinkData(id="l_orphan", src="s1", dst="s99", bw_mbps=10.0))
    errs = model.validate()
    assert any("does not exist" in e for e in errs)
    model.delete_link("l_orphan")

    # 6. Host sending to itself
    model.update_host("h1", HostData(id="h1", send_to="h1"))
    errs = model.validate()
    assert any("cannot set itself as its communication destination" in e for e in errs)


# ---------------------------------------------------------------------------
# Test 4: GUI Offscreen Window & Canvas Lifecycle
# ---------------------------------------------------------------------------
def test_topo_editor_gui_offscreen():
    """Verify MainWindow, Canvas, tool modes, and view functions run cleanly offscreen."""
    import sys
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    from topo_editor.main_window import MainWindow
    from topo_editor.topology_canvas import CanvasTool

    win = MainWindow("diamond.toponet")
    assert win.model.topology_name == "Diamond Multi-Path SDN Topology"
    assert len(win.model.switches) == 4
    assert len(win.model.hosts) == 4
    assert len(win.model.links) == 8

    # Test tool switching
    win.canvas.set_tool(CanvasTool.WIRE)
    assert win.canvas.current_tool == CanvasTool.WIRE
    assert win.btn_tool_wire.isChecked()

    win.canvas.set_tool(CanvasTool.SELECT)
    assert win.canvas.current_tool == CanvasTool.SELECT
    assert win.btn_tool_select.isChecked()

    # Test View functions
    win.canvas.zoom_in()
    win.canvas.zoom_out()
    win.canvas.reset_zoom()
    win.canvas.fit_to_screen()

    # Close and cleanup
    win.close()
