"""AICL-BIN typed data structures.

These are lightweight, slots-based classes used by the codec for
encoding requests and decoding responses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "Identity",
    "Symbol",
    "QoS",
    "TraceEntry",
    "ChunkInfo",
    "ErrorInfo",
    "AckInfo",
    "BlobRef",
    "Backpressure",
    "ToolInvocation",
    "ModelInvocation",
    "MetadataEntry",
]


@dataclass(slots=True)
class Identity:
    """A participant in the AICL network.

    id_type : one of IDENTITY_MODULE, IDENTITY_AGENT, IDENTITY_MODEL,
              IDENTITY_RUNTIME, IDENTITY_SYSTEM, IDENTITY_EXTERNAL
    name    : human-readable name of the module/agent
    instance_id : optional instance identifier (for multi-instance modules)
    """

    id_type: int
    name: str
    instance_id: int = 0

    def to_bytes(self) -> bytes:
        """Encode identity to binary.

        Layout: 1 byte id_type | 1 byte name_len | name (UTF-8) | 4 bytes instance_id
        """
        name_bytes = self.name.encode("utf-8")
        if len(name_bytes) > 255:
            raise ValueError(f"Identity name too long: {len(name_bytes)} > 255")
        import struct
        return (
            struct.pack("B", self.id_type)
            + struct.pack("B", len(name_bytes))
            + name_bytes
            + struct.pack(">I", self.instance_id)
        )

    @classmethod
    def from_bytes(cls, data) -> "Identity":
        """Decode identity from binary. Accepts bytes or a memoryview."""
        import struct
        if len(data) < 2:
            raise ValueError("Identity too short")
        id_type = data[0]
        name_len = data[1]
        if len(data) < 2 + name_len + 4:
            raise ValueError("Identity truncated")
        name = bytes(data[2 : 2 + name_len]).decode("utf-8")
        instance_id = struct.unpack_from(">I", data, 2 + name_len)[0]
        return cls(id_type=id_type, name=name, instance_id=instance_id)


@dataclass(slots=True)
class Symbol:
    """A typed operand — the wire's actual unit of data, matching
    core-rust's `Operand` enum.

    tag   : one of the S_* tags in symbol_types.py (S_I8..S_DURATION_MS,
            or a vendor tag >= 0x80 — see symbol_types.S_VENDOR_BASE)
    value : the raw value (type depends on tag) —
            S_I8/I16/I32/I64/U8/U16/U32/U64: int
            S_F32/F64: float
            S_BOOL: bool
            S_STRING: str
            S_BYTES: bytes
            S_UUID: 16 raw bytes
            S_HANDLE: int (u64)
            S_REF: int (u16)
            S_BUF_REF: (id: int, offset: int, length: int)
            S_LIST: list[Symbol]
            S_MAP: dict[str, Symbol]
            S_NULL: None
            S_TS_MS: int (i64)
            S_DURATION_MS: int (u32)
            vendor tag (>= 0x80): raw bytes (this codebase's extension
              mechanism — see operands.py)
    """

    tag: int
    value: object

    def __repr__(self) -> str:
        return f"Symbol(tag=0x{self.tag:02x}, value={self.value!r})"


@dataclass(slots=True)
class QoS:
    """Quality-of-service parameters."""

    priority_class: int
    reliability: int
    ordering: int
    delivery_mode: int
    max_retries: int
    retry_delay_ms: int


@dataclass(slots=True)
class TraceEntry:
    """A single trace/com provenance entry."""

    actor_type: int
    actor_name: str
    action: str
    timestamp_ms: int
    duration_us: int


@dataclass(slots=True)
class ChunkInfo:
    """Chunking metadata for fragmented messages."""

    total_chunks: int
    chunk_index: int
    original_size: int
    chunk_offset: int
    chunk_size: int


@dataclass(slots=True)
class ErrorInfo:
    """Error information carried in error packets."""

    error_code: int
    severity: int
    message: str
    details: Optional[str] = None


@dataclass(slots=True)
class AckInfo:
    """Acknowledgement information."""

    ack_type: str = "ack"
    message: str = ""


@dataclass(slots=True)
class BlobRef:
    """Reference to external/shmem binary data.

    ref_type  : one of REF_SHMEM, REF_FILE, REF_S3, REF_URL, REF_GPU_BUFFER
    size      : total size of referenced data in bytes
    offset    : byte offset into the reference
    identifier: resource identifier (path, URL, shmem name, etc.)
    """

    ref_type: int
    size: int
    offset: int
    identifier: str


@dataclass(slots=True)
class Backpressure:
    """Backpressure information for adaptive flow control."""

    queue_depth: int
    max_queue: int
    drop_reason: int
    retry_after_ms: int


@dataclass(slots=True)
class ToolInvocation:
    """Descriptor for invoking an external tool."""

    tool_name: str
    parameters_json: str
    timeout_ms: int = 5000


@dataclass(slots=True)
class ModelInvocation:
    """Descriptor for invoking an AI model."""

    model_name: str
    task: str
    parameters_json: str
    timeout_ms: int = 5000


@dataclass(slots=True)
class MetadataEntry:
    """A single key-value metadata entry."""

    key: str
    value: str