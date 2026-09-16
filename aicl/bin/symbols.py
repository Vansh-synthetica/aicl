"""AICL-BIN symbol encoding/decoding.

Symbol layout: 1 byte tag | 1/3 bytes length | N bytes value

Supports: S_STRING, S_NUMBER, S_INTEGER, S_BOOLEAN, S_TAG, S_KEY,
          S_VECTOR, S_REFERENCE, S_JSON, S_DATETIME, S_UUID, S_NULL, S_BLOB
"""
from __future__ import annotations

import struct
from typing import Iterator

from aicl.bin.symbol_types import (
    S_STRING, S_NUMBER, S_INTEGER, S_BOOLEAN, S_TAG,
    S_KEY, S_VECTOR, S_REFERENCE, S_JSON, S_DATETIME,
    S_UUID, S_NULL, S_BLOB,
)
from aicl.bin.exceptions import SymbolError
from aicl.bin.types import Symbol

__all__ = ["encode_symbol", "decode_symbol", "encode_symbols", "decode_symbols"]


# ─── Length packing ────────────────────────────────────────────

def _pack_length(length: int) -> bytes:
    if length <= 0xFF:
        return struct.pack("B", length)
    return bytes([0xFF]) + struct.pack(">H", length)


def _unpack_length(data: memoryview, pos: int) -> tuple[int, int]:
    first = data[pos]
    pos += 1
    if first == 0xFF:
        return struct.unpack_from(">H", data, pos)[0], pos + 2
    return first, pos


# ─── Value encoding ────────────────────────────────────────────

def _encode_value(tag: int, value) -> bytes:
    if tag in (S_STRING, S_TAG, S_KEY, S_REFERENCE, S_JSON):
        return value.encode("utf-8")
    if tag == S_NUMBER:
        return struct.pack(">d", float(value))
    if tag == S_INTEGER:
        return struct.pack(">q", int(value))
    if tag == S_BOOLEAN:
        return struct.pack("B", 1 if value else 0)
    if tag == S_VECTOR:
        sub = b"".join(encode_symbol(s) for s in value)
        return struct.pack(">H", len(value)) + sub
    if tag == S_DATETIME:
        return struct.pack(">qq", int(value[0]), int(value[1]))
    if tag == S_UUID:
        return bytes(value)
    if tag == S_NULL:
        return b""
    if tag == S_BLOB:
        bval = bytes(value)
        return struct.pack(">I", len(bval)) + bval
    raise SymbolError(f"Unknown symbol tag: 0x{tag:02x}")


def encode_symbol(symbol: Symbol) -> bytes:
    """Encode a single Symbol to bytes."""
    raw = _encode_value(symbol.tag, symbol.value)
    return struct.pack("B", symbol.tag) + _pack_length(len(raw)) + raw


def encode_symbols(symbols) -> bytes:
    """Encode a list of Symbols to bytes."""
    return b"".join(encode_symbol(s) for s in symbols)


# ─── Value decoding ──────────────────────────────────────────

def _decode_value(tag: int, length: int, data: memoryview, pos: int):
    end = pos + length
    if end > len(data):
        raise SymbolError(f"Truncated symbol (need {length} at {pos})")
    v = data[pos:end]

    if tag == S_STRING:
        return v.tobytes().decode("utf-8"), end
    if tag == S_NUMBER:
        return struct.unpack_from(">d", v, 0)[0], end
    if tag == S_INTEGER:
        return struct.unpack_from(">q", v, 0)[0], end
    if tag == S_BOOLEAN:
        return bool(v[0]), end
    if tag in (S_TAG, S_KEY, S_REFERENCE, S_JSON):
        return v.tobytes().decode("utf-8"), end
    if tag == S_VECTOR:
        count = struct.unpack_from(">H", v, 0)[0]
        syms, _ = decode_symbols(v[2:])
        return syms, end
    if tag == S_DATETIME:
        ms = struct.unpack_from(">q", v, 0)[0]
        ns = struct.unpack_from(">q", v, 8)[0]
        return (ms, ns), end
    if tag == S_UUID:
        return v.tobytes(), end
    if tag == S_NULL:
        return None, end
    if tag == S_BLOB:
        ilen = struct.unpack_from(">I", v, 0)[0]
        return v[4:4 + ilen].tobytes(), end
    raise SymbolError(f"Unknown symbol tag: 0x{tag:02x}")


def decode_symbol(data: memoryview, pos: int = 0) -> tuple[Symbol, int]:
    """Decode one Symbol. Returns (Symbol, new_pos)."""
    tag = data[pos]; pos += 1
    length, pos = _unpack_length(data, pos)
    value, pos = _decode_value(tag, length, data, pos)
    return Symbol(tag=tag, value=value), pos


def decode_symbols(data: memoryview, pos: int = 0) -> tuple[list[Symbol], int]:
    """Decode all symbols. Returns (list, new_pos)."""
    result: list[Symbol] = []
    while pos < len(data):
        sym, pos = decode_symbol(data, pos)
        result.append(sym)
    return result, pos


def iter_symbols(data: memoryview, pos: int = 0) -> Iterator[Symbol]:
    """Iterate over symbols without creating a list."""
    while pos < len(data):
        sym, pos = decode_symbol(data, pos)
        yield sym
