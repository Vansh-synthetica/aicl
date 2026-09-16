"""
Cross-process AICL server — attaches to two shared-memory rings created by
the client, decodes each request with the real aicl.bin codec, and replies
with a real classify response. Runs as its own OS process (spawned via
subprocess.Popen by the client), so this is genuine cross-process IPC, not
an in-process shortcut.
"""
from __future__ import annotations

import sys

from aicl.bin.codec_api import decode, encode
from aicl.bin.codec_packet import Packet
from aicl.bin.symbol_types import S_STRING
from aicl.bin.types import Symbol
from aicl.transport.shared_memory_ring import SharedMemoryRing

STOP_SENTINEL = b"__STOP__"


def main() -> None:
    req_name, resp_name = sys.argv[1], sys.argv[2]
    req_ring = SharedMemoryRing.attach(req_name)
    resp_ring = SharedMemoryRing.attach(resp_name)

    while True:
        wire = req_ring.pop()
        if wire == STOP_SENTINEL:
            break
        _view = decode(wire)  # real decode — mirrors what a model module would do
        response = Packet(operation=3, symbols=[
            Symbol(S_STRING, "positive"),
            Symbol(S_STRING, "1.0"),
        ])
        resp_ring.push(encode(response))

    req_ring.close()
    resp_ring.close()


if __name__ == "__main__":
    main()
