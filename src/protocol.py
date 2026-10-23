"""
Custom Binary Datagram Protocol for SDN UDP Sockets.
Provides packet serialization, sequence tracking, high-resolution timestamps,
and flow identification.
"""

import struct
import time

MAGIC_HEADER = b"SDN1"
HEADER_FORMAT = "!4s I d H B B H"
HEADER_STRUCT = struct.Struct(HEADER_FORMAT)
HEADER_SIZE = HEADER_STRUCT.size  # 22 bytes

# Flow Identifiers
FLOW_MAIN = 1
FLOW_CROSS = 2
FLOW_PROBE = 99

# Packet Flags
FLAG_DATA = 0x01
FLAG_START = 0x02
FLAG_FIN = 0x04
FLAG_HEARTBEAT = 0x08
FLAG_FEEDBACK = 0x10

# Feedback Payload Format: 4 floats (16 bytes)
# (loss_pct, throughput_mbps, latency_ms, suggested_rate_mbps)
FEEDBACK_FORMAT = "!ffff"
FEEDBACK_STRUCT = struct.Struct(FEEDBACK_FORMAT)
FEEDBACK_SIZE = FEEDBACK_STRUCT.size


class InvalidPacketError(Exception):
    """Raised when a received UDP packet does not conform to the protocol."""
    pass


def pack_packet(seq_num: int, flow_id: int = FLOW_MAIN, flags: int = FLAG_DATA, payload: bytes = b"") -> bytes:
    """
    Serializes a UDP datagram packet with the protocol header.
    
    Fields:
      - Magic: 4 bytes ("SDN1")
      - Sequence Number: 4 bytes unsigned int
      - Timestamp: 8 bytes float (sender time in seconds)
      - Flow ID: 2 bytes unsigned short
      - Flags: 1 byte
      - Reserved: 1 byte
      - Payload Length: 2 bytes unsigned short
    """
    send_time = time.time()
    payload_len = len(payload)
    header = HEADER_STRUCT.pack(
        MAGIC_HEADER,
        seq_num,
        send_time,
        flow_id,
        flags,
        0,  # reserved
        payload_len
    )
    return header + payload


def unpack_packet(data: bytes):
    """
    Deserializes a received UDP datagram.
    
    Returns:
      tuple: (seq_num, timestamp, flow_id, flags, payload)
    """
    if len(data) < HEADER_SIZE:
        raise InvalidPacketError(f"Packet too short: {len(data)} bytes < {HEADER_SIZE} bytes")
    
    magic, seq_num, send_time, flow_id, flags, _, payload_len = HEADER_STRUCT.unpack_from(data, 0)
    
    if magic != MAGIC_HEADER:
        raise InvalidPacketError(f"Invalid magic bytes: {magic}")
    
    payload = data[HEADER_SIZE:HEADER_SIZE + payload_len]
    return seq_num, send_time, flow_id, flags, payload


def make_dummy_payload(target_total_packet_size: int = 1024) -> bytes:
    """Creates dummy byte padding so the total packet equals the target size."""
    needed = max(0, target_total_packet_size - HEADER_SIZE)
    return b"X" * needed


def pack_feedback(loss_pct: float, throughput_mbps: float, latency_ms: float, suggested_rate_mbps: float) -> bytes:
    """Serializes receiver congestion feedback payload."""
    payload = FEEDBACK_STRUCT.pack(float(loss_pct), float(throughput_mbps), float(latency_ms), float(suggested_rate_mbps))
    return pack_packet(seq_num=0, flow_id=FLOW_MAIN, flags=FLAG_FEEDBACK, payload=payload)


def unpack_feedback(payload: bytes):
    """Deserializes feedback payload: (loss_pct, throughput_mbps, latency_ms, suggested_rate_mbps)."""
    if len(payload) < FEEDBACK_SIZE:
        raise InvalidPacketError(f"Feedback payload too short: {len(payload)} < {FEEDBACK_SIZE}")
    return FEEDBACK_STRUCT.unpack_from(payload, 0)
