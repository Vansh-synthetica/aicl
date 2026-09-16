"""
Cross-process AICL streaming server — pushes a 50-chunk stream (same shape
as Orcha's real token-delta events) through a shared-memory ring, one AICL
packet per chunk, using ChunkInfo for real chunk metadata. Runs as its own
OS process.
"""
from __future__ import annotations

import sys

from aicl.bin.codec_api import encode
from aicl.bin.codec_packet import Packet
from aicl.bin.symbol_types import S_STRING
from aicl.bin.types import ChunkInfo, Symbol
from aicl.transport.shared_memory_ring import SharedMemoryRing

STOP_SENTINEL = b"__STOP__"
GO_SENTINEL = b"__GO__"
N_CHUNKS = 50
CHUNK_TEXT = " token"


def main() -> None:
    control_name, out_name = sys.argv[1], sys.argv[2]
    control = SharedMemoryRing.attach(control_name)
    out = SharedMemoryRing.attach(out_name)

    while True:
        cmd = control.pop()
        if cmd == STOP_SENTINEL:
            break
        # cmd == GO_SENTINEL: stream 50 chunks as fast as possible.
        for i in range(N_CHUNKS):
            pkt = Packet(
                operation=4,  # OP_GEN
                symbols=[Symbol(S_STRING, CHUNK_TEXT)],
                chunk_info=ChunkInfo(
                    total_chunks=N_CHUNKS, chunk_index=i,
                    original_size=len(CHUNK_TEXT) * N_CHUNKS,
                    chunk_offset=i * len(CHUNK_TEXT), chunk_size=len(CHUNK_TEXT),
                ),
            )
            out.push(encode(pkt))
        out.push(encode(Packet(operation=4, symbols=[], intent="end")))

    control.close()
    out.close()


if __name__ == "__main__":
    main()
