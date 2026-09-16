"""AICL-BIN operation codes — matches core-rust's AiclOpcode exactly
(core-rust/src/opcode.rs), which is itself the ISA spec's taxonomy.

The pre-rewrite version of this file defined a completely different set
of opcodes (OP_CLS=0x03, OP_GEN=0x04, etc., a TLV-payload-only concept
with no Rust equivalent) — see WIRE_FORMAT_AUDIT.md for the full history.
These are the real wire-format opcode values.
"""
from __future__ import annotations

# System 0x00-0x0F
OP_NOP: int = 0x00
OP_HELLO: int = 0x01
OP_GOODBYE: int = 0x02
OP_DISCOVER: int = 0x03
OP_PING: int = 0x04
OP_PONG: int = 0x05
OP_ACK: int = 0x06
OP_NAK: int = 0x07
OP_ERROR: int = 0x08
OP_CANCEL: int = 0x09
OP_VERSION: int = 0x0A
# 0x0B-0x0F unassigned

# Call/Return 0x10-0x1F
OP_CALL: int = 0x10
OP_RETURN: int = 0x11
OP_STREAM: int = 0x12
OP_STREAM_END: int = 0x13
# 0x14-0x1F unassigned

# Memory 0x20-0x2F
OP_MEMORY_READ: int = 0x20
OP_MEMORY_WRITE: int = 0x21
OP_MEMORY_DELETE: int = 0x22
OP_INDEX_QUERY: int = 0x23
OP_INDEX_UPSERT: int = 0x24
# 0x25-0x2F unassigned

# Capability 0x30-0x3F
OP_CAPABILITY_ADVERTISE: int = 0x30
OP_CAPABILITY_WITHDRAW: int = 0x31
OP_CAPABILITY_QUERY: int = 0x32
# 0x33-0x3F unassigned

# AI primitives 0x40-0x4F
OP_MODEL_CALL: int = 0x40
OP_TOOL_CALL: int = 0x41
OP_EMBED: int = 0x42
OP_CLASSIFY: int = 0x43
OP_REASON: int = 0x44
OP_RETRIEVE: int = 0x45
OP_EXECUTE: int = 0x46
# 0x47-0x4F unassigned

# Tracing 0x50-0x5F
OP_TRACE: int = 0x50
OP_STATS: int = 0x51
OP_HEALTH: int = 0x52
# 0x53-0x5F unassigned

# Buffer 0x60-0x6F
OP_BUFFER_REF: int = 0x60
OP_BUFFER_RELEASE: int = 0x61
OP_BUFFER_SHARE: int = 0x62
# 0x63-0xEF unassigned

# Vendor-defined: 0xF0-0xFF
OP_VENDOR_BASE: int = 0xF0

OPERATION_NAMES: dict[int, str] = {
    OP_NOP: "NOP",
    OP_HELLO: "HELLO",
    OP_GOODBYE: "GOODBYE",
    OP_DISCOVER: "DISCOVER",
    OP_PING: "PING",
    OP_PONG: "PONG",
    OP_ACK: "ACK",
    OP_NAK: "NAK",
    OP_ERROR: "ERROR",
    OP_CANCEL: "CANCEL",
    OP_VERSION: "VERSION",
    OP_CALL: "CALL",
    OP_RETURN: "RETURN",
    OP_STREAM: "STREAM",
    OP_STREAM_END: "STREAM_END",
    OP_MEMORY_READ: "MEMORY_READ",
    OP_MEMORY_WRITE: "MEMORY_WRITE",
    OP_MEMORY_DELETE: "MEMORY_DELETE",
    OP_INDEX_QUERY: "INDEX_QUERY",
    OP_INDEX_UPSERT: "INDEX_UPSERT",
    OP_CAPABILITY_ADVERTISE: "CAPABILITY_ADVERTISE",
    OP_CAPABILITY_WITHDRAW: "CAPABILITY_WITHDRAW",
    OP_CAPABILITY_QUERY: "CAPABILITY_QUERY",
    OP_MODEL_CALL: "MODEL_CALL",
    OP_TOOL_CALL: "TOOL_CALL",
    OP_EMBED: "EMBED",
    OP_CLASSIFY: "CLASSIFY",
    OP_REASON: "REASON",
    OP_RETRIEVE: "RETRIEVE",
    OP_EXECUTE: "EXECUTE",
    OP_TRACE: "TRACE",
    OP_STATS: "STATS",
    OP_HEALTH: "HEALTH",
    OP_BUFFER_REF: "BUFFER_REF",
    OP_BUFFER_RELEASE: "BUFFER_RELEASE",
    OP_BUFFER_SHARE: "BUFFER_SHARE",
}


def is_vendor(opcode: int) -> bool:
    """True for opcodes in the vendor-defined range (0xF0-0xFF)."""
    return 0xF0 <= opcode <= 0xFF


def is_assigned(opcode: int) -> bool:
    """True if `opcode` is a real, named opcode or in the vendor range.

    False for unassigned gaps (e.g. 0x0B-0x0F) — per ISA §8 step 4, an
    unassigned opcode should be rejected at decode time, not silently
    accepted. See codec_api.decode.
    """
    return opcode in OPERATION_NAMES or is_vendor(opcode)


# Convenience categories, updated for the real opcode set.
REQUEST_OPS: frozenset[int] = frozenset({
    OP_HELLO, OP_DISCOVER, OP_PING, OP_CALL, OP_STREAM,
    OP_MEMORY_READ, OP_MEMORY_WRITE, OP_MEMORY_DELETE,
    OP_INDEX_QUERY, OP_INDEX_UPSERT,
    OP_CAPABILITY_ADVERTISE, OP_CAPABILITY_WITHDRAW, OP_CAPABILITY_QUERY,
    OP_MODEL_CALL, OP_TOOL_CALL, OP_EMBED, OP_CLASSIFY, OP_REASON,
    OP_RETRIEVE, OP_EXECUTE, OP_TRACE, OP_STATS, OP_HEALTH,
    OP_BUFFER_REF, OP_BUFFER_SHARE,
})

RESPONSE_OPS: frozenset[int] = frozenset({
    OP_GOODBYE, OP_PONG, OP_ACK, OP_NAK, OP_ERROR, OP_RETURN,
    OP_STREAM_END, OP_VERSION, OP_BUFFER_RELEASE,
})

SYSTEM_OPS: frozenset[int] = frozenset({
    OP_NOP, OP_HELLO, OP_GOODBYE, OP_DISCOVER, OP_PING, OP_PONG,
    OP_ACK, OP_NAK, OP_ERROR, OP_CANCEL, OP_VERSION,
})
