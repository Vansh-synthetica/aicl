# AICL — Adaptive Inter-Module Communication Language

AICL is a compact binary wire protocol for AI-module-to-AI-module
communication: a typed packet format, a streaming decoder for partial
buffers, a semantic layer mapping model intents/actions onto the wire, and
a Python SDK that can talk either natively (via a compiled Rust core) or
over HTTP.

```python
from aicl import encode, decode, Packet
from aicl.bin.types import Symbol
from aicl.bin.symbol_types import S_STRING

pkt = Packet(symbols=[Symbol(S_STRING, "hello")])
wire = encode(pkt)
assert decode(wire).symbols[0].value == "hello"
```

## Install

```bash
pip install localhousellm-aicl
```

Zero third-party dependencies — pure standard library. For development:

```bash
git clone https://github.com/LocalHouseLLM/AICL
cd AICL
python -m venv .venv
.venv\Scripts\activate      # .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"
pytest
```

## What's in the box

- **`aicl.bin`** — the binary codec: `encode`/`decode`, `Packet`,
  `PacketView`, `StreamingDecoder` for partial/chunked buffers, typed
  symbols, and a CRC32 trailer for payload integrity.
- **`aicl.semantic`** — `ModelIntent`/`ModelAction`/`ModelObservation`/
  `ModelRequest`/`ModelResult`, a `SemanticAdapter` bridging model output to
  the wire, `AICLGrammar` for intent validation, and a `GateCheck`/
  `GateResult` safety gate for inbound/outbound packets.
- **`aicl.sl`** — a human-readable debug formatter (`format_packet`,
  `format_symbol`, `format_tlv`, `format_view`) for inspecting packets on
  the wire — never emitted on the wire itself, display-only.
- **`aicl.sdk`** — the developer-facing runtime (`AICLRuntime`, `Model`,
  structured results, cancellation, diagnostics). Native transport
  delegates the hot path (codec, routing, shared-memory sync, scheduling)
  to a compiled Rust core; HTTP transport is available as an explicit
  opt-in fallback that needs nothing compiled.
- **`aicl.transport`** — connection/session/address plumbing shared by both
  transports.
- **`core-rust`** / **`core-cpp`** / **`native-cpp`** — native
  implementations. `core-rust` is the reference the ISA spec is written
  against.

## Native transport requires a compiled Rust core

`aicl.sdk`'s native (default) transport loads `aicl_core.dll`/`.so`/`.dylib`
via FFI (`aicl/sdk/_ffi.py`) — it looks in `core-rust/target/release/`,
`core-rust/target/debug/`, or `$AICL_CORE_LIB`. Build it with:

```bash
cd core-rust
cargo build --release
cargo test --release   # 40 tests
```

Without a compiled core, use the HTTP transport instead
(`AICLRuntime(http=True, http_url="...")`) or work directly against
`aicl.bin`/`aicl.semantic`, which are pure Python and need nothing compiled.

## Benchmarks

Two real OS processes, genuine shared-memory IPC, the same `aicl.bin`
codec this repo ships, compared against FastAPI over HTTPS doing the same
job:

| Scenario | AICL | FastAPI/HTTPS | Difference |
|---|---|---|---|
| Request/response (cross-process, no inference) | 16.3µs avg | 1,063µs avg | ~65× faster |
| Streaming, 51 chunks/response (cross-process, no inference) | 452µs/stream | 14,005µs/stream | ~31× faster |
| End-to-end, real inference, AICL over HTTP (40 real tokens) | 952ms avg | 964ms avg | ~1% faster |
| **End-to-end, real inference, AICL fully in-process (no network at all)** | **1,061.5ms avg (−62.6ms vs. no-relay)** | — | **further ~12ms faster than AICL-over-HTTP** |

The pure-transport rows isolate transport cost from model compute — real,
but they overstate what a user actually feels. The middle row is what
matters with the network still involved at all: AICL adds no measurable
overhead over calling the model directly, while HTTPS/SSE adds a genuine
but tiny ~5-78ms depending on the run. The **last row answers a different
question — can the network be removed entirely** — by having the relay
load the model directly (via `llama-cpp-python`, no HTTP/TCP/`localhost`
anywhere) instead of calling a separate server. It measurably wins, on
top of everything else.

Full methodology, every caveat, and the debugging story behind that last
number are in [BENCHMARKS.md](BENCHMARKS.md) — including two real,
fixable inefficiencies found along the way (DNS-resolving `"localhost"`
instead of using `127.0.0.1`, and reconstructing a fresh HTTP client per
call instead of reusing one) that turned out to cost every path in this
benchmark ~40% of its total time, unrelated to AICL vs. HTTPS at all.

## Wire format status — read before assuming cross-language compatibility

**`aicl.bin` (Python) and `core-rust` currently implement two different wire
formats**, not the same protocol in two languages. They share the magic
bytes (`b"AICL"`) and not much else: different header sizes (Python's is
64 bytes; the spec and Rust use 56), different opcode taxonomies, different
operand/symbol type tag sets. See [`WIRE_FORMAT_AUDIT.md`](WIRE_FORMAT_AUDIT.md)
for the full field-by-field comparison against
[`protocol/AICL-ISA.md`](protocol/AICL-ISA.md), the normative spec.

Practically: a Python module using `aicl.bin` and a Rust module using
`core-rust` cannot decode each other's packets today. `aicl.bin` is being
brought in line with the ISA spec (and Rust); until that lands, treat
`aicl.bin` as Python-to-Python only, and `core-rust` as the spec-compliant
implementation to build cross-language interop against.

## Testing

```bash
pytest tests/
```

92 Python tests, covering the binary codec, error handling
(truncated/corrupt packets, checksum mismatches, streaming with partial
buffers), the semantic layer, the SDK surface (capabilities, cancellation,
results, transports), and the debug formatter — pure Python, no native
build required. Plus 40 Rust tests (`cd core-rust && cargo test --release`)
covering the native codec, the lock-free ring buffer, the FFI boundary, and
capability dispatch.

## License

MPL-2.0 — see [LICENSE](LICENSE).
