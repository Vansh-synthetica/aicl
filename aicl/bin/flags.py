"""AICL-BIN packet flags and TLV type codes."""
from __future__ import annotations

# ─── Packet flags (16 bits) ───────────────────────────────────

FLAG_REQUEST: int = 0x0001
"""Packet is a request (expects a response)."""

FLAG_RESPONSE: int = 0x0002
"""Packet is a response."""

FLAG_EVENT: int = 0x0004
"""Packet is a fire-and-forget event."""

FLAG_ERROR: int = 0x0008
"""Packet is an error response."""

FLAG_HEARTBEAT: int = 0x0010
"""Liveness probe packet."""

FLAG_CANCEL: int = 0x0020
"""Cancellation request."""

FLAG_ACK: int = 0x0040
"""Acknowledgement."""

FLAG_STREAM_CHUNK: int = 0x0080
"""Payload is a chunk of a streaming message."""

FLAG_HAS_TRAILER: int = 0x0100
"""A CRC32 trailer follows the payload."""

FLAG_COMPRESSED: int = 0x0200
"""Payload is compressed (lz4/zstd)."""

FLAG_ENCRYPTED: int = 0x0400
"""Payload is encrypted."""

FLAG_FRAGMENTED: int = 0x0800
"""Message is split across multiple packets."""

FLAG_BACKPRESSURE: int = 0x1000
"""Contains backpressure information."""

FLAG_HAS_EXTENSIONS: int = 0x2000
"""Extension TLVs are present."""

FLAG_EOS: int = 0x8000
"""End-of-stream marker."""

# ─── TLV type codes ───────────────────────────────────────────

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
"""Explicit CRC32 checksum override (overrides trailer checksum)."""

# Types 0x20–0xFE: reserved for extensions.
# Type 0xFF: permanently reserved.