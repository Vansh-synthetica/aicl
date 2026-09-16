"""AICL-BIN operand type tags — matches core-rust's OperandType exactly
(core-rust/src/operand.rs).

The pre-rewrite version of this file defined a different 13-tag set
(S_STRING=0x01, S_NUMBER=0x02, ... S_BLOB=0x0D) with no integer-width or
float-width distinction and no List/Map/Handle/Ref/BufRef/TsMs/
DurationMs — see WIRE_FORMAT_AUDIT.md for the full history. These are the
real wire-format operand tags. Names kept as `S_*` for source
compatibility with existing imports.
"""
from __future__ import annotations

S_I8: int = 0x01
S_I16: int = 0x02
S_I32: int = 0x03
S_I64: int = 0x04
S_U8: int = 0x05
S_U16: int = 0x06
S_U32: int = 0x07
S_U64: int = 0x08
S_F32: int = 0x09
S_F64: int = 0x0A
# 0x0B-0x0F unassigned
S_BOOL: int = 0x10
S_STRING: int = 0x11
S_BYTES: int = 0x12
S_UUID: int = 0x13
S_HANDLE: int = 0x14
S_REF: int = 0x15
S_BUF_REF: int = 0x16
S_LIST: int = 0x17
S_MAP: int = 0x18
S_NULL: int = 0x19
S_TS_MS: int = 0x1A
S_DURATION_MS: int = 0x1B
# 0x1C-0x7F unassigned
S_VENDOR_BASE: int = 0x80
"""Vendor-defined operand tags occupy 0x80-0xFF. Used by this codebase's
extension mechanism (see operands.py) to carry Python-only rich fields
(origin, qos, trace, error_info, etc.) that have no equivalent in
core-rust's operand set, in a form Rust can safely skip without choking
on — real cross-language interop for the core, honest extension for the
rest. See EXTENSION_TAGS below for the specific tag assignments."""

SYMBOL_TYPE_NAMES: dict[int, str] = {
    S_I8: "I8", S_I16: "I16", S_I32: "I32", S_I64: "I64",
    S_U8: "U8", S_U16: "U16", S_U32: "U32", S_U64: "U64",
    S_F32: "F32", S_F64: "F64",
    S_BOOL: "BOOL", S_STRING: "STR", S_BYTES: "BYTES", S_UUID: "UUID",
    S_HANDLE: "HANDLE", S_REF: "REF", S_BUF_REF: "BUF_REF",
    S_LIST: "LIST", S_MAP: "MAP", S_NULL: "NULL",
    S_TS_MS: "TS_MS", S_DURATION_MS: "DURATION_MS",
}


def is_vendor(tag: int) -> bool:
    return 0x80 <= tag <= 0xFF
