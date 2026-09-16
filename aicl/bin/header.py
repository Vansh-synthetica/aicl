"""AICL-BIN fixed header (64 bytes) encoder/decoder."""
from __future__ import annotations

import struct
from typing import NamedTuple

from aicl.bin.constants import (
    HEADER_SIZE,
    CURRENT_VERSION,
    SUPPORTED_VERSIONS,
    HEADER_STRUCT,
)
from aicl.bin.exceptions import HeaderError

__all__ = [
    "Header",
    "pack_header",
    "unpack_header",
]


class Header(NamedTuple):
    """Fixed 64-byte header fields."""

    magic: bytes
    version: int
    flags: int
    session_id: bytes
    message_id: bytes
    correlation_id: bytes
    payload_length: int
    target_count: int
    reserved: int


def pack_header(
    version: int,
    flags: int,
    session_id: bytes,
    message_id: bytes,
    correlation_id: bytes,
    payload_length: int,
    target_count: int,
) -> bytes:
    """Pack the 64-byte fixed header.

    All IDs must be exactly 16 bytes.
    """
    if version not in SUPPORTED_VERSIONS:
        raise HeaderError(f"Unsupported version: {version}")
    if len(session_id) != 16:
        raise HeaderError(f"session_id must be 16 bytes, got {len(session_id)}")
    if len(message_id) != 16:
        raise HeaderError(f"message_id must be 16 bytes, got {len(message_id)}")
    if len(correlation_id) != 16:
        raise HeaderError(f"correlation_id must be 16 bytes, got {len(correlation_id)}")
    if payload_length > 0xFFFFFF:
        raise HeaderError(f"payload_length too large: {payload_length}")
    if target_count > 0xFFFF:
        raise HeaderError(f"target_count too large: {target_count}")

    return struct.pack(
        HEADER_STRUCT,
        b"AICL",
        version,
        flags,
        session_id,
        message_id,
        correlation_id,
        payload_length,
        target_count,
        0,  # reserved
    )


def unpack_header(data: memoryview) -> Header:
    """Unpack the 64-byte fixed header from a memoryview."""
    if len(data) < HEADER_SIZE:
        raise HeaderError(f"Header too short: {len(data)} < {HEADER_SIZE}")

    try:
        magic, version, flags, session_id, message_id, correlation_id, payload_length, target_count, reserved = struct.unpack_from(
            HEADER_STRUCT, data, 0
        )
    except struct.error as exc:
        raise HeaderError(f"Failed to unpack header: {exc}") from exc

    if magic != b"AICL":
        raise HeaderError(f"Invalid magic: {magic!r} != b'AICL'")
    if version not in SUPPORTED_VERSIONS:
        raise HeaderError(f"Unsupported version: {version}")
    if payload_length > 0xFFFFFF:
        raise HeaderError(f"payload_length too large: {payload_length}")
    if target_count > 0xFFFF:
        raise HeaderError(f"target_count too large: {target_count}")

    return Header(
        magic=magic,
        version=version,
        flags=flags,
        session_id=session_id,
        message_id=message_id,
        correlation_id=correlation_id,
        payload_length=payload_length,
        target_count=target_count,
        reserved=reserved,
    )