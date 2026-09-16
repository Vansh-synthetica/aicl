# Benchmarks: AICL vs FastAPI/HTTPS

This document exists to answer one question honestly: **for AI-module-to-
AI-module communication on the same machine, how much does AICL's binary
shared-memory transport actually save over a normal FastAPI/HTTPS/JSON
service?** Every number below is reproducible — the scripts that produced
it are in this repo, and the commands to rerun them are included.

## TL;DR

| Scenario | AICL | FastAPI/HTTPS | Difference |
|---|---|---|---|
| Request/response, **same process** (Rust) | 140ns avg | — | — |
| Request/response, **cross-process** (Python, 2 real OS processes) | 16.3µs avg | 1,063µs avg (persistent conn) | **~65× faster** |
| Request/response, cross-process, fresh connection each time | 16.3µs avg | 17,093µs avg | **~1,050× faster** |
| Streaming, 51 chunks/response, cross-process (no real inference) | 452µs/stream (8.9µs/chunk) | 14,005µs/stream (275µs/chunk) | **~31× faster** |
| **End-to-end with real model inference** (40 real tokens, Qwen2.5-0.5B) | 952ms avg, **−6.3ms vs. no-relay** | 964ms avg, **+5.2ms vs. no-relay** | **~1% faster overall** |

The pure-transport numbers (rows 1–4) isolate transport/codec cost from
compute — that's the right way to measure a transport, but by itself it
overstates what a user actually feels. The **last row is the one that
matters for judging real impact**: with genuine model inference in the
loop, AICL adds no measurable overhead over calling the model directly,
while HTTPS/SSE adds ~78ms — real, but a small fraction of total time once
the model itself is doing ~950ms of work. Read [Methodology](#methodology)
and [What this does and doesn't prove](#what-this-does-and-doesnt-prove)
before citing any of this.

## Results

### 1. Same-process, Rust (`core-rust/examples/bench_local_path.rs`)

Both ends of the channel live in one OS process, communicating through a
lock-free SPSC ring buffer over a raw pointer — no process boundary, no
OS involved in the handoff at all. This measures the transport primitive
itself, not a deployable two-module system.

```
cd core-rust
cargo run --release --example bench_local_path
```

| Path | Avg | p50 | p95 | p99 | Throughput |
|---|---|---|---|---|---|
| Encode (reuse buffer) | 93–147ns | 100ns | 200–300ns | 200–300ns | 5.5–8.2M/s |
| Decode (zero-copy view) | 48–52ns | 0–100ns | 100ns | 100ns | 11.7–12.8M/s |
| Decode (owned/`Arc` copy) | 91–395ns | 100–400ns | 100–400ns | 100–500ns | 2.2–6.6M/s |
| Raw ring buffer push+pop | 30–33ns | 0ns | 100ns | 100–200ns | 14.9–16.1M/s |
| **`LocalChannel` (zero-copy)** | **140ns** | **100ns** | **300ns** | **300ns** | **5.79M/s** |
| `LocalChannel` (standard decode) | 197ns | 200ns | 300ns | 400ns | 3.86M/s |

These are in the same tens-to-hundreds-of-nanoseconds range independently-
reported shared-memory IPC implementations typically land in for same-
process operation — consistent with what a lock-free ring buffer with no
syscalls in the hot path should achieve.

### 2. Cross-process, Python (`benchmarks/https_vs_binary/`)

**This is the comparison that actually matters.** Two genuinely separate
OS processes (`subprocess.Popen`-spawned, verifiably different PIDs),
communicating through real OS-backed shared memory
(`multiprocessing.shared_memory`), using the same `aicl.bin` codec that
ships in this repo — the exact same Python encode/decode path Stage 0's
92-test suite exercises. Same interpreter, same language, same kind of
process boundary as the FastAPI benchmark below; only the transport
differs.

```
cd benchmarks/https_vs_binary
"../../.venv/Scripts/python.exe" cross_process_client.py 5000
```

| Metric | Value |
|---|---|
| Avg | 16.3µs |
| p50 | 14.1µs |
| p95 | 19.6µs |
| p99 | 75.6µs |
| Throughput | 60,693 req/s |

The response payload each round trip carries is real: `{"label":
"positive", "confidence": 1.0}`, captured live from Qwen2.5-0.5B-Instruct
running under `llama-server` — not synthetic filler text. **The 16.3µs is
the transport-and-codec cost of moving that already-generated response
between two processes, not the model inference that produced it.** Qwen
inference for that response took ~345ms; nothing in this benchmark re-runs
that per iteration, on either side of the comparison.

### 3. Cross-process, FastAPI/HTTPS (`benchmarks/https_vs_binary/client.py`)

Two separate OS processes: a `uvicorn` server terminating a self-signed
TLS connection, and an `httpx` client. Same request/response shape, same
canned response payload as above.

```
python gen_cert.py
python -m uvicorn server:app --host 127.0.0.1 --port 8443 \
    --ssl-keyfile key.pem --ssl-certfile cert.pem --log-level warning &
python client.py 5000
```

| Mode | Avg | p50 | p95 | p99 | Throughput |
|---|---|---|---|---|---|
| Persistent connection (TLS handshake paid once) | 1,063µs | 932µs | 1,738µs | 3,003µs | 940 req/s |
| Fresh connection per request (TLS handshake every time) | 17,093µs | 16,769µs | 26,087µs | 29,485µs | 58 req/s |

**Important correction from an earlier draft of this comparison:** the
persistent-connection overhead is *not* a repeated TLS handshake — that
cost is paid once, when the connection opens, and amortized across every
request after. What you're seeing in the 1,063µs is TCP-loopback
round-trip + HTTP/1.1 framing + Starlette routing + Pydantic request
validation + JSON serialize/deserialize. The fresh-connection row is where
TLS/TCP setup cost genuinely shows up, on every single request.

### 4. Streaming — the case that actually resembles this project's real traffic

Orcha (this project's agent runtime) streams model output to its desktop
frontend as Server-Sent Events, one small JSON event per token
(`orcha/api/agent_stream.py`: `yield f"data: {json.dumps(wire)}\n\n"`).
That's a *many small messages per response* pattern, which is exactly
where per-message transport overhead compounds instead of being drowned
out by a single big payload. This benchmark reproduces that shape: 50
token-delta chunks + 1 end marker per "response," cross-process both ways.

```
# AICL side
python streaming_aicl_client.py 200

# SSE side (separate terminal, server already running from step 3)
python -m uvicorn streaming_sse_server:app --host 127.0.0.1 --port 8443 \
    --ssl-keyfile key.pem --ssl-certfile cert.pem --log-level warning &
python streaming_sse_client.py 200
```

| Path | Avg full stream | p50 | p95 | p99 | Per-chunk avg | Streams/s |
|---|---|---|---|---|---|---|
| **AICL shared-memory ring** | **452µs** | 422µs | 658µs | 793µs | **8.9µs** | 2,206 |
| FastAPI SSE (HTTPS) | 14,005µs | 13,265µs | 18,734µs | 24,993µs | 275µs | 71.4 |

~31× faster to deliver a complete 51-chunk stream. This is the scenario
where AICL's transport choice would actually be felt by a real user —
every chunk saved is latency a token-by-token UI update doesn't have to
wait through.

### 5. End-to-end with real model inference — does the transport gap survive contact with real work?

Every result above deliberately excludes model inference, to isolate
transport cost. That's the right way to measure a transport, but it leaves
the actual question unanswered: **when a real model is doing real work,
does AICL's transport advantage still matter, or does it disappear into
the noise of generation time?**

This benchmark answers that directly. Three conditions, interleaved
round-by-round (not run as separate blocks — see the warm-up note below),
each doing a **real** 40-token generation against Qwen2.5-0.5B-Instruct
via `llama-server`, no canned responses:

- **Baseline**: client calls `llama-server` directly, no relay.
- **AICL relay**: client → AICL shared-memory ring → relay process → calls
  `llama-server` for real → streams each real token back over the ring as
  it's produced → client.
- **SSE relay**: client → HTTPS → relay process (FastAPI) → calls
  `llama-server` for real → streams each real token back as SSE as it's
  produced → client.

```
cd benchmarks/https_vs_binary
# Start llama-server (port 8099) and e2e_sse_relay_server.py (port 8443) first
"../../.venv/Scripts/python.exe" e2e_combined.py 40
```

| Path | Avg | p50 | min | max |
|---|---|---|---|---|
| Baseline (no relay) | 958.5ms | 944.6ms | 920.3ms | 1,218.7ms |
| **AICL relay** | **952.3ms** | 939.3ms | 922.8ms | 1,274.7ms |
| SSE relay (HTTPS) | 963.8ms | 951.8ms | 929.9ms | 1,268.7ms |

| Comparison | Result |
|---|---|
| AICL relay overhead vs. no-relay baseline | **−6.3ms** (no measurable overhead) |
| SSE relay overhead vs. no-relay baseline | **+5.2ms** |
| Paired, round-by-round (SSE − AICL) | **+11.5ms mean**, +7.3ms median, stdev 24.2ms, over 40 rounds |

**The honest answer: AICL is still faster end-to-end with real inference
in the loop, by a small margin now (~1%) that's close to measurement
noise** — not the 65× or 1,050× a pure-transport comparison shows. ~950ms
of every ~960ms here is real model compute (`llama-server`'s own reported
`prompt_ms + predicted_ms`), which nothing in this benchmark can shrink.
AICL's ring buffer adds no measurable overhead on top of that; FastAPI/SSE
adds a genuine but tiny ~5-12ms. Whether that matters depends entirely on
what you're building — irrelevant for a single request/response, and even
in a tight loop of many calls it's a small fraction of total time once
real inference dominates.

**Getting to this number took four rounds of debugging a benchmark that
was lying to us**, and it's worth documenting in full because the lesson
generalizes well past this one comparison:

1. **Warm-up drift**: running each condition as one big sequential block
   let `llama-server` (and the OS page cache, CPU frequency scaling) get
   faster over the first several calls, so whichever condition ran last
   looked artificially fastest. Fixed by interleaving: one round of
   baseline → AICL → SSE, repeated, instead of three separate blocks.
2. **A real connection-reuse bug**: `llama-server` doesn't reliably
   support HTTP keep-alive — a reused connection gets forcibly closed by
   the server on the second request (`WinError 10054`), and httpx's
   stale-connection retry silently added ~2 seconds that had nothing to
   do with any transport being tested. Initially "fixed" by using a fresh
   client per call — correct in spirit, expensive in practice (see #4).
3. **Sync vs. async httpx**: even after fixing both of the above, one
   path was still ~1.7s faster than the others. Isolated with a direct
   side-by-side test (identical request, identical server, only the
   client's sync-vs-async calling convention changed) — sync httpx
   streaming measured ~3,450ms, async measured ~1,700ms, for the exact
   same request. The SSE relay path happened to use async for its call to
   `llama-server`; baseline and the AICL relay happened to use sync. That
   was the *entire* earlier "HTTPS is faster" result — a Windows/httpx
   networking artifact, not a transport-protocol finding. Fixed by making
   every path's call to `llama-server` use the same (async) convention.
4. **Two genuine, fixable sources of waste, found by profiling the "fast"
   number for where the remaining time actually went** — this is the part
   that made everything ~40% faster, not just more comparable:
   - Resolving `"localhost"` cost **~250-290ms per request** on this
     machine (confirmed via direct A/B test: identical request, `127.0.0.1`
     took ~5ms, `localhost` took ~260ms). Switched every call to
     `llama-server` to the literal IP.
   - Constructing a fresh `httpx.AsyncClient()` per call (the fix from
     step 2) cost a flat **~160-220ms every single time**, regardless of
     host or `trust_env` setting — confirmed this was the client object's
     own setup cost, not networking, by timing client construction with no
     request at all. Fixed by keeping **one persistent `AsyncClient` per
     process**, sending an explicit `Connection: close` header per request
     instead — this still defeats `llama-server`'s keep-alive bug (the
     server closes the connection itself, httpx opens a clean new one for
     the next request) without paying full client-reconstruction cost.

   Combined, these two fixes cut **every condition's time by ~40-42%**
   (baseline: 1,653ms → 958ms; AICL: 1,647ms → 952ms; SSE: 1,732ms →
   964ms) — none of it an AICL-vs-HTTPS effect, all of it avoidable
   Python/Windows networking overhead that was inflating every path
   roughly equally and masking how close to the real inference floor
   (`llama-server`'s own ~950ms) everything actually could get.

None of these four issues were bugs in AICL's own code — all four were in
the benchmark harness (or, for #4, in *how any Python client on Windows
talks to a local HTTP server*, a lesson worth carrying into real code, not
just this benchmark). Reporting the first number that came out at any of
these stages would have been actively misleading.

## Methodology

- **Timer**: Rust benchmarks use `std::time::Instant` (Windows:
  `QueryPerformanceCounter`, sub-microsecond resolution). Python
  benchmarks use `time.perf_counter()` (also sub-microsecond on Windows).
  All latencies are measured client-side, wall-clock, per round trip.
- **Iteration counts**: 100,000 for the same-process Rust benchmarks,
  5,000 for cross-process request/response, 500 for fresh-TLS-connection
  (deliberately smaller — each iteration pays a real handshake), 200
  streams (× 51 chunks = 10,200 messages) for the streaming benchmarks.
- **Warm-up**: every benchmark discards one untimed iteration first, so
  process-spawn cost, connection establishment, and OS/interpreter
  first-call overhead aren't counted in the timed loop (except the
  fresh-connection HTTPS benchmark, where paying that cost every time is
  the point).
- **What's excluded on purpose**: no model inference happens inside any
  timed loop. The response payloads are real (captured once from a live
  Qwen2.5-0.5B-Instruct call), but generating them is not part of what's
  being measured — this isolates transport/codec cost from compute cost,
  which is the actual question ("is the wire protocol worth it") rather
  than a model speed test.

## What this does and doesn't prove

**Does prove**: for two processes on the same Windows machine, in Python,
sending small structured messages back and forth, AICL's shared-memory
ring transport is dramatically faster than FastAPI over HTTPS — real,
reproducible, order-of-magnitude numbers, not a synthetic microbenchmark
with an unfair payload.

**Doesn't prove**:
- That HTTPS/FastAPI is "bad" — it's solving a different problem. AICL's
  ring buffer requires both ends on the same machine with access to a
  shared memory segment; FastAPI can talk to a module on another machine,
  in a container, behind a load balancer, written in any language with an
  HTTP client. That flexibility has a cost, and this benchmark measures
  exactly that cost — it's not free, but it's also not what AICL is for.
- That this reflects the current product. Orcha's actual internal module
  communication today is same-process Python function calls (`AgentNode`
  calling `ToolExecutor` directly) — no HTTP hop exists there to replace.
  Orcha's FastAPI server is the boundary to the Electron desktop frontend,
  a genuine separate process across which AICL's *current* Python
  implementation could plausibly compete, but nothing here is wired into
  that path yet. This is a capability demonstration, not a shipped
  optimization.
- Cross-platform numbers. Everything here ran on Windows. Linux loopback
  TCP has less syscall overhead than Windows' — FastAPI's numbers would
  likely improve somewhat on Linux; AICL's shared-memory path would likely
  also improve. The *ratio* between them is not guaranteed to hold exactly,
  though the underlying mechanism gap (syscalls + TLS + JSON vs a shared
  ring buffer) doesn't go away on any OS.
- Raw C/C++ shared-memory IPC numbers. Independently reported C-level
  SPSC shared-memory benchmarks (no interpreter, no protocol encode/decode)
  can reach double-digit nanoseconds cross-process. Python's interpreter
  overhead (object allocation, `struct.pack`/`unpack`, reference counting)
  puts a floor under what this implementation can reach that a compiled
  language wouldn't have — 16.3µs cross-process in Python is a fair number
  for what it is, not a ceiling on what AICL's protocol itself could do in
  a compiled cross-process implementation (which doesn't exist yet — see
  [README.md](README.md)'s wire-format-status section on the Python/Rust
  format mismatch).

## Reproducing all of this

```bash
cd benchmarks/https_vs_binary
pip install -r requirements.txt
python gen_cert.py

# Cross-process request/response
python cross_process_client.py 5000

# Cross-process HTTPS (start server, then client, separate terminals)
python -m uvicorn server:app --host 127.0.0.1 --port 8443 --ssl-keyfile key.pem --ssl-certfile cert.pem --log-level warning
python client.py 5000

# Streaming (AICL)
python streaming_aicl_client.py 200

# Streaming (SSE — start server, then client, separate terminals)
python -m uvicorn streaming_sse_server:app --host 127.0.0.1 --port 8443 --ssl-keyfile key.pem --ssl-certfile cert.pem --log-level warning
python streaming_sse_client.py 200

# End-to-end with real model inference (needs a small local GGUF model —
# see e2e_combined.py for the exact llama-server command; start it on port
# 8099, and e2e_sse_relay_server.py via uvicorn on port 8443, first)
"../../.venv/Scripts/python.exe" e2e_combined.py 40

# Same-process Rust
cd ../../core-rust
cargo run --release --example bench_local_path
```
