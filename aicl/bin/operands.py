"""AICL-BIN operand encoding/decoding — matches core-rust's
encode_operand/decode_operand exactly (core-rust/src/codec.rs).

Layout: 1 byte tag, then a tag-dependent value:
  - fixed-width types (I8..F64, BOOL, UUID, HANDLE, REF, TS_MS,
    DURATION_MS): raw big-endian bytes, no length prefix.
  - STR/BYTES: varint length prefix + raw bytes.
  - LIST: varint count + that many recursively-encoded operands.
  - MAP: varint count, then for each entry: varint key length + UTF-8
    key bytes + one recursively-encoded operand value.
  - BUF_REF: u64 id + u32 offset + u32 length, fixed width.
  - NULL: no value bytes at all.
  - Vendor tags (>= 0x80): varint length + raw bytes (this codebase's
    extension mechanism for Python-only rich fields with no core-rust
    equivalent — see symbol_types.py).

This replaces the old TLV-nested-symbol format (symbols.py, pre-rewrite)
— see WIRE_FORMAT_AUDIT.md for the full history.
"""
from __future__ import annotations

import struct
from typing import Iterator

from aicl.bin.symbol_types import (
    S_I8, S_I16, S_I32, S_I64, S_U8, S_U16, S_U32, S_U64, S_F32, S_F64,
    S_BOOL, S_STRING, S_BYTES, S_UUID, S_HANDLE, S_REF, S_BUF_REF,
    S_LIST, S_MAP, S_NULL, S_TS_MS, S_DURATION_MS,
    is_vendor,
)
from aicl.bin.varint import encode_varint, decode_varint
from aicl.bin.exceptions import SymbolError
from aicl.bin.types import Symbol

__all__ = ["encode_symbol", "decode_symbol", "encode_symbols", "decode_symbols", "iter_symbols"]

_FIXED_STRUCT: dict[int, str] = {
    S_I8: ">b", S_I16: ">h", S_I32: ">i", S_I64: ">q",
    S_U8: ">B", S_U16: ">H", S_U32: ">I", S_U64: ">Q",
    S_F32: ">f", S_F64: ">d",
    S_TS_MS: ">q", S_DURATION_MS: ">I",
}


def encode_symbol(symbol: Symbol) -> bytes:
    """Encode a single operand (tag + value) to wire bytes."""
    tag = symbol.tag
    value = symbol.value
    out = bytearray([tag])

    if tag in _FIXED_STRUCT:
        out += struct.pack(_FIXED_STRUCT[tag], value)
    elif tag == S_BOOL:
        out.append(1 if value else 0)
    elif tag == S_STRING:
        raw = value.encode("utf-8")
        out += encode_varint(len(raw))
        out += raw
    elif tag == S_BYTES:
        raw = bytes(value)
        out += encode_varint(len(raw))
        out += raw
    elif tag == S_UUID:
        raw = bytes(value)
        if len(raw) != 16:
            raise SymbolError(f"UUID operand must be 16 bytes, got {len(raw)}")
        out += raw
    elif tag == S_HANDLE:
        out += struct.pack(">Q", value)
    elif tag == S_REF:
        out += struct.pack(">H", value)
    elif tag == S_BUF_REF:
        buf_id, offset, length = value
        out += struct.pack(">QII", buf_id, offset, length)
    elif tag == S_LIST:
        out += encode_varint(len(value))
        for item in value:
            out += encode_symbol(item)
    elif tag == S_MAP:
        out += encode_varint(len(value))
        for key, item in value.items():
            kb = key.encode("utf-8")
            out += encode_varint(len(kb))
            out += kb
            out += encode_symbol(item)
    elif tag == S_NULL:
        pass
    elif is_vendor(tag):
        raw = bytes(value)
        out += encode_varint(len(raw))
        out += raw
    else:
        raise SymbolError(f"Unknown operand tag: 0x{tag:02x}")

    return bytes(out)


def decode_symbol(data, pos: int = 0) -> tuple[Symbol, int]:
    """Decode one operand. Returns (Symbol, new_pos)."""
    if pos >= len(data):
        raise SymbolError("operand: no tag byte")
    tag = data[pos]
    pos += 1

    if tag in _FIXED_STRUCT:
        fmt = _FIXED_STRUCT[tag]
        size = struct.calcsize(fmt)
        if pos + size > len(data):
            raise SymbolError(f"operand 0x{tag:02x}: need {size} bytes")
        value = struct.unpack_from(fmt, data, pos)[0]
        pos += size
    elif tag == S_BOOL:
        if pos >= len(data):
            raise SymbolError("operand BOOL: need 1 byte")
        raw = data[pos]
        if raw > 1:
            raise SymbolError(f"operand BOOL: invalid value {raw}")
        value = bool(raw)
        pos += 1
    elif tag in (S_STRING, S_BYTES):
        length, pos = decode_varint(data, pos)
        end = pos + length
        if end > len(data):
            raise SymbolError(f"operand 0x{tag:02x}: truncated (need {length} at {pos})")
        raw = bytes(data[pos:end])
        value = raw.decode("utf-8") if tag == S_STRING else raw
        pos = end
    elif tag == S_UUID:
        if pos + 16 > len(data):
            raise SymbolError("operand UUID: need 16 bytes")
        value = bytes(data[pos:pos + 16])
        pos += 16
    elif tag == S_HANDLE:
        if pos + 8 > len(data):
            raise SymbolError("operand HANDLE: need 8 bytes")
        value = struct.unpack_from(">Q", data, pos)[0]
        pos += 8
    elif tag == S_REF:
        if pos + 2 > len(data):
            raise SymbolError("operand REF: need 2 bytes")
        value = struct.unpack_from(">H", data, pos)[0]
        pos += 2
    elif tag == S_BUF_REF:
        if pos + 16 > len(data):
            raise SymbolError("operand BUF_REF: need 16 bytes")
        buf_id, offset, length = struct.unpack_from(">QII", data, pos)
        value = (buf_id, offset, length)
        pos += 16
    elif tag == S_LIST:
        count, pos = decode_varint(data, pos)
        items = []
        for _ in range(count):
            item, pos = decode_symbol(data, pos)
            items.append(item)
        value = items
    elif tag == S_MAP:
        count, pos = decode_varint(data, pos)
        result: dict[str, Symbol] = {}
        for _ in range(count):
            klen, pos = decode_varint(data, pos)
            kend = pos + klen
            if kend > len(data):
                raise SymbolError(f"operand MAP: truncated key (need {klen} at {pos})")
            key = bytes(data[pos:kend]).decode("utf-8")
            pos = kend
            item, pos = decode_symbol(data, pos)
            result[key] = item
        value = result
    elif tag == S_NULL:
        value = None
    elif is_vendor(tag):
        length, pos = decode_varint(data, pos)
        end = pos + length
        if end > len(data):
            raise SymbolError(f"vendor operand 0x{tag:02x}: truncated (need {length} at {pos})")
        value = bytes(data[pos:end])
        pos = end
    else:
        raise SymbolError(f"Unknown operand tag: 0x{tag:02x}")

    return Symbol(tag=tag, value=value), pos


def encode_symbols(symbols) -> bytes:
    """Encode a bare sequence of operands back to back (no count prefix —
    used where the caller already knows/encodes the count separately,
    e.g. the top-level packet payload)."""
    return b"".join(encode_symbol(s) for s in symbols)


def decode_symbols(data, pos: int = 0) -> tuple[list[Symbol], int]:
    """Decode operands until `data` is exhausted."""
    result: list[Symbol] = []
    while pos < len(data):
        sym, pos = decode_symbol(data, pos)
        result.append(sym)
    return result, pos


def iter_symbols(data, pos: int = 0) -> Iterator[Symbol]:
    """Iterate over operands without building a list."""
    while pos < len(data):
        sym, pos = decode_symbol(data, pos)
        yield sym
