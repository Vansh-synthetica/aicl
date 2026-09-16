"""
Cross-process AICL streaming — client side. Times how long it takes to
receive a full 50-chunk stream through the shared-memory ring, repeated N
times, cross-process (separate OS process running streaming_aicl_server.py).
Directly comparable to streaming_sse_client.py.

Run: python streaming_aicl_client.py [repeats]
"""
from __future__ import annotations

import statistics
import subprocess
import sys
import time
import uuid

from aicl.bin.codec_api import decode
from aicl.transport.shared_memory_ring import SharedMemoryRing

STOP_SENTINEL = b"__STOP__"
GO_SENTINEL = b"__GO__"


def percentile(sorted_us: list[float], p: float) -> float:
    if not sorted_us:
        return 0.0
    idx = min(int((p / 100.0) * len(sorted_us)), len(sorted_us) - 1)
    return sorted_us[idx]


def one_stream(control: SharedMemoryRing, out: SharedMemoryRing) -> tuple[float, int]:
    t0 = time.perf_counter()
    control.push(GO_SENTINEL)
    n = 0
    while True:
        wire = out.pop()
        view = decode(wire)
        n += 1
        if view.intent == "end":
            break
    return (time.perf_counter() - t0) * 1_000_000, n


def main() -> None:
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 200

    control_name = f"aicl_ctl_{uuid.uuid4().hex[:8]}"
    out_name = f"aicl_out_{uuid.uuid4().hex[:8]}"
    control = SharedMemoryRing.create(control_name, capacity=4, slot_size=256)
    out = SharedMemoryRing.create(out_name, capacity=64, slot_size=256)

    proc = subprocess.Popen(
        [sys.executable, "streaming_aicl_server.py", control_name, out_name],
        cwd="D:/New folder (6)/Projects/AICL/benchmarks/https_vs_binary")
    try:
        one_stream(control, out)  # warm-up: pays process-spawn/attach cost

        stream_times_us: list[float] = []
        overall_start = time.perf_counter()
        for _ in range(repeats):
            t_us, _n = one_stream(control, out)
            stream_times_us.append(t_us)
        overall_total = time.perf_counter() - overall_start

        stream_times_us.sort()
        avg = statistics.mean(stream_times_us)
        p50 = percentile(stream_times_us, 50.0)
        p95 = percentile(stream_times_us, 95.0)
        p99 = percentile(stream_times_us, 99.0)
        streams_per_sec = repeats / overall_total

        print(f"AICL Cross-Process Streaming Benchmark ({repeats} streams x 51 chunks each)")
        print(f"  {'Configuration':<40} {'Avg':>10} {'p50':>10} {'p95':>10} {'p99':>10} {'Streams/s':>10}")
        print(f"  {'-' * 92}")
        print(f"  {'AICL ring full-stream completion (51ch)':<40} "
              f"{avg:>9.1f}us {p50:>9.1f}us {p95:>9.1f}us {p99:>9.1f}us {streams_per_sec:>10.1f}")
        print(f"  per-chunk average: {avg / 51:.1f}us")
    finally:
        control.push(STOP_SENTINEL)
        proc.wait(timeout=10)
        control.close()
        out.close()


if __name__ == "__main__":
    main()
