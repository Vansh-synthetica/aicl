from __future__ import annotations
import struct, uuid
from dataclasses import dataclass, field
from typing import Optional, List
import aicl.bin.constants as C
import aicl.bin.extension_tags as X
from aicl.bin.operands import encode_symbol
from aicl.bin.varint import encode_varint
from aicl.bin.exceptions import EncodeError
from aicl.bin.types import Identity, Symbol, QoS, TraceEntry, ChunkInfo, ErrorInfo, AckInfo, BlobRef, Backpressure, ModelInvocation, ToolInvocation
from aicl.bin.symbol_types import S_STRING


@dataclass(slots=True)
class Packet:
    version: int = C.CURRENT_VERSION
    flags: int = C.FLAG_REQUEST
    session_id: Optional[bytes] = None
    message_id: Optional[bytes] = None
    correlation_id: Optional[bytes] = None
    origin: Optional[Identity] = None
    targets: list = field(default_factory=list)
    operation: int = 0
    intent: str = ""
    symbols: list = field(default_factory=list)
    response_symbols: list = field(default_factory=list)
    confidence: float = 1.0
    priority: int = 128
    deadline_ms: int = 0
    capabilities: list = field(default_factory=list)
    qos: Optional[QoS] = None
    security: Optional[bytes] = None
    trace: list = field(default_factory=list)
    chunk_info: Optional[ChunkInfo] = None
    blob_refs: list = field(default_factory=list)
    backpressure: Optional[Backpressure] = None
    error_info: Optional[ErrorInfo] = None
    ack_info: Optional[AckInfo] = None
    target_caps: list = field(default_factory=list)
    schema_id: str = ""
    stream_id: Optional[bytes] = None
    partial_result: Optional[bytes] = None
    model_invocation: Optional[ModelInvocation] = None
    tool_invocation: Optional[ToolInvocation] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.session_id is None: self.session_id = uuid.uuid4().bytes
        if self.message_id is None: self.message_id = uuid.uuid4().bytes
        if self.correlation_id is None: self.correlation_id = b"\x00" * 16
        for name, bid in [("session_id", self.session_id), ("message_id", self.message_id), ("correlation_id", self.correlation_id)]:
            if len(bid) != 16: raise EncodeError(f"{name} must be 16 bytes")

    def build_payload(self) -> bytes:
        """Build the wire payload: opcode(1) + varint(operand_count) +
        operands — matching core-rust's AiclCodec::encode_into exactly.

        `self.symbols` are the "core" operands, on the wire exactly as
        given (this is what a Rust decoder would recognize). Every other
        rich field on this Packet with no core-rust equivalent rides
        along as an additional `Operand::Vendor(tag, bytes)` operand,
        appended after the core ones — see extension_tags.py.
        """
        operands: List[Symbol] = list(self.symbols)
        self._append_extensions(operands)

        out = bytearray()
        out.append(self.operation & 0xFF)
        out += encode_varint(len(operands))
        for op in operands:
            out += encode_symbol(op)
        return bytes(out)

    def _append_extensions(self, operands: List[Symbol]) -> None:
        def ext(tag: int, raw: bytes) -> None:
            operands.append(Symbol(tag=tag, value=raw))

        if self.session_id:
            ext(X.EXT_SESSION_ID, bytes(self.session_id))
        if self.origin:
            ext(X.EXT_ORIGIN, self.origin.to_bytes())
        if self.targets:
            ext(X.EXT_TARGETS, b",".join(t.encode() for t in self.targets))
        if self.intent:
            ext(X.EXT_INTENT, self.intent.encode())
        if self.response_symbols:
            ext(X.EXT_RESPONSE_SYMBOLS, b"".join(encode_symbol(s) for s in self.response_symbols))
        if self.confidence != 1.0:
            ext(X.EXT_CONFIDENCE, struct.pack(">d", self.confidence))
        if self.priority != 128:
            ext(X.EXT_PRIORITY, struct.pack("B", self.priority))
        if self.capabilities:
            ext(X.EXT_CAPABILITIES, b",".join(c.encode() for c in self.capabilities))
        if self.qos:
            q = self.qos
            ext(X.EXT_QOS, struct.pack(">BBBBII", q.priority_class, q.reliability, q.ordering, q.delivery_mode, q.max_retries, q.retry_delay_ms))
        if self.security:
            ext(X.EXT_SECURITY, self.security)
        for e in self.trace:
            an, ac = e.actor_name.encode(), e.action.encode()
            ent = struct.pack("BBB", e.actor_type, len(an), len(ac)) + an + ac + struct.pack(">q", e.timestamp_ms) + struct.pack(">i", e.duration_us)
            ext(X.EXT_TRACE_ENTRY, ent)
        if self.chunk_info:
            c = self.chunk_info
            ext(X.EXT_CHUNK_INFO, struct.pack(">BBI", c.total_chunks, c.chunk_index, c.original_size) + struct.pack(">II", c.chunk_offset, c.chunk_size))
        for br in self.blob_refs:
            ib = br.identifier.encode()
            ext(X.EXT_BLOB_REF, struct.pack("BBI", br.ref_type, len(ib), br.size) + struct.pack(">I", br.offset) + ib)
        if self.backpressure:
            bp = self.backpressure
            ext(X.EXT_BACKPRESSURE, struct.pack(">IIHH", bp.queue_depth, bp.max_queue, bp.drop_reason, bp.retry_after_ms))
        if self.error_info:
            e = self.error_info
            mb, db = e.message.encode(), (e.details or "").encode()
            ext(X.EXT_ERROR_INFO, struct.pack(">HH", e.error_code, e.severity) + struct.pack("B", len(mb)) + mb + struct.pack(">H", len(db)) + db)
        if self.ack_info:
            ext(X.EXT_ACK_INFO, struct.pack("B", 0) + self.ack_info.message.encode())
        if self.target_caps:
            ext(X.EXT_TARGET_CAPS, b",".join(c.encode() for c in self.target_caps))
        if self.schema_id:
            ext(X.EXT_SCHEMA_ID, self.schema_id.encode())
        if self.stream_id:
            ext(X.EXT_STREAM_ID, bytes(self.stream_id))
        if self.partial_result:
            ext(X.EXT_PARTIAL_RESULT, self.partial_result)
        if self.model_invocation:
            m = self.model_invocation
            nb, tb, pb = m.model_name.encode(), m.task.encode(), m.parameters_json.encode()
            ext(X.EXT_MODEL_INVOCATION, struct.pack(">BBB", len(nb), len(tb), len(pb)) + nb + tb + pb + struct.pack(">I", m.timeout_ms))
        if self.tool_invocation:
            ti = self.tool_invocation
            nb, pb = ti.tool_name.encode(), ti.parameters_json.encode()
            ext(X.EXT_TOOL_INVOCATION, struct.pack(">BB", len(nb), len(pb)) + nb + pb + struct.pack(">I", ti.timeout_ms))
        if self.metadata:
            mp = []
            for k, v in self.metadata.items():
                kb, vb = k.encode(), str(v).encode()
                mp.append(struct.pack("B", len(kb)) + kb + struct.pack(">H", len(vb)) + vb)
            ext(X.EXT_METADATA, b"".join(mp))
