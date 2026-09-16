"""AICL-BIN fixed header (56 bytes) encoder/decoder.

Layout (matches core-rust/src/codec.rs exactly, byte for byte):

    offset  size  field
    0       4     magic         b"AICL"
    4       2     version       u16 BE, 0x0100 (major=1, minor=0)
    6       2     flags         u16 BE
    8       16    message_id    raw UUID bytes
    24      16    correlation_id raw UUID bytes
    40      4     deadline_ms   u32 BE
    44      4     payload_length u32 BE
    48      4     (zero padding — not a field, keeps header_crc32 8-byte
                   aligned; part of the CRC-covered prefix)
    52      4     header_crc32  u32 BE, CRC32 over bytes 0-51

Older AICL-BIN versions of this codebase used a different, incompatible
64-byte layout (session_id + target_count instead of deadline_ms, no
header CRC) — see WIRE_FORMAT_AUDIT.md for the full history. This is the
ISA-spec-compliant layout the Rust implementation actually uses on the
wire.
"""
from __future__ import annotations

import struct
from typing import NamedTuple

from aicl.bin.constants import (
    HEADER_SIZE,
    HEADER_CRC_SCOPE,
    HEADER_STRUCT,
    HEADER_PREFIX_STRUCT,
    SUPPORTED_VERSIONS,
    MAGIC,
)
from aicl.bin.exceptions import HeaderError
from aicl.bin.validation import compute_crc32

__all__ = [
    "Header",
    "pack_header",
    "unpack_header",
]


class Header(NamedTuple):
    """Fixed 56-byte header fields."""

    magic: bytes
    version: int
    flags: int
    message_id: bytes
    correlation_id: bytes
    deadline_ms: int
    payload_length: int


def pack_header(
    version: int,
    flags: int,
    message_id: bytes,
    correlation_id: bytes,
    deadline_ms: int,
    payload_length: int,
) -> bytes:
    """Pack the 56-byte fixed header, including its trailing header_crc32.

    ``message_id`` and ``correlation_id`` must each be exactly 16 bytes.
    """
    if version not in SUPPORTED_VERSIONS:
        raise HeaderError(f"Unsupported version: {version}")
    if len(message_id) != 16:
        raise HeaderError(f"message_id must be 16 bytes, got {len(message_id)}")
    if len(correlation_id) != 16:
        raise HeaderError(f"correlation_id must be 16 bytes, got {len(correlation_id)}")
    if payload_length > 0xFFFFFFFF:
        raise HeaderError(f"payload_length too large: {payload_length}")
    if deadline_ms > 0xFFFFFFFF:
        raise HeaderError(f"deadline_ms too large: {deadline_ms}")

    prefix = struct.pack(
        HEADER_PREFIX_STRUCT,
        MAGIC,
        version,
        flags,
        message_id,
        correlation_id,
        deadline_ms,
        payload_length,
    )
    assert len(prefix) == HEADER_CRC_SCOPE, (
        f"header prefix is {len(prefix)} bytes, expected {HEADER_CRC_SCOPE}"
    )
    crc = compute_crc32(prefix)
    return prefix + struct.pack(">I", crc)


def unpack_header(data: memoryview) -> Header:
    """Unpack the 56-byte fixed header from a memoryview.

    Does not validate the header CRC itself — see
    ``validation.validate_header`` for the full validation pass (magic,
    version, CRC, payload-length bounds) used by ``codec_api.decode``.
    """
    if len(data) < HEADER_SIZE:
        raise HeaderError(f"Header too short: {len(data)} < {HEADER_SIZE}")

    try:
        magic, version, flags, message_id, correlation_id, deadline_ms, payload_length, _crc = \
            struct.unpack_from(HEADER_STRUCT, data, 0)
    except struct.error as exc:
        raise HeaderError(f"Failed to unpack header: {exc}") from exc

    if magic != MAGIC:
        raise HeaderError(f"Invalid magic: {magic!r} != {MAGIC!r}")
    if version not in SUPPORTED_VERSIONS:
        raise HeaderError(f"Unsupported version: {version}")

    return Header(
        magic=magic,
        version=version,
        flags=flags,
        message_id=message_id,
        correlation_id=correlation_id,
        deadline_ms=deadline_ms,
        payload_length=payload_length,
    )
