"""
FastAPI SSE streaming — client side. Times how long it takes to receive a
full 50-chunk token stream over HTTPS+SSE, repeated N times, cross-process
(separate uvicorn process). This is the realistic shape of Orcha's actual
production streaming: many small JSON events per response, not one big
payload.

Run: python streaming_sse_client.py [repeats]
"""
from __future__ import annotations

import statistics
import sys
import time

import httpx

BASE_URL = "https://127.0.0.1:8443"


def percentile(sorted_ms: list[float], p: float) -> float:
    if not sorted_ms:
        return 0.0
    idx = min(int((p / 100.0) * len(sorted_ms)), len(sorted_ms) - 1)
    return sorted_ms[idx]


def one_stream(client: httpx.Client) -> tuple[float, int]:
    """Returns (total_stream_time_us, chunk_count)."""
    t0 = time.perf_counter()
    n = 0
    with client.stream("GET", "/stream") as resp:
        for line in resp.iter_lines():
            if line.startswith("data:"):
                n += 1
    return (time.perf_counter() - t0) * 1_000_000, n


def main() -> None:
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    stream_times_us: list[float] = []
    with httpx.Client(base_url=BASE_URL, verify=False, http2=False, timeout=30.0) as client:
        one_stream(client)  # warm the connection
        overall_start = time.perf_counter()
        for _ in range(repeats):
            t_us, _n = one_stream(client)
            stream_times_us.append(t_us)
        overall_total = time.perf_counter() - overall_start

    stream_times_us.sort()
    avg = statistics.mean(stream_times_us)
    p50 = percentile(stream_times_us, 50.0)
    p95 = percentile(stream_times_us, 95.0)
    p99 = percentile(stream_times_us, 99.0)
    streams_per_sec = repeats / overall_total

    print(f"HTTPS SSE Streaming Benchmark ({repeats} streams x 51 chunks each)")
    print(f"  {'Configuration':<40} {'Avg':>10} {'p50':>10} {'p95':>10} {'p99':>10} {'Streams/s':>10}")
    print(f"  {'-' * 92}")
    print(f"  {'SSE full-stream completion (51 chunks)':<40} "
          f"{avg:>9.1f}us {p50:>9.1f}us {p95:>9.1f}us {p99:>9.1f}us {streams_per_sec:>10.1f}")
    print(f"  per-chunk average: {avg / 51:.1f}us")


if __name__ == "__main__":
    main()
