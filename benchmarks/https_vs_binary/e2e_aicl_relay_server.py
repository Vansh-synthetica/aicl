"""
End-to-end AICL relay server — a separate OS process that receives a
generate request over the AICL shared-memory ring, calls llama-server's
real streaming completion endpoint, and forwards each real token chunk to
the client over AICL as it arrives (not buffered — same "relay tokens as
they're produced" shape Orcha's SSE relay uses today).
"""
from __future__ import annotations

import asyncio
import sys

import httpx

from aicl.bin.codec_api import decode, encode
from aicl.bin.codec_packet import Packet
from aicl.bin.symbol_types import S_STRING
from aicl.bin.types import Symbol
from aicl.transport.shared_memory_ring import SharedMemoryRing

STOP_SENTINEL = b"__STOP__"
LLAMA_URL = "http://localhost:8099/v1/chat/completions"
MAX_TOKENS = 40


async def main() -> None:
    req_name, resp_name = sys.argv[1], sys.argv[2]
    req_ring = SharedMemoryRing.attach(req_name)
    resp_ring = SharedMemoryRing.attach(resp_name)

    while True:
        # Long timeout: this blocks between requests for however long the
        # client takes between calls, which in a benchmark loop should be
        # near-instant but during process startup (cold Python interpreter
        # + import time for this script itself) can eat into a short
        # default budget before the first request even arrives.
        wire = req_ring.pop(timeout_s=120.0)
        if wire == STOP_SENTINEL:
            break
        view = decode(wire)
        prompt = view.symbols[0].value

        # A fresh AsyncClient per call to llama-server, not a reused
        # persistent one, and async rather than sync:
        #  - llama-server doesn't reliably support HTTP keep-alive
        #    (confirmed: a reused connection gets forcibly closed by the
        #    server on the second request; httpx's stale-connection retry
        #    silently adds ~2s that has nothing to do with AICL's own
        #    transport).
        #  - sync httpx streaming reads measured ~2x slower than async for
        #    this exact request against this exact server on this machine
        #    (~3450ms vs ~1700ms) — a real, large, transport-independent
        #    artifact. Every path in this benchmark that talks to
        #    llama-server uses async for this reason (see
        #    e2e_combined.py's baseline_call), or the comparison would
        #    silently measure "sync vs async httpx" instead of "AICL vs
        #    HTTPS".
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", LLAMA_URL, json={
                "model": "qwen2.5-0.5b",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": MAX_TOKENS,
                "temperature": 0.1,
                "stream": True,
            }) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    # Forward the raw SSE data payload as one AICL chunk —
                    # real token content, relayed as it's produced.
                    chunk = Packet(operation=4, symbols=[Symbol(S_STRING, payload)])
                    resp_ring.push(encode(chunk))
        resp_ring.push(encode(Packet(operation=4, symbols=[], intent="end")))

    req_ring.close()
    resp_ring.close()


if __name__ == "__main__":
    asyncio.run(main())
