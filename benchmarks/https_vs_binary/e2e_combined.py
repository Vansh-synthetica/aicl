"""
End-to-end combined benchmark — runs baseline / AICL relay / SSE relay
*interleaved*, one round at a time, instead of as three separate
sequential blocks. Running each condition as its own big block let a real
confound through: llama-server (and the OS page cache, CPU frequency
scaling, etc.) gets faster over the first several calls as things warm up,
so whichever condition happened to run last looked artificially fastest.
Interleaving spreads that warm-up drift evenly across all three
conditions instead of letting it masquerade as a transport effect.

Prerequisites (start these first, in separate terminals):
  1. llama-server on port 8099 (see BENCHMARKS.md)
  2. e2e_sse_relay_server.py via uvicorn on port 8443

Run: python e2e_combined.py [rounds]
"""
from __future__ import annotations

import asyncio
import statistics
import subprocess
import sys
import time
import uuid

import httpx

from aicl.bin.codec_api import decode, encode
from aicl.bin.codec_packet import Packet
from aicl.bin.symbol_types import S_STRING
from aicl.bin.types import Symbol
from aicl.transport.shared_memory_ring import SharedMemoryRing

STOP_SENTINEL = b"__STOP__"
# 127.0.0.1, not "localhost": resolving "localhost" measured ~250-290ms of
# DNS/name-resolution overhead per call on this machine — the literal IP
# skips that entirely (confirmed via direct A/B test, ~5ms vs ~260ms for
# an identical request).
LLAMA_URL = "http://127.0.0.1:8099/v1/chat/completions"
SSE_BASE_URL = "https://127.0.0.1:8443"
PROMPT = "List three interesting facts about the Roman Empire."
MAX_TOKENS = 40


async def baseline_call(client: httpx.AsyncClient) -> float:
    # httpx.AsyncClient, not the sync Client: a direct side-by-side test
    # (sync vs async, identical request, same server) measured sync
    # streaming reads at ~3450ms and async at ~1700ms for this exact
    # request on this machine — a real, large, completely
    # transport-independent httpx/Windows-networking artifact. Every path
    # in this benchmark that talks to llama-server uses async for this
    # reason, or the comparison silently measures "sync vs async httpx"
    # instead of "AICL vs HTTPS".
    #
    # One persistent client, reused across calls, with an explicit
    # `Connection: close` header per request — not a fresh AsyncClient()
    # constructed every call. llama-server doesn't reliably support HTTP
    # keep-alive (confirmed: a reused connection with no close-signal gets
    # forcibly closed by the server on the second request, WinError
    # 10054), but constructing a whole fresh AsyncClient to work around
    # that costs ~160-220ms of its own, every single call (confirmed via
    # direct measurement — that cost is flat regardless of trust_env or
    # host, i.e. it's the client object's own setup, not networking).
    # Sending `Connection: close` tells httpx to close and replace the
    # connection itself after each response — same safety against the
    # stale-connection bug, without paying full client reconstruction.
    t0 = time.perf_counter()
    async with client.stream("POST", LLAMA_URL, headers={"Connection": "close"}, json={
        "model": "qwen2.5-0.5b",
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAX_TOKENS, "temperature": 0.1, "stream": True,
    }) as resp:
        async for _line in resp.aiter_lines():
            pass
    return (time.perf_counter() - t0) * 1000


def aicl_call(req_ring: SharedMemoryRing, resp_ring: SharedMemoryRing) -> float:
    t0 = time.perf_counter()
    req_ring.push(encode(Packet(operation=4, symbols=[Symbol(S_STRING, PROMPT)])), timeout_s=30.0)
    while True:
        view = decode(resp_ring.pop(timeout_s=30.0))
        if view.intent == "end":
            break
    return (time.perf_counter() - t0) * 1000


def summarize(name: str, times_ms: list[float]) -> None:
    print(f"  {name:<28} avg: {statistics.mean(times_ms):>8.1f}ms   "
          f"p50: {statistics.median(times_ms):>8.1f}ms   "
          f"min: {min(times_ms):>8.1f}ms   max: {max(times_ms):>8.1f}ms")


async def main() -> None:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    req_name = f"aicl_e2e_req_{uuid.uuid4().hex[:8]}"
    resp_name = f"aicl_e2e_resp_{uuid.uuid4().hex[:8]}"
    req_ring = SharedMemoryRing.create(req_name, capacity=4, slot_size=1024)
    resp_ring = SharedMemoryRing.create(resp_name, capacity=16, slot_size=1024)
    aicl_proc = subprocess.Popen(
        [sys.executable, "e2e_aicl_relay_server.py", req_name, resp_name],
        cwd="D:/New folder (6)/Projects/AICL/benchmarks/https_vs_binary")

    baseline_times: list[float] = []
    aicl_times: list[float] = []
    sse_times: list[float] = []

    try:
        async with httpx.AsyncClient(timeout=60.0) as baseline_client, \
                httpx.AsyncClient(base_url=SSE_BASE_URL, verify=False, http2=False, timeout=60.0) as sse_client:

            # Warm-up: one untimed call per condition, in the same
            # interleaved order, so the FIRST measured round isn't the
            # coldest one for whichever condition happens to run first.
            await baseline_call(baseline_client)
            aicl_call(req_ring, resp_ring)
            await sse_call_async(sse_client)

            print(f"Interleaved end-to-end benchmark ({rounds} rounds x 3 conditions, "
                  f"real {MAX_TOKENS}-token generation each)")
            for i in range(rounds):
                baseline_times.append(await baseline_call(baseline_client))
                aicl_times.append(aicl_call(req_ring, resp_ring))
                sse_times.append(await sse_call_async(sse_client))

        print()
        summarize("Baseline (no relay)", baseline_times)
        summarize("AICL relay (shared memory)", aicl_times)
        summarize("SSE relay (HTTPS)", sse_times)
        print()
        aicl_overhead = statistics.mean(aicl_times) - statistics.mean(baseline_times)
        sse_overhead = statistics.mean(sse_times) - statistics.mean(baseline_times)
        print(f"  AICL relay overhead vs no-relay baseline: {aicl_overhead:+.1f}ms")
        print(f"  SSE relay overhead vs no-relay baseline:  {sse_overhead:+.1f}ms")

        # Paired, round-by-round differences — much more sensitive than
        # comparing the two distributions' means, since round-to-round
        # system noise (CPU scheduling jitter, thermal state, etc.) hits
        # all three conditions within the same round similarly and mostly
        # cancels out here instead of drowning out a genuinely small
        # per-message transport difference.
        paired_sse_minus_aicl = [sse - aicl for sse, aicl in zip(sse_times, aicl_times)]
        paired_aicl_minus_base = [aicl - base for aicl, base in zip(aicl_times, baseline_times)]
        print()
        print(f"  Paired (SSE - AICL) per round: mean {statistics.mean(paired_sse_minus_aicl):+.1f}ms, "
              f"median {statistics.median(paired_sse_minus_aicl):+.1f}ms, "
              f"stdev {statistics.stdev(paired_sse_minus_aicl):.1f}ms")
        print(f"  Paired (AICL - baseline) per round: mean {statistics.mean(paired_aicl_minus_base):+.1f}ms, "
              f"median {statistics.median(paired_aicl_minus_base):+.1f}ms, "
              f"stdev {statistics.stdev(paired_aicl_minus_base):.1f}ms")
    finally:
        req_ring.push(STOP_SENTINEL)
        aicl_proc.wait(timeout=10)
        req_ring.close()
        resp_ring.close()


async def sse_call_async(client: httpx.AsyncClient) -> float:
    t0 = time.perf_counter()
    async with client.stream("POST", "/generate", json={"prompt": PROMPT}) as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data:") and '"kind": "end"' in line:
                break
    return (time.perf_counter() - t0) * 1000


if __name__ == "__main__":
    asyncio.run(main())
