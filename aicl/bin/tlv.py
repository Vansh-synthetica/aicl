"""AICL-BIN TLV (Type-Length-Value) encoding/decoding.

Layout: 1 byte type | 3 bytes big-endian length | N bytes value
Max value size: 16,777,215 bytes (24-bit).
"""
from __future__ import annotations

import struct
from typing import Iterator, Tuple

from aicl.bin.constants import HEADER_SIZE, MAX_TLV_VALUE_SIZE
from aicl.bin.exceptions import TLVError

__all__ = ["encode_tlv", "decode_tlv", "decode_all_tlvs", "iter_tlvs", "pack_tlv_length", "unpack_tlv_length"]

TLV_ENTRY_HEADER_FMT = ">BH"  # 1 byte type + 2 bytes placeholder (we'll use 3-byte length)
# Actually we pack manually: type(1) + length(3) + value(N)


def pack_tlv_length(length: int) -> bytes:
    """Pack a 24-bit length as 3 bytes big-endian."""
    if length > 0xFFFFFF:
        raise TLVError(f"TLV value too large: {length}")
    return struct.pack(">I", length)[1:]  # Strip leading zero byte


def unpack_tlv_length(data: memoryview, pos: int) -> tuple[int, int]:
    """Unpack 24-bit length from pos. Returns (length, new_pos)."""
    length = (data[pos] << 16) | (data[pos + 1] << 8) | data[pos + 2]
    return length, pos + 3


def encode_tlv(tlv_type: int, value: bytes) -> bytes:
    """Encode a single TLV entry. Returns type(1) + len(3) + value."""
    value_bytes = bytes(value)
    length = len(value_bytes)
    header = struct.pack("B", tlv_type) + pack_tlv_length(length)
    return header + value_bytes


def decode_tlv(data: memoryview, pos: int = 0) -> tuple[int, memoryview, int]:
    """Decode one TLV entry. Returns (type, value_view, new_pos)."""
    tlv_type = data[pos]
    length, pos = unpack_tlv_length(data, pos + 1)
    end = pos + length
    if end > len(data):
        raise TLVError(f"Truncated TLV (need {length} at {pos})")
    value = memoryview(data)[pos:end]
    return tlv_type, value, end


def iter_tlvs(data: memoryview, pos: int = 0) -> Iterator[Tuple[int, memoryview, int]]:
    """Iterate over TLV entries, yielding (type, value, end_pos)."""
    while pos < len(data):
        tlv_type, value, end = decode_tlv(data, pos)
        yield tlv_type, value, end
        pos = end


def decode_all_tlvs(data: memoryview) -> list[tuple[int, bytes]]:
    """Decode all TLV entries into a list of (type, bytes)."""
    result: list[tuple[int, bytes]] = []
    pos = 0
    while pos < len(data):
        tlv_type, value, pos = decode_tlv(data, pos)
        result.append((tlv_type, value.tobytes()))
    return result


def encode_tlvs(tlvs: list[tuple[int, bytes]]) -> bytes:
    """Encode a list of TLV entries. Returns concatenated bytes."""
    return b"".join(encode_tlv(t, v) for t, v in tlvs)