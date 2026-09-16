"""LEB128 varint encode/decode — matches core-rust's codec.rs exactly.

Used for operand counts, string/bytes/list/map lengths in the new
opcode + operand payload structure (replacing the old TLV length
prefixes). Continuation bit convention: set on every byte EXCEPT the
last one — the same bug fixed in core-rust's encode_varint this session
(it had the continuation bit backwards, silently truncating any value
>= 128) applies here too if gotten wrong, so this is deliberately written
to match Rust's corrected version byte for byte.
"""
from __future__ import annotations

from aicl.bin.exceptions import SymbolError

__all__ = ["encode_varint", "decode_varint"]

_MAX_BYTES = 4  # matches core-rust's decode_varint 4-byte cap


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise SymbolError(f"varint value must be non-negative, got {value}")
    out = bytearray()
    for _ in range(_MAX_BYTES):
        more = value > 0x7F
        out.append((value & 0x7F) | (0x80 if more else 0))
        if not more:
            return bytes(out)
        value >>= 7
    return bytes(out)


def decode_varint(data, pos: int = 0) -> tuple[int, int]:
    """Decode one varint from `data` starting at `pos`.

    Returns (value, new_pos). Raises SymbolError on overflow (>4 bytes) or
    truncation (ran out of bytes before the continuation bit cleared).
    """
    value = 0
    shift = 0
    for i in range(_MAX_BYTES):
        if pos + i >= len(data):
            raise SymbolError("varint truncated")
        byte = data[pos + i]
        value |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return value, pos + i + 1
        shift += 7
    raise SymbolError("varint > 4 bytes")
