#!/usr/bin/env python3
"""
Root launcher for TopoEditor (Network Topology Editor).
Companion application for SDN Congestion Detection and Dynamic Traffic Rerouting.

Usage:
  python run_topo_editor.py
  python run_topo_editor.py diamond.toponet
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from topo_editor.main import main

if __name__ == "__main__":
    sys.exit(main())
