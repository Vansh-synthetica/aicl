"""AICL-BIN protocol constants."""
from __future__ import annotations

MAGIC: bytes = b"AICL"
# 56 bytes, matching core-rust's actual wire layout (core-rust/src/opcode.rs
# HEADER_SIZE) and the ISA spec's implied byte diagram — not the spec
# text's "32 bytes" figure, which WIRE_FORMAT_AUDIT.md already flags as a
# typo. See header.py for the exact field-by-field layout.
HEADER_SIZE: int = 56
# core-rust's ISA_VERSION: u16 = 0x0100 (major=1, minor=0), not a bare
# small int — the version field is a packed major/minor pair on the wire.
CURRENT_VERSION: int = 0x0100
SUPPORTED_VERSIONS: frozenset[int] = frozenset({0x0100})
MAX_TLV_VALUE_SIZE: int = 0xFFFFFF
MAX_SYMBOL_SIZE: int = 0xFFFF
MAX_BLOB_SIZE: int = 0xFFFFFFFF
MAX_PACKET_SIZE: int = MAX_TLV_VALUE_SIZE + HEADER_SIZE
MAX_STREAM_CHUNKS: int = 0xFF
CHECKSUM_SIZE: int = 4
TRAILER_MAGIC: int = 0x5CA1AB13
# magic, version, flags, message_id, correlation_id, deadline_ms,
# payload_length, 4 zero padding bytes (part of the header-CRC-covered
# prefix, not a real field), header_crc32. Used to unpack a complete
# 56-byte header in one call.
HEADER_STRUCT: str = ">4sHH16s16sII4xI"
# Same fields, minus the trailing header_crc32 — used to pack the 52-byte
# CRC-covered prefix first (so its CRC32 can be computed), before
# appending the CRC itself as a separate 4 bytes. See header.py. `4x`
# still emits the 4 zero padding bytes on pack (struct.pack writes NULs
# for `x`, no value needed), so this and HEADER_STRUCT stay in lockstep.
HEADER_PREFIX_STRUCT: str = ">4sHH16s16sII4x"
# Header CRC32 covers exactly this many leading bytes (everything up to,
# not including, the CRC field itself) — confirmed directly against
# core-rust/src/codec.rs (`crc32(&data[..52])` on both encode and decode),
# which matches the ISA spec's implied 52-byte scope. An earlier version
# of WIRE_FORMAT_AUDIT.md claimed Rust only covered 28 bytes; that was
# stale/incorrect relative to the current code and has been corrected.
HEADER_CRC_SCOPE: int = 52

# Flag bit values match core-rust's AiclFlags exactly (core-rust/src/
# opcode.rs) — these are NOT the same bit positions AICL-BIN used before
# this rewrite; only REQUEST, RESPONSE, and CANCEL happened to coincide.
FLAG_REQUEST: int = 0x0001
FLAG_RESPONSE: int = 0x0002
FLAG_STREAM_CHUNK: int = 0x0004
FLAG_STREAM_END: int = 0x0008
FLAG_ERROR: int = 0x0010
FLAG_CANCEL: int = 0x0020
FLAG_HEARTBEAT: int = 0x0040
FLAG_COMPRESSED: int = 0x0080
FLAG_ENCRYPTED: int = 0x0100
FLAG_TRACED: int = 0x0200
FLAG_PRIORITY_HIGH: int = 0x0400
FLAG_PRIORITY_LOW: int = 0x0800
FLAG_EXTENDED: int = 0x1000
FLAG_HAS_BUFFER_REF: int = 0x2000
FLAG_FROZEN: int = 0x4000
# 0x8000 is reserved (unused) in core-rust's AiclFlags.

# FLAG_HAS_TRAILER isn't part of core-rust's named AiclFlags set, but its
# bit (0x0100) is exactly what core-rust's own codec.rs checks to gate
# trailer presence at the wire level (`(flags & 0x0100) != 0`) — the same
# bit Rust's AiclFlags calls ENCRYPTED. Both names are correct for what
# they each describe; this isn't a collision to "fix," it's Rust's actual
# wire behavior, which this constant matches on purpose.
FLAG_HAS_TRAILER: int = 0x0100

# Six flag names this codebase used before the rewrite (EVENT, ACK,
# FRAGMENTED, BACKPRESSURE, HAS_EXTENSIONS, EOS) have no equivalent header
# bit in core-rust's AiclFlags — Rust expresses those concepts differently:
#   - EVENT / ACK: via opcode (AiclOpcode::Ack exists; "event" packets are
#     just packets with neither REQUEST nor RESPONSE set), not a flag.
#   - FRAGMENTED / BACKPRESSURE: via a payload TLV (TYPE_CHUNK_INFO /
#     TYPE_BACKPRESSURE) carrying the actual metadata, with STREAM_CHUNK
#     marking that a chunk TLV is present — not a dedicated flag bit.
#   - HAS_EXTENSIONS: renamed to FLAG_EXTENDED above (0x1000), Rust's name
#     for the same bit.
#   - EOS: superseded by FLAG_STREAM_END (0x0008) above, Rust's actual
#     end-of-stream signal.
# Removed rather than aliased to a wrong bit — every caller of the old
# names has been updated to the real replacement (see validation.py,
# codec_view.py, sl/formatter.py).

TYPE_ORIGIN: int = 0x01
TYPE_TARGETS: int = 0x02
TYPE_OPERATION: int = 0x03
TYPE_INTENT: int = 0x04
TYPE_SYMBOLS: int = 0x05
TYPE_RESPONSE_SYMBOLS: int = 0x06
TYPE_METADATA: int = 0x07
TYPE_CONFIDENCE: int = 0x08
TYPE_PRIORITY: int = 0x09
TYPE_DEADLINE: int = 0x0A
TYPE_CAPABILITIES: int = 0x0B
TYPE_QOS: int = 0x0C
TYPE_SECURITY: int = 0x0D
TYPE_TRACE: int = 0x0E
TYPE_CHUNK_INFO: int = 0x0F
TYPE_BLOB_REF: int = 0x10
TYPE_BACKPRESSURE: int = 0x11
TYPE_ERROR_INFO: int = 0x12
TYPE_ACK_INFO: int = 0x13
TYPE_TARGET_CAPABILITIES: int = 0x14
TYPE_SCHEMA_ID: int = 0x15
TYPE_STREAM_ID: int = 0x16
TYPE_PARTIAL_RESULT: int = 0x17
TYPE_MODEL_INVOCATION: int = 0x18
TYPE_TOOL_INVOCATION: int = 0x19
TYPE_CHECKSUM: int = 0x1A
