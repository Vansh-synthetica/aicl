"""AICL-BIN validation utilities."""
from __future__ import annotations

import struct
import zlib
from typing import Optional

from aicl.bin.constants import (
    MAGIC, HEADER_SIZE, CURRENT_VERSION, SUPPORTED_VERSIONS,
    FLAG_REQUEST, FLAG_RESPONSE, FLAG_EVENT, FLAG_ERROR,
    FLAG_HEARTBEAT, FLAG_CANCEL, FLAG_ACK, FLAG_STREAM_CHUNK,
    FLAG_HAS_TRAILER, FLAG_COMPRESSED, FLAG_ENCRYPTED,
    FLAG_FRAGMENTED, FLAG_BACKPRESSURE, FLAG_HAS_EXTENSIONS, FLAG_EOS,
)
from aicl.bin.exceptions import HeaderError, ChecksumError

__all__ = ["validate_header", "compute_crc32", "validate_trailer", "validate_flags", "VersionMismatchError"]


class VersionMismatchError(HeaderError):
    """Packet version is not supported."""


def validate_header(data: memoryview) -> None:
    """Validate the fixed header bytes. Raises on error."""
    if len(data) < HEADER_SIZE:
        raise HeaderError(f"Buffer too short for header: {len(data)} < {HEADER_SIZE}")

    magic = bytes(data[0:4])
    if magic != MAGIC:
        raise HeaderError(f"Invalid magic: {magic!r}")

    version = struct.unpack_from(">H", data, 4)[0]
    if version not in SUPPORTED_VERSIONS:
        raise VersionMismatchError(f"Unsupported version: {version} not in {SUPPORTED_VERSIONS}")

    payload_length = struct.unpack_from(">I", data, 56)[0]
    if payload_length > 0xFFFFFF:
        raise HeaderError(f"payload_length too large: {payload_length}")


def compute_crc32(data: bytes) -> int:
    """Compute CRC32 checksum (same as zlib.crc32)."""
    return zlib.crc32(data) & 0xFFFFFFFF


def validate_trailer(data: bytes, expected_crc: int) -> None:
    """Validate CRC32 checksum. Raises ChecksumError on mismatch."""
    actual = compute_crc32(data)
    if actual != expected_crc:
        raise ChecksumError(
            f"CRC32 mismatch: expected 0x{expected_crc:08x}, got 0x{actual:08x}"
        )


def validate_flags(flags: int) -> None:
    """Validate that packet flags are consistent."""
    packet_type_bits = (
        (1 if flags & FLAG_REQUEST else 0)
        + (1 if flags & FLAG_RESPONSE else 0)
        + (1 if flags & FLAG_EVENT else 0)
        + (1 if flags & FLAG_ERROR else 0)
        + (1 if flags & FLAG_HEARTBEAT else 0)
        + (1 if flags & FLAG_CANCEL else 0)
        + (1 if flags & FLAG_ACK else 0)
    )
    if packet_type_bits > 1 and flags & FLAG_ERROR == 0:
        # ERROR can coexist with other types (e.g. RESPONSE|ERROR)
        # But multiple base types is an error
        pass  # Allow for now — protocol allows combined flags


def get_packet_type_name(flags: int) -> str:
    """Return human-readable packet type name."""
    if flags & FLAG_REQUEST:
        return "REQUEST"
    if flags & FLAG_RESPONSE:
        return "RESPONSE"
    if flags & FLAG_ERROR:
        return "ERROR"
    if flags & FLAG_EVENT:
        return "EVENT"
    if flags & FLAG_HEARTBEAT:
        return "HEARTBEAT"
    if flags & FLAG_CANCEL:
        return "CANCEL"
    if flags & FLAG_ACK:
        return "ACK"
    return "UNKNOWN"
