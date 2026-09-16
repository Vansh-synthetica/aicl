from __future__ import annotations
import struct
from typing import Optional, List, Tuple
import aicl.bin.constants as C
import aicl.bin.extension_tags as X
import aicl.bin.header as H
from aicl.bin.operands import decode_symbol
from aicl.bin.varint import decode_varint
from aicl.bin.symbol_types import S_STRING, is_vendor
from aicl.bin.types import Identity, Symbol, QoS, Backpressure, ErrorInfo


class PacketView:
    __slots__ = ("_raw", "_hdr_end", "_pay_end", "_hdr", "_operation",
                 "_symbols", "_extensions")

    def __init__(self, raw, hdr_end, pay_end):
        self._raw = raw if isinstance(raw, memoryview) else memoryview(raw)
        self._hdr_end, self._pay_end = hdr_end, pay_end
        self._hdr = H.unpack_header(self._raw[:C.HEADER_SIZE])

        payload = self._raw[self._hdr_end:self._pay_end]
        self._operation = payload[0] if len(payload) else 0
        self._symbols: List[Symbol] = []
        self._extensions: dict[int, list] = {}
        if len(payload) > 1:
            count, pos = decode_varint(payload, 1)
            for _ in range(count):
                sym, pos = decode_symbol(payload, pos)
                if is_vendor(sym.tag):
                    self._extensions.setdefault(sym.tag, []).append(sym.value)
                else:
                    self._symbols.append(sym)

    @property
    def raw(self):
        return self._raw
    @property
    def version(self):
        return self._hdr.version
    @property
    def flags(self):
        return self._hdr.flags
    @property
    def message_id(self):
        return self._hdr.message_id
    @property
    def correlation_id(self):
        return self._hdr.correlation_id
    @property
    def deadline_ms(self):
        return self._hdr.deadline_ms
    @property
    def payload_length(self):
        return self._hdr.payload_length
    @property
    def has_trailer(self):
        return bool(self.flags & C.FLAG_HAS_TRAILER)
    @property
    def is_request(self):
        return bool(self.flags & C.FLAG_REQUEST)
    @property
    def is_response(self):
        return bool(self.flags & C.FLAG_RESPONSE)
    @property
    def is_error(self):
        return bool(self.flags & C.FLAG_ERROR)
    @property
    def is_stream_chunk(self):
        return bool(self.flags & C.FLAG_STREAM_CHUNK)
    @property
    def is_stream_end(self):
        return bool(self.flags & C.FLAG_STREAM_END)

    @property
    def operation(self):
        return self._operation

    @property
    def symbols(self):
        """The "core" operands — everything on the wire that isn't one of
        this codebase's vendor-tagged extension fields (see the
        properties below, and extension_tags.py)."""
        return self._symbols

    def _ext_one(self, tag: int):
        vals = self._extensions.get(tag)
        return vals[0] if vals else None

    def _ext_all(self, tag: int) -> list:
        return self._extensions.get(tag, [])

    @property
    def session_id(self):
        return self._ext_one(X.EXT_SESSION_ID)

    @property
    def origin(self):
        v = self._ext_one(X.EXT_ORIGIN)
        return Identity.from_bytes(v) if v else None

    @property
    def targets(self):
        v = self._ext_one(X.EXT_TARGETS)
        return [t.decode() for t in v.split(b",") if t] if v else []

    @property
    def intent(self):
        v = self._ext_one(X.EXT_INTENT)
        return v.decode() if v else ""

    @property
    def response_symbols(self):
        v = self._ext_one(X.EXT_RESPONSE_SYMBOLS)
        if not v:
            return []
        syms, _ = _decode_symbol_seq(v)
        return syms

    @property
    def confidence(self):
        v = self._ext_one(X.EXT_CONFIDENCE)
        return struct.unpack_from(">d", v, 0)[0] if v else 1.0

    @property
    def priority(self):
        v = self._ext_one(X.EXT_PRIORITY)
        return v[0] if v else 128

    @property
    def capabilities(self):
        v = self._ext_one(X.EXT_CAPABILITIES)
        return [c.decode() for c in v.split(b",") if c] if v else []

    @property
    def qos(self):
        v = self._ext_one(X.EXT_QOS)
        if not v or len(v) < 12:
            return None
        return QoS(v[0], v[1], v[2], v[3],
                   struct.unpack_from(">I", v, 4)[0],
                   struct.unpack_from(">I", v, 8)[0])

    @property
    def security(self):
        return self._ext_one(X.EXT_SECURITY)

    @property
    def trace(self):
        from aicl.bin.types import TraceEntry
        out = []
        for d in self._ext_all(X.EXT_TRACE_ENTRY):
            actor_type, nl, al = d[0], d[1], d[2]
            off = 3
            actor_name = d[off:off + nl].decode(); off += nl
            action = d[off:off + al].decode(); off += al
            ts = struct.unpack_from(">q", d, off)[0]; off += 8
            dur = struct.unpack_from(">i", d, off)[0]
            out.append(TraceEntry(actor_type, actor_name, action, ts, dur))
        return out

    @property
    def chunk_info(self):
        from aicl.bin.types import ChunkInfo
        v = self._ext_one(X.EXT_CHUNK_INFO)
        if not v or len(v) < 14:
            return None
        total_chunks, chunk_index = v[0], v[1]
        original_size = struct.unpack_from(">I", v, 2)[0]
        chunk_offset = struct.unpack_from(">I", v, 6)[0]
        chunk_size = struct.unpack_from(">I", v, 10)[0]
        return ChunkInfo(total_chunks, chunk_index, original_size, chunk_offset, chunk_size)

    @property
    def blob_refs(self):
        from aicl.bin.types import BlobRef
        out = []
        for d in self._ext_all(X.EXT_BLOB_REF):
            ref_type, il = d[0], d[1]
            size = struct.unpack_from(">I", d, 2)[0]
            offset = struct.unpack_from(">I", d, 6)[0]
            identifier = d[10:10 + il].decode()
            out.append(BlobRef(ref_type, identifier, size, offset))
        return out

    @property
    def backpressure(self):
        v = self._ext_one(X.EXT_BACKPRESSURE)
        if not v or len(v) < 12:
            return None
        return Backpressure(struct.unpack_from(">I", v, 0)[0],
                             struct.unpack_from(">I", v, 4)[0],
                             struct.unpack_from(">H", v, 8)[0],
                             struct.unpack_from(">H", v, 10)[0])

    @property
    def error_info(self):
        v = self._ext_one(X.EXT_ERROR_INFO)
        if not v or len(v) < 7:
            return None
        ec, sev = struct.unpack_from(">HH", v, 0)
        ml = v[4]
        off = 5
        if off + ml > len(v):
            return None
        msg = v[off:off + ml].decode()
        off += ml
        dl = struct.unpack_from(">H", v, off)[0] if off + 2 <= len(v) else 0
        off += 2
        det = v[off:off + dl].decode() if dl else None
        return ErrorInfo(ec, sev, msg, det)

    @property
    def ack_info(self):
        from aicl.bin.types import AckInfo
        v = self._ext_one(X.EXT_ACK_INFO)
        return AckInfo(v[1:].decode()) if v and len(v) >= 1 else None

    @property
    def target_caps(self):
        v = self._ext_one(X.EXT_TARGET_CAPS)
        return [c.decode() for c in v.split(b",") if c] if v else []

    @property
    def schema_id(self):
        v = self._ext_one(X.EXT_SCHEMA_ID)
        return v.decode() if v else ""

    @property
    def stream_id(self):
        return self._ext_one(X.EXT_STREAM_ID)

    @property
    def partial_result(self):
        return self._ext_one(X.EXT_PARTIAL_RESULT)

    @property
    def model_invocation(self):
        from aicl.bin.types import ModelInvocation
        v = self._ext_one(X.EXT_MODEL_INVOCATION)
        if not v or len(v) < 3:
            return None
        nl, tl, pl = v[0], v[1], v[2]
        off = 3
        model_name = v[off:off + nl].decode(); off += nl
        task = v[off:off + tl].decode(); off += tl
        parameters_json = v[off:off + pl].decode(); off += pl
        timeout_ms = struct.unpack_from(">I", v, off)[0] if off + 4 <= len(v) else 0
        return ModelInvocation(model_name, task, parameters_json, timeout_ms)

    @property
    def tool_invocation(self):
        from aicl.bin.types import ToolInvocation
        v = self._ext_one(X.EXT_TOOL_INVOCATION)
        if not v or len(v) < 2:
            return None
        nl, pl = v[0], v[1]
        off = 2
        tool_name = v[off:off + nl].decode(); off += nl
        parameters_json = v[off:off + pl].decode(); off += pl
        timeout_ms = struct.unpack_from(">I", v, off)[0] if off + 4 <= len(v) else 0
        return ToolInvocation(tool_name, parameters_json, timeout_ms)

    @property
    def metadata(self):
        v = self._ext_one(X.EXT_METADATA)
        if not v:
            return {}
        result, pos = {}, 0
        while pos < len(v):
            kl = v[pos]
            pos += 1
            if pos + kl > len(v):
                break
            k = v[pos:pos + kl].decode()
            pos += kl
            vl = struct.unpack_from(">H", v, pos)[0]
            pos += 2
            if pos + vl > len(v):
                break
            result[k] = v[pos:pos + vl].decode()
            pos += vl
        return result

    @property
    def extension_tlvs(self):
        """Back-compat name for the raw (tag, bytes) vendor extensions —
        kept for callers that inspected this before the payload-structure
        rewrite. Prefer the named properties above."""
        return [(tag, v) for tag, vals in self._extensions.items() for v in vals]

    def __repr__(self):
        return "<PacketView op=0x%02x flags=0x%04x msg=%s>" % (
            self.operation, self.flags, self.message_id.hex()[:8])


def _decode_symbol_seq(data) -> Tuple[list, int]:
    """Decode a back-to-back operand sequence (no count prefix) — used for
    the response_symbols extension, which stores its operands the same
    way encode_symbols() writes them."""
    result = []
    pos = 0
    while pos < len(data):
        sym, pos = decode_symbol(data, pos)
        result.append(sym)
    return result, pos
