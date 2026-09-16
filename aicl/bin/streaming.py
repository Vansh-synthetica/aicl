"""AICL-BIN streaming decoder for partial buffers."""
from __future__ import annotations
import struct
from typing import List
from aicl.bin.constants import HEADER_SIZE
from aicl.bin.validation import validate_header

__all__ = ["StreamingDecoder"]


class StreamingDecoder:
    """Incremental decoder for stream of bytes.

    Feed raw bytes in any chunk size; each call to `feed()` returns zero or
    more complete PacketViews. Partial packets are held in an internal buffer
    until more bytes arrive.
    """

    def __init__(self, max_packets_per_feed: int = 256):
        self._buf = bytearray()
        self._max_per_feed = max_packets_per_feed

    def feed(self, data: bytes) -> List:
        """Consume bytes, return completed PacketViews."""
        self._buf.extend(data)
        results: List = []
        n = len(self._buf)

        # Find the earliest position with an incomplete packet (and decode any
        # complete packets before it).
        scan = 0
        first_incomplete = -1
        last_consumed = 0

        while scan + HEADER_SIZE <= n and len(results) < self._max_per_feed:
            idx = self._buf.find(b"AICL", scan)
            if idx < 0 or idx + HEADER_SIZE > n:
                break
            scan = idx
            try:
                validate_header(memoryview(self._buf)[scan:scan + HEADER_SIZE])
            except Exception:
                scan += 1
                continue
            payload_length = struct.unpack_from(">I", self._buf, scan + 56)[0]
            pkt_end = scan + HEADER_SIZE + payload_length
            has_trailer = (self._buf[scan + 6] << 8 | self._buf[scan + 7]) & 0x0100
            if has_trailer:
                pkt_end += 4
            if n < pkt_end:
                first_incomplete = scan
                break
            from aicl.bin.codec_api import decode
            pkt_buf = bytes(self._buf[scan:pkt_end])
            results.append(decode(pkt_buf))
            scan = pkt_end
            last_consumed = pkt_end

        if first_incomplete >= 0:
            del self._buf[:first_incomplete]
        elif last_consumed > 0:
            del self._buf[:last_consumed]

        return results

    def pending(self) -> int:
        return len(self._buf)

    def clear(self) -> None:
        self._buf.clear()

    def __repr__(self) -> str:
        return f"<StreamingDecoder pending={len(self._buf)} bytes>"

