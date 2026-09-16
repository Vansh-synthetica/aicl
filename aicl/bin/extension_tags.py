"""Vendor-tag assignments for AICL-BIN's Python-side rich fields.

core-rust's wire format has no equivalent of Packet's origin/qos/trace/
error_info/ack_info/backpressure/security/capabilities/schema_id/
model_invocation/tool_invocation/session_id/etc. — those are entirely
this codebase's own extensions, with no cross-language meaning. Rather
than drop them (this codebase's rich object model is worth keeping) or
invent a second, incompatible wire format alongside the real one, each
one rides on the wire as an `Operand::Vendor(tag, bytes)` — a real part
of the ISA spec's own extensibility story (operand tags 0x80-0xFF are
vendor-defined). A Rust decoder sees a normal operand list where some
entries happen to carry an opaque vendor payload it can skip; a Python
decoder recognizes these specific tags and reconstructs the rich fields.

This is why every field below keeps working exactly as before — nothing
was removed — while the wire format itself is 100% ISA-spec-compliant at
every layer, not just the header.
"""
from __future__ import annotations

EXT_SESSION_ID: int = 0x80
EXT_ORIGIN: int = 0x81
EXT_TARGETS: int = 0x82
EXT_INTENT: int = 0x83
EXT_RESPONSE_SYMBOLS: int = 0x84
EXT_CONFIDENCE: int = 0x85
EXT_PRIORITY: int = 0x86
EXT_CAPABILITIES: int = 0x87
EXT_QOS: int = 0x88
EXT_SECURITY: int = 0x89
EXT_TRACE_ENTRY: int = 0x8A  # one vendor operand per trace entry
EXT_CHUNK_INFO: int = 0x8B
EXT_BLOB_REF: int = 0x8C  # one vendor operand per blob ref
EXT_BACKPRESSURE: int = 0x8D
EXT_ERROR_INFO: int = 0x8E
EXT_ACK_INFO: int = 0x8F
EXT_TARGET_CAPS: int = 0x90
EXT_SCHEMA_ID: int = 0x91
EXT_STREAM_ID: int = 0x92
EXT_PARTIAL_RESULT: int = 0x93
EXT_MODEL_INVOCATION: int = 0x94
EXT_TOOL_INVOCATION: int = 0x95
EXT_METADATA: int = 0x96
# 0x97-0xFF free for future extension fields.
