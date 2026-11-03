#!/usr/bin/env python3
"""
TopoEditor — Application Entry Point.
Topic 27: SDN Congestion Detection and Dynamic Traffic Rerouting.

Usage:
  python main.py
  python main.py path/to/topology.toponet
"""

import sys
import os
import argparse

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from topo_editor.main_window import MainWindow


def main():
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    app.setApplicationName("TopoEditor")
    app.setApplicationDisplayName("TopoEditor — Network Topology Editor")
    app.setOrganizationName("SDN Team 11")

    # Set default modern font
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    parser = argparse.ArgumentParser(description="TopoEditor — Network Topology Editor (.toponet)")
    parser.add_argument("file", nargs="?", default=None, help="Optional .toponet file to open on startup")
    args, unknown = parser.parse_known_args()

    # Look for diamond.toponet if no file specified and it exists in root
    target_file = args.file
    if not target_file:
        candidate = os.path.join(BASE_DIR, "diamond.toponet")
        if os.path.exists(candidate):
            target_file = candidate

    window = MainWindow(initial_filepath=target_file)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
