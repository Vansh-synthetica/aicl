from __future__ import annotations
import struct
from typing import Optional, List, Tuple
import aicl.bin.constants as C
import aicl.bin.tlv as T
import aicl.bin.symbols as S
import aicl.bin.header as H
from aicl.bin.types import Identity, Symbol, QoS, Backpressure, ErrorInfo


class PacketView:
    __slots__ = ("_raw", "_hdr_end", "_pay_end", "_tlv_cache", "_syms", "_rsyms", "_hdr")

    def __init__(self, raw, hdr_end, pay_end):
        self._raw = raw if isinstance(raw, memoryview) else memoryview(raw)
        self._hdr_end, self._pay_end = hdr_end, pay_end
        self._tlv_cache = {}
        self._syms = None
        self._rsyms = None
        self._hdr = H.unpack_header(self._raw[:C.HEADER_SIZE])

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
    def session_id(self):
        return self._hdr.session_id
    @property
    def message_id(self):
        return self._hdr.message_id
    @property
    def correlation_id(self):
        return self._hdr.correlation_id
    @property
    def payload_length(self):
        return self._hdr.payload_length
    @property
    def target_count(self):
        return self._hdr.target_count
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
    def is_event(self):
        return bool(self.flags & C.FLAG_EVENT)
    @property
    def is_error(self):
        return bool(self.flags & C.FLAG_ERROR)
    @property
    def is_stream_chunk(self):
        return bool(self.flags & C.FLAG_STREAM_CHUNK)
    @property
    def is_eos(self):
        return bool(self.flags & C.FLAG_EOS)
    @property
    def is_fragmented(self):
        return bool(self.flags & C.FLAG_FRAGMENTED)

    def _tlv(self, t):
        if t in self._tlv_cache:
            return self._tlv_cache[t]
        for typ, val, _ in T.iter_tlvs(self._raw[self._hdr_end:self._pay_end]):
            if typ == t:
                self._tlv_cache[t] = val
                return val
        return None

    @property
    def origin(self):
        v = self._tlv(C.TYPE_ORIGIN)
        return Identity.from_bytes(v) if v else None

    @property
    def targets(self):
        v = self._tlv(C.TYPE_TARGETS)
        return [t.decode() for t in v.tobytes().split(b",") if t] if v else []

    @property
    def operation(self):
        v = self._tlv(C.TYPE_OPERATION)
        return v[0] if v else 0

    @property
    def intent(self):
        v = self._tlv(C.TYPE_INTENT)
        return v.tobytes().decode() if v else ""

    @property
    def symbols(self):
        if self._syms is None:
            v = self._tlv(C.TYPE_SYMBOLS)
            self._syms = list(S.iter_symbols(v)) if v else []
        return self._syms

    @property
    def response_symbols(self):
        if self._rsyms is None:
            v = self._tlv(C.TYPE_RESPONSE_SYMBOLS)
            self._rsyms = list(S.iter_symbols(v)) if v else []
        return self._rsyms

    @property
    def confidence(self):
        v = self._tlv(C.TYPE_CONFIDENCE)
        return struct.unpack_from(">d", v.tobytes(), 0)[0] if v and len(v) >= 4 else 1.0

    @property
    def priority(self):
        v = self._tlv(C.TYPE_PRIORITY)
        return v[0] if v else 128

    @property
    def deadline_ms(self):
        v = self._tlv(C.TYPE_DEADLINE)
        return struct.unpack_from(">q", v.tobytes(), 0)[0] if v and len(v) >= 8 else 0

    @property
    def capabilities(self):
        v = self._tlv(C.TYPE_CAPABILITIES)
        return [c.decode() for c in v.tobytes().split(b",") if c] if v else []

    @property
    def qos(self):
        v = self._tlv(C.TYPE_QOS)
        if not v or len(v) < 12:
            return None
        d = v.tobytes()
        return QoS(d[0], d[1], d[2], d[3],
                   struct.unpack_from(">I", d, 4)[0],
                   struct.unpack_from(">I", d, 8)[0])

    @property
    def stream_id(self):
        v = self._tlv(C.TYPE_STREAM_ID)
        return bytes(v[:16]) if v and len(v) >= 16 else None

    @property
    def partial_result(self):
        v = self._tlv(C.TYPE_PARTIAL_RESULT)
        return v.tobytes() if v else None

    @property
    def schema_id(self):
        v = self._tlv(C.TYPE_SCHEMA_ID)
        return v.tobytes().decode() if v else ""

    @property
    def error_info(self):
        v = self._tlv(C.TYPE_ERROR_INFO)
        if not v:
            return None
        d = v.tobytes()
        if len(d) < 7:
            return None
        ec, sev = struct.unpack_from(">HH", d, 0)
        ml = d[4]
        off = 5
        if off + ml > len(d):
            return None
        msg = d[off:off + ml].decode()
        off += ml
        dl = struct.unpack_from(">H", d, off)[0] if off + 2 <= len(d) else 0
        off += 2
        det = d[off:off + dl].decode() if dl else None
        return ErrorInfo(ec, sev, msg, det)

    @property
    def backpressure(self):
        v = self._tlv(C.TYPE_BACKPRESSURE)
        if not v or len(v) < 12:
            return None
        d = v.tobytes()
        return Backpressure(struct.unpack_from(">I", d, 0)[0],
                            struct.unpack_from(">I", d, 4)[0],
                            struct.unpack_from(">H", d, 8)[0],
                            struct.unpack_from(">H", d, 10)[0])

    @property
    def metadata(self):
        v = self._tlv(C.TYPE_METADATA)
        if not v:
            return {}
        result, pos = {}, 0
        d = v.tobytes()
        while pos < len(d):
            kl = d[pos]
            pos += 1
            if pos + kl > len(d):
                break
            k = d[pos:pos + kl].decode()
            pos += kl
            vl = struct.unpack_from(">H", d, pos)[0]
            pos += 2
            if pos + vl > len(d):
                break
            result[k] = d[pos:pos + vl].decode()
            pos += vl
        return result

    @property
    def extension_tlvs(self):
        return [(t, v.tobytes()) for t, v, _ in T.iter_tlvs(self._raw[self._hdr_end:self._pay_end])]

    def __repr__(self):
        return "<PacketView op=%d flags=0x%04x msg=%s>" % (self.operation, self.flags, self.message_id.hex()[:8])
