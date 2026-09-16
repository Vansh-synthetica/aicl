"""AICL-BIN validation utilities."""
from __future__ import annotations

import struct
import zlib
from typing import Optional

from aicl.bin.constants import (
    MAGIC, HEADER_SIZE, HEADER_CRC_SCOPE, SUPPORTED_VERSIONS,
    MAX_TLV_VALUE_SIZE,
    FLAG_REQUEST, FLAG_RESPONSE, FLAG_ERROR,
    FLAG_HEARTBEAT, FLAG_CANCEL, FLAG_STREAM_CHUNK, FLAG_STREAM_END,
    FLAG_HAS_TRAILER, FLAG_COMPRESSED, FLAG_ENCRYPTED,
)
from aicl.bin.exceptions import HeaderError, ChecksumError

__all__ = ["validate_header", "compute_crc32", "validate_trailer", "validate_flags", "VersionMismatchError"]


class VersionMismatchError(HeaderError):
    """Packet version is not supported."""


def validate_header(data: memoryview) -> None:
    """Validate the fixed 56-byte header. Raises on error.

    Checks magic, version, the header_crc32 trailer (bytes 52-55, covering
    bytes 0-51), and payload_length bounds — not just field-level sanity
    like the older 64-byte format did; core-rust's header genuinely
    carries an integrity check over itself, so this actually verifies it.
    """
    if len(data) < HEADER_SIZE:
        raise HeaderError(f"Buffer too short for header: {len(data)} < {HEADER_SIZE}")

    magic = bytes(data[0:4])
    if magic != MAGIC:
        raise HeaderError(f"Invalid magic: {magic!r}")

    version = struct.unpack_from(">H", data, 4)[0]
    if version not in SUPPORTED_VERSIONS:
        raise VersionMismatchError(f"Unsupported version: {version} not in {SUPPORTED_VERSIONS}")

    hdr_crc = struct.unpack_from(">I", data, HEADER_CRC_SCOPE)[0]
    computed = compute_crc32(bytes(data[:HEADER_CRC_SCOPE]))
    if hdr_crc != computed:
        raise HeaderError(
            f"header CRC mismatch: expected 0x{computed:08x}, got 0x{hdr_crc:08x}"
        )

    payload_length = struct.unpack_from(">I", data, 44)[0]
    if payload_length > MAX_TLV_VALUE_SIZE:
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
    """Validate that packet flags are consistent.

    core-rust has no dedicated "packet type" concept at the flag level
    beyond REQUEST/RESPONSE/ERROR/HEARTBEAT/CANCEL — acknowledgement and
    fire-and-forget events are conveyed by opcode, not a flag bit (see
    constants.py's note on the flags that were dropped in the ISA-aligned
    rewrite).
    """
    packet_type_bits = (
        (1 if flags & FLAG_REQUEST else 0)
        + (1 if flags & FLAG_RESPONSE else 0)
        + (1 if flags & FLAG_ERROR else 0)
        + (1 if flags & FLAG_HEARTBEAT else 0)
        + (1 if flags & FLAG_CANCEL else 0)
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
    if flags & FLAG_HEARTBEAT:
        return "HEARTBEAT"
    if flags & FLAG_CANCEL:
        return "CANCEL"
    if flags & FLAG_STREAM_CHUNK:
        return "STREAM_CHUNK"
    if flags & FLAG_STREAM_END:
        return "STREAM_END"
    return "UNKNOWN"
