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
LLAMA_URL = "http://127.0.0.1:8099/v1/chat/completions"
MAX_TOKENS = 40


async def main() -> None:
    req_name, resp_name = sys.argv[1], sys.argv[2]
    req_ring = SharedMemoryRing.attach(req_name)
    resp_ring = SharedMemoryRing.attach(resp_name)

    # One persistent AsyncClient for the whole process lifetime, not a
    # fresh one per call — see e2e_combined.py's baseline_call for the
    # full reasoning: a fresh AsyncClient() costs ~160-220ms to construct
    # regardless of what it talks to (confirmed via direct measurement),
    # and llama-server's keep-alive problem is better solved with an
    # explicit `Connection: close` header per request than by rebuilding
    # the whole client every time. Async (not sync) for the same reason
    # documented there: sync httpx streaming reads measured ~2x slower
    # than async for this exact request on this machine, a real
    # transport-independent artifact every path here must avoid the same
    # way.
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            # Long timeout: this blocks between requests for however long
            # the client takes between calls, which in a benchmark loop
            # should be near-instant but during process startup (cold
            # Python interpreter + import time for this script itself) can
            # eat into a short default budget before the first request
            # even arrives.
            wire = req_ring.pop(timeout_s=120.0)
            if wire == STOP_SENTINEL:
                break
            view = decode(wire)
            prompt = view.symbols[0].value

            async with client.stream("POST", LLAMA_URL, headers={"Connection": "close"}, json={
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
