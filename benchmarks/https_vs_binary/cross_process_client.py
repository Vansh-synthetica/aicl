"""
Cross-process AICL benchmark — client side.

Creates two shared-memory rings (request, response), spawns
cross_process_server.py as a genuinely separate OS process, then does N
real request/response round trips through the actual aicl.bin codec —
directly comparable to client.py's FastAPI HTTPS benchmark, which is also
two separate OS processes on the same machine. This is the apples-to-apples
version of the comparison: same language (Python), same process boundary,
only the transport differs.

Run: python cross_process_client.py [iterations]
"""
from __future__ import annotations

import statistics
import subprocess
import sys
import time
import uuid

from aicl.bin.codec_api import decode, encode
from aicl.bin.codec_packet import Packet
from aicl.bin.symbol_types import S_STRING
from aicl.bin.types import Symbol
from aicl.transport.shared_memory_ring import SharedMemoryRing

STOP_SENTINEL = b"__STOP__"


def percentile(sorted_us: list[float], p: float) -> float:
    if not sorted_us:
        return 0.0
    idx = min(int((p / 100.0) * len(sorted_us)), len(sorted_us) - 1)
    return sorted_us[idx]


def print_result(name: str, latencies_us: list[float], total_s: float, iterations: int) -> None:
    avg = statistics.mean(latencies_us)
    p50 = percentile(latencies_us, 50.0)
    p95 = percentile(latencies_us, 95.0)
    p99 = percentile(latencies_us, 99.0)
    throughput = iterations / total_s
    print(f"  {name:<40} {avg:>9.1f}us {p50:>9.1f}us {p95:>9.1f}us {p99:>9.1f}us {throughput:>10.0f}")


def main() -> None:
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 5000

    req_name = f"aicl_req_{uuid.uuid4().hex[:8]}"
    resp_name = f"aicl_resp_{uuid.uuid4().hex[:8]}"
    req_ring = SharedMemoryRing.create(req_name, capacity=8, slot_size=512)
    resp_ring = SharedMemoryRing.create(resp_name, capacity=8, slot_size=512)

    proc = subprocess.Popen([sys.executable, "cross_process_server.py", req_name, resp_name],
                             cwd="D:/New folder (6)/Projects/AICL/benchmarks/https_vs_binary")
    try:
        request = Packet(operation=3, symbols=[
            Symbol(S_STRING, "The quick brown fox jumps over the lazy dog."),
            Symbol(S_STRING, "gpt-4"),
        ])
        wire = encode(request)

        # Warm-up: first cross-process message pays process-spawn/attach cost.
        req_ring.push(wire)
        resp_ring.pop()

        latencies: list[float] = []
        start = time.perf_counter()
        for _ in range(iterations):
            t0 = time.perf_counter()
            req_ring.push(wire)
            resp_wire = resp_ring.pop()
            decode(resp_wire)
            latencies.append((time.perf_counter() - t0) * 1_000_000)
        total = time.perf_counter() - start
        latencies.sort()

        print(f"AICL Cross-Process Benchmark ({iterations} iterations)")
        print(f"  {'Configuration':<40} {'Avg':>10} {'p50':>10} {'p95':>10} {'p99':>10} {'Throughput':>10}")
        print(f"  {'-' * 92}")
        print_result("AICL shared-memory ring (2 processes)", latencies, total, iterations)
    finally:
        req_ring.push(STOP_SENTINEL)
        proc.wait(timeout=10)
        req_ring.close()
        resp_ring.close()


if __name__ == "__main__":
    main()
