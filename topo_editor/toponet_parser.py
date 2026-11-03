"""
TopoEditor — File Loading, Serialization, and Format Compatibility.
Supports .toponet format used by the companion SDN network simulator.
"""

import os
import json
from typing import Dict, Any, List, Optional, Tuple

TOPOLOGY_FILE_EXTENSION = ".toponet"


class ToponetFormatError(Exception):
    """Raised when a .toponet file fails extension or JSON schema validation."""
    pass


class ToponetParser:
    """
    Handles reading, parsing, validating, and writing .toponet topology files.
    Preserves exact field compatibility with the existing simulator:
      - format: "topologia-network"
      - version: "1.0"
      - topology_name, description
      - switches (list of switch dicts with id, dpid, name, role, x, y, protocols)
      - hosts (list of host dicts with id, name, ip, role, x, y, connected_to, etc.)
      - links (list of link dicts with id, src, dst, bw_mbps, delay_ms, max_queue, loss_pct, etc.)
      - paths, traffic_profile, sdn_policy, and any other custom root fields preserved intact.
    """

    @staticmethod
    def validate_extension(filepath: str) -> None:
        """Validates that the file path ends with .toponet."""
        if not filepath:
            raise ToponetFormatError("No filepath provided.")
        if not filepath.lower().endswith(TOPOLOGY_FILE_EXTENSION):
            _, ext = os.path.splitext(filepath)
            raise ToponetFormatError(
                f"Invalid file extension '{ext or '<none>'}'. Only '{TOPOLOGY_FILE_EXTENSION}' files are supported."
            )

    @staticmethod
    def load(filepath: str) -> Dict[str, Any]:
        """
        Loads and validates a .toponet file from disk.

        Returns a dictionary containing:
          - topology_name: str
          - description: str
          - format: str
          - version: str
          - switches: list of dicts
          - hosts: list of dicts
          - links: list of dicts
          - paths: dict (optional)
          - traffic_profile: dict (optional)
          - sdn_policy: dict (optional)
          - extra_fields: dict of all unrecognized root keys preserved for round-tripping
        """
        ToponetParser.validate_extension(filepath)

        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Topology file not found: {filepath}")

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as err:
            raise ToponetFormatError(f"Malformed JSON in '{os.path.basename(filepath)}': {err}")
        except Exception as err:
            raise ToponetFormatError(f"Error reading '{os.path.basename(filepath)}': {err}")

        if not isinstance(data, dict):
            raise ToponetFormatError("Toponet file must contain a root JSON object.")

        # Validate essential lists
        for key in ["switches", "hosts", "links"]:
            if key not in data or not isinstance(data[key], list):
                raise ToponetFormatError(f"Missing or invalid required section: '{key}' (must be a list).")

        # Extract known sections
        result: Dict[str, Any] = {
            "filepath": os.path.abspath(filepath),
            "format": data.get("format", "topologia-network"),
            "version": data.get("version", "1.0"),
            "topology_name": data.get("topology_name", "Untitled Topology"),
            "description": data.get("description", ""),
            "switches": data.get("switches", []),
            "hosts": data.get("hosts", []),
            "links": data.get("links", []),
            "paths": data.get("paths", {}),
            "traffic_profile": data.get("traffic_profile", {}),
            "sdn_policy": data.get("sdn_policy", {}),
            "extra_fields": {}
        }

        # Preserve unknown fields
        known_keys = {
            "format", "version", "topology_name", "description",
            "switches", "hosts", "links", "paths", "traffic_profile", "sdn_policy"
        }
        for k, v in data.items():
            if k not in known_keys:
                result["extra_fields"][k] = v

        return result

    @staticmethod
    def save(data: Dict[str, Any], filepath: str) -> None:
        """
        Serializes and writes topology data to a .toponet file.
        Preserves all known and unknown fields to maintain 100% round-trip compatibility.
        """
        ToponetParser.validate_extension(filepath)

        out_data: Dict[str, Any] = {
            "format": data.get("format", "topologia-network"),
            "version": data.get("version", "1.0"),
            "topology_name": data.get("topology_name", "Custom Topology"),
            "description": data.get("description", ""),
            "switches": data.get("switches", []),
            "hosts": data.get("hosts", []),
            "links": data.get("links", [])
        }

        # Keep paths if present
        if data.get("paths"):
            out_data["paths"] = data["paths"]

        # Keep traffic profile if present or synthesize if configured
        if data.get("traffic_profile"):
            out_data["traffic_profile"] = data["traffic_profile"]

        # Keep sdn_policy if present
        if data.get("sdn_policy"):
            out_data["sdn_policy"] = data["sdn_policy"]

        # Re-attach extra fields
        extra = data.get("extra_fields", {})
        for k, v in extra.items():
            if k not in out_data:
                out_data[k] = v

        temp_path = filepath + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(out_data, f, indent=2)
            # Atomically replace destination
            if os.path.exists(filepath):
                os.replace(temp_path, filepath)
            else:
                os.rename(temp_path, filepath)
        except Exception as err:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise ToponetFormatError(f"Failed to write file '{filepath}': {err}")
