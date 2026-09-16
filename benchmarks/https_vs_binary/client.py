"""
HTTPS transport benchmark — client side.

Measures round-trip latency for the same kind of AI-to-AI request/response
AICL's own bench_local_path.rs measures for its native path: encode a
request, send it, get a response, decode it. Reports avg/p50/p95/p99 and
throughput in the same format as the Rust benchmark for direct comparison.

Two connection modes are measured, since which is realistic depends on how
the FastAPI service is actually used:
  - persistent: one TCP+TLS connection, reused for every request (best case
    for HTTPS — the TLS handshake cost is paid once).
  - fresh: a new TCP+TLS connection per request (worst case — the honest
    comparison if "AI module A" doesn't keep a long-lived connection open
    to "AI module B", e.g. a serverless/short-lived-process caller).

Run: python client.py [iterations]
"""
from __future__ import annotations

import statistics
import sys
import time

import httpx

BASE_URL = "https://127.0.0.1:8443"
REQUEST_BODY = {
    "text": "The quick brown fox jumps over the lazy dog.",
    "labels": ["positive", "negative", "neutral"],
    "model": "gpt-4",
}


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
    print(f"  {name:<40} {avg:>9.1f}µs {p50:>9.1f}µs {p95:>9.1f}µs {p99:>9.1f}µs {throughput:>10.0f}")


def bench_persistent(iterations: int) -> None:
    latencies: list[float] = []
    with httpx.Client(base_url=BASE_URL, verify=False, http2=False) as client:
        # Warm the connection (TLS handshake) outside the timed loop.
        client.post("/classify", json=REQUEST_BODY)
        start = time.perf_counter()
        for _ in range(iterations):
            t0 = time.perf_counter()
            resp = client.post("/classify", json=REQUEST_BODY)
            resp.json()
            latencies.append((time.perf_counter() - t0) * 1_000_000)
        total = time.perf_counter() - start
    latencies.sort()
    print_result("HTTPS classify (persistent conn)", latencies, total, iterations)


def bench_fresh_connection(iterations: int) -> None:
    latencies: list[float] = []
    start = time.perf_counter()
    for _ in range(iterations):
        t0 = time.perf_counter()
        with httpx.Client(base_url=BASE_URL, verify=False, http2=False) as client:
            resp = client.post("/classify", json=REQUEST_BODY)
            resp.json()
        latencies.append((time.perf_counter() - t0) * 1_000_000)
    total = time.perf_counter() - start
    latencies.sort()
    print_result("HTTPS classify (fresh conn/request)", latencies, total, iterations)


if __name__ == "__main__":
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    fresh_iterations = min(iterations, 500)  # TLS handshake per request is slow

    print(f"HTTPS Transport Benchmark ({iterations} iterations, persistent; "
          f"{fresh_iterations} iterations, fresh)")
    print(f"  {'Configuration':<40} {'Avg':>10} {'p50':>10} {'p95':>10} {'p99':>10} {'Throughput':>10}")
    print(f"  {'-' * 92}")
    bench_persistent(iterations)
    bench_fresh_connection(fresh_iterations)
