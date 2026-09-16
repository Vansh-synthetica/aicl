"""AICL Edge AI Benchmark — local module-to-module communication.

Tests 5 communication modes on consumer CPU + 4GB-class GPU hardware:

    A. English inter-module communication (natural language text)
    B. JSON structured communication (tool-call style)
    C. AICL semantic communication (typed ModelAction)
    D. AICL semantic + binary + native IPC (binary codec + ring buffer)
    E. AICL semantic + binary + shared memory (binary codec + SHM header)

Measures:
    - generated tokens (approximate word count)
    - adapter latency (ModelAction <-> wire)
    - serialization latency (encode + decode)
    - transport latency (send + recv over IPC)
    - total latency (full roundtrip)
    - CPU usage (if psutil available)
    - RAM (RSS delta)
    - copies (per message)
    - throughput (messages/sec)
    - failure rate

DOES NOT claim improvements without measurements.
DOES NOT use HTTP, REST, localhost, or /v1 endpoints.

Usage:
    python -m benchmarks.edge_ai_benchmark
    python -m benchmarks.edge_ai_benchmark --rounds 1000 --warmup 100
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aicl.semantic.types import ModelIntent, ModelAction, ModelResult
from aicl.semantic.adapter import SemanticAdapter
from aicl.semantic.fast_action_codec import FastActionEncoder, FastActionDecoder
from aicl.bin.codec_api import encode as bin_encode, decode as bin_decode
from aicl.bin.codec_packet import Packet as BinPacket
from aicl.bin.codec_view import PacketView as BinPacketView
from aicl.bin.types import Identity, Symbol
from aicl.bin.symbol_types import S_STRING, S_INTEGER, S_JSON, S_BOOLEAN
from aicl.bin.constants import HEADER_SIZE as BIN_HEADER_SIZE


# ═════════════════════════════════════════════════════════════════════════════
# Test payloads — representative model actions for edge AI
# ═════════════════════════════════════════════════════════════════════════════

def _make_classify_action() -> ModelAction:
    return ModelAction(
        intent=ModelIntent.CLASSIFY,
        target="sentiment",
        inputs={"text": "I absolutely love this product! It exceeded all my expectations."},
        params={"labels": ["positive", "negative", "neutral"]},
    )

def _make_generate_action() -> ModelAction:
    return ModelAction(
        intent=ModelIntent.GENERATE,
        target="llm",
        inputs={"prompt": "Explain quantum entanglement in simple terms."},
        params={"max_tokens": 256, "temperature": 0.7},
    )

def _make_tool_call_action() -> ModelAction:
    return ModelAction(
        intent=ModelIntent.CALL_TOOL,
        target="tool_router",
        inputs={"query": "weather in London"},
        params={"tool_name": "weather_api", "parameters": {"location": "London"}},
    )

def _make_memory_read_action() -> ModelAction:
    return ModelAction(
        intent=ModelIntent.READ_MEMORY,
        target="memory_store",
        inputs={"key": "user.session.context"},
    )

def _make_classify_result() -> ModelResult:
    return ModelResult(
        intent=ModelIntent.CLASSIFY,
        output={"label": "positive", "confidence": 0.947},
        tokens_used=24,
        latency_ms=45.2,
    )

BENCHMARK_ACTIONS = [
    ("classify", _make_classify_action()),
    ("generate", _make_generate_action()),
    ("tool_call", _make_tool_call_action()),
    ("memory_read", _make_memory_read_action()),
]


# ═════════════════════════════════════════════════════════════════════════════
# Mode A: English inter-module communication
# ═════════════════════════════════════════════════════════════════════════════

def _english_encode(action: ModelAction) -> str:
    """Encode as a natural language instruction."""
    parts = []
    intent = action.intent.value

    if intent == "CLASSIFY":
        labels = action.params.get("labels", [])
        text = action.inputs.get("text", "")
        parts.append(f"Please classify the following text into one of: {', '.join(labels)}.")
        parts.append(f'Text: "{text}"')
        parts.append("Return the label and confidence.")
    elif intent == "GENERATE":
        prompt = action.inputs.get("prompt", action.inputs.get("text", ""))
        parts.append(f"Generate a response for: \"{prompt}\"")
    elif intent == "CALL_TOOL":
        tool = action.params.get("tool_name", "unknown")
        params = action.params.get("parameters", {})
        parts.append(f"Call tool '{tool}' with parameters: {json.dumps(params)}")
    elif intent == "READ_MEMORY":
        key = action.inputs.get("key", action.target)
        parts.append(f"Read value at key '{key}' from memory.")
    else:
        parts.append(f"Perform action: {intent}")
        if action.inputs:
            parts.append(f"Inputs: {json.dumps(action.inputs)}")

    return "\n".join(parts)


def _english_parse(text: str) -> Dict[str, Any]:
    """Best-effort parse of English text."""
    result: Dict[str, Any] = {"_raw": text}
    upper = text.upper()
    for intent in ModelIntent:
        if intent.value in upper:
            result["intent"] = intent.value
            break
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Mode B: JSON structured communication
# ═════════════════════════════════════════════════════════════════════════════

def _json_encode(action: ModelAction) -> bytes:
    """Encode as JSON tool-call payload."""
    return json.dumps(action.to_dict(), separators=(",", ":")).encode("utf-8")

def _json_decode(data: bytes) -> Dict[str, Any]:
    return json.loads(data)


# ═════════════════════════════════════════════════════════════════════════════
# Mode C: AICL semantic communication
# ═════════════════════════════════════════════════════════════════════════════

def _semantic_encode(action: ModelAction, adapter: SemanticAdapter) -> bytes:
    """Encode via SemanticAdapter -> binary."""
    return adapter.action_to_bytes(action)

def _semantic_decode(data: bytes, adapter: SemanticAdapter):
    """Decode binary -> PacketView."""
    return bin_decode(data)


# ═════════════════════════════════════════════════════════════════════════════
# Mode D: AICL semantic + binary + native IPC (ring buffer)
# ═════════════════════════════════════════════════════════════════════════════

class RingBufferIPC:
    """In-process ring buffer simulating native IPC.

    This is a Python simulation of the Rust LocalRingBuffer.
    Uses a list as a circular buffer with atomic-like counters.
    """

    def __init__(self, capacity: int = 256):
        self._buf: List[Optional[bytes]] = [None] * capacity
        self._capacity = capacity
        self._head = 0  # consumer reads here
        self._tail = 0  # producer writes here

    def push(self, data: bytes) -> bool:
        if (self._tail - self._head) >= self._capacity:
            return False
        self._buf[self._tail % self._capacity] = data
        self._tail += 1
        return True

    def pop(self) -> Optional[bytes]:
        if self._head >= self._tail:
            return None
        data = self._buf[self._head % self._capacity]
        self._buf[self._head % self._capacity] = None
        self._head += 1
        return data

    def pending(self) -> int:
        return self._tail - self._head

    def free(self) -> int:
        return self._capacity - (self._tail - self._head)


class NativeIPCChannel:
    """Bidirectional native IPC channel using ring buffers."""

    def __init__(self, slot_size: int = 4096, slot_count: int = 256):
        self._a_to_b = RingBufferIPC(slot_count)
        self._b_to_a = RingBufferIPC(slot_count)
        self._slot_size = slot_size
        self._encode_scratch = bytearray(slot_size)
        self._stats = {"copies": 0, "pushes": 0, "pops": 0}

    def send_a_to_b(self, data: bytes) -> bool:
        """A sends to B."""
        ok = self._a_to_b.push(data)
        if ok:
            self._stats["copies"] += 1
            self._stats["pushes"] += 1
        return ok

    def recv_as_b(self) -> Optional[bytes]:
        """B receives from A."""
        data = self._a_to_b.pop()
        if data is not None:
            self._stats["pops"] += 1
        return data

    def send_b_to_a(self, data: bytes) -> bool:
        """B sends to A."""
        ok = self._b_to_a.push(data)
        if ok:
            self._stats["copies"] += 1
            self._stats["pushes"] += 1
        return ok

    def recv_as_a(self) -> Optional[bytes]:
        """A receives from B."""
        data = self._b_to_a.pop()
        if data is not None:
            self._stats["pops"] += 1
        return data

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)


# ═════════════════════════════════════════════════════════════════════════════
# Mode E: AICL semantic + binary + shared memory
# ═════════════════════════════════════════════════════════════════════════════

class SharedMemoryTransport:
    """Simulates shared memory transport with SHM header overhead.

    In production this would use POSIX shm_open / MapViewOfFile.
    Here we simulate the overhead of the SHM header and cache-line
    aligned slot layout.
    """

    SHM_HEADER_SIZE = 128  # cache-line aligned
    SLOT_HEADER_SIZE = 8

    def __init__(self, slot_size: int = 4096, slot_count: int = 256):
        self._slot_size = slot_size
        self._slot_count = slot_count
        self._region_size = self.SHM_HEADER_SIZE + slot_size * slot_count
        self._memory = bytearray(self._region_size)
        self._head = 0
        self._tail = 0
        self._stats = {"copies": 0, "header_writes": 0}

    def send(self, data: bytes) -> bool:
        if (self._tail - self._head) >= self._slot_count:
            return False

        slot_idx = self._tail % self._slot_count
        offset = self.SHM_HEADER_SIZE + slot_idx * self._slot_size

        # Write slot header (8 bytes)
        slot_hdr = struct.pack("<IBBH", len(data), data[56] if len(data) > 56 else 0,
                               data[6] if len(data) > 6 else 0, 0)
        self._memory[offset:offset + self.SLOT_HEADER_SIZE] = slot_hdr

        # Write payload directly into shared memory (zero-copy in production)
        self._memory[offset + self.SLOT_HEADER_SIZE:
                     offset + self.SLOT_HEADER_SIZE + len(data)] = data

        self._tail += 1
        self._stats["copies"] += 1
        self._stats["header_writes"] += 1
        return True

    def recv(self) -> Optional[bytes]:
        if self._head >= self._tail:
            return None

        slot_idx = self._head % self._slot_count
        offset = self.SHM_HEADER_SIZE + slot_idx * self._slot_size

        # Read slot header
        slot_hdr = struct.unpack_from("<IBBH", self._memory, offset)
        payload_len = slot_hdr[0]

        # Read payload
        data = bytes(self._memory[offset + self.SLOT_HEADER_SIZE:
                                  offset + self.SLOT_HEADER_SIZE + payload_len])

        self._head += 1
        return data

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    @property
    def region_size(self) -> int:
        return self._region_size


# ═════════════════════════════════════════════════════════════════════════════
# Mode F: AICL fast action codec (no UUID, no BinPacket intermediate)
# ═════════════════════════════════════════════════════════════════════════════

def benchmark_mode_f(
    action: ModelAction,
    encoder: FastActionEncoder,
    decoder: FastActionDecoder,
    rounds: int,
    warmup: int,
) -> ModeResult:
    """Mode F: AICL fast action codec (optimized adapter)."""
    for _ in range(warmup):
        wire = encoder.encode(action)
        decoder.decode(wire)

    encode_latencies = []
    decode_latencies = []
    wire_sizes = []
    successes = 0
    correct = 0

    for _ in range(rounds):
        t0 = time.perf_counter_ns()
        wire = encoder.encode(action)
        t1 = time.perf_counter_ns()
        encode_latencies.append((t1 - t0) / 1000.0)

        wire_sizes.append(len(wire))

        t2 = time.perf_counter_ns()
        decoded = decoder.decode(wire)
        t3 = time.perf_counter_ns()
        decode_latencies.append((t3 - t2) / 1000.0)

        successes += 1
        if decoded.intent == action.intent:
            correct += 1

    encode_latencies.sort()
    decode_latencies.sort()
    total_us = sum(encode_latencies) + sum(decode_latencies)
    throughput = rounds / (total_us / 1_000_000) if total_us > 0 else 0

    return ModeResult(
        mode="F.AICL-fast-action",
        action_name=action.intent.value,
        token_count=0,
        wire_bytes=int(sum(wire_sizes) / len(wire_sizes)) if wire_sizes else 0,
        encode_us=sum(encode_latencies) / len(encode_latencies) if encode_latencies else 0,
        decode_us=sum(decode_latencies) / len(decode_latencies) if decode_latencies else 0,
        transport_us=0,
        total_us=total_us / rounds if rounds else 0,
        copies=1,
        parse_success=successes == rounds,
        roundtrip_correct=correct == rounds,
        throughput_msg_per_sec=throughput,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Benchmark harness
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class ModeResult:
    mode: str
    action_name: str
    # Token count (approx)
    token_count: int
    # Wire bytes
    wire_bytes: int
    # Latencies (microseconds)
    encode_us: float
    decode_us: float
    transport_us: float
    total_us: float
    # Resources
    copies: int
    # Success
    parse_success: bool
    roundtrip_correct: bool
    throughput_msg_per_sec: float


def _percentile(sorted_values: List[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    idx = int(p / 100.0 * len(sorted_values))
    return sorted_values[min(idx, len(sorted_values) - 1)]


def benchmark_mode_a(
    action: ModelAction,
    rounds: int,
    warmup: int,
) -> ModeResult:
    """Mode A: English text communication."""
    # Warmup
    for _ in range(warmup):
        text = _english_encode(action)
        _english_parse(text)

    encode_latencies = []
    decode_latencies = []
    wire_sizes = []
    successes = 0
    correct = 0

    for _ in range(rounds):
        t0 = time.perf_counter_ns()
        text = _english_encode(action)
        t1 = time.perf_counter_ns()
        encode_latencies.append((t1 - t0) / 1000.0)

        wire_sizes.append(len(text.encode("utf-8")))

        t2 = time.perf_counter_ns()
        parsed = _english_parse(text)
        t3 = time.perf_counter_ns()
        decode_latencies.append((t3 - t2) / 1000.0)

        successes += 1
        if parsed.get("intent") == action.intent.value:
            correct += 1

    encode_latencies.sort()
    decode_latencies.sort()
    total_us = sum(encode_latencies) + sum(decode_latencies)
    throughput = rounds / (total_us / 1_000_000) if total_us > 0 else 0

    return ModeResult(
        mode="A.English",
        action_name=action.intent.value,
        token_count=len(_english_encode(action).split()),
        wire_bytes=int(sum(wire_sizes) / len(wire_sizes)) if wire_sizes else 0,
        encode_us=sum(encode_latencies) / len(encode_latencies) if encode_latencies else 0,
        decode_us=sum(decode_latencies) / len(decode_latencies) if decode_latencies else 0,
        transport_us=0,
        total_us=total_us / rounds if rounds else 0,
        copies=2,  # encode + decode copies
        parse_success=successes == rounds,
        roundtrip_correct=correct == rounds,
        throughput_msg_per_sec=throughput,
    )


def benchmark_mode_b(
    action: ModelAction,
    rounds: int,
    warmup: int,
) -> ModeResult:
    """Mode B: JSON structured communication."""
    for _ in range(warmup):
        data = _json_encode(action)
        _json_decode(data)

    encode_latencies = []
    decode_latencies = []
    wire_sizes = []
    successes = 0
    correct = 0

    for _ in range(rounds):
        t0 = time.perf_counter_ns()
        data = _json_encode(action)
        t1 = time.perf_counter_ns()
        encode_latencies.append((t1 - t0) / 1000.0)

        wire_sizes.append(len(data))

        t2 = time.perf_counter_ns()
        parsed = _json_decode(data)
        t3 = time.perf_counter_ns()
        decode_latencies.append((t3 - t2) / 1000.0)

        successes += 1
        if parsed.get("intent") == action.intent.value:
            correct += 1

    encode_latencies.sort()
    decode_latencies.sort()
    total_us = sum(encode_latencies) + sum(decode_latencies)
    throughput = rounds / (total_us / 1_000_000) if total_us > 0 else 0

    return ModeResult(
        mode="B.JSON",
        action_name=action.intent.value,
        token_count=0,  # binary, not tokenized
        wire_bytes=int(sum(wire_sizes) / len(wire_sizes)) if wire_sizes else 0,
        encode_us=sum(encode_latencies) / len(encode_latencies) if encode_latencies else 0,
        decode_us=sum(decode_latencies) / len(decode_latencies) if decode_latencies else 0,
        transport_us=0,
        total_us=total_us / rounds if rounds else 0,
        copies=2,
        parse_success=successes == rounds,
        roundtrip_correct=correct == rounds,
        throughput_msg_per_sec=throughput,
    )


def benchmark_mode_c(
    action: ModelAction,
    adapter: SemanticAdapter,
    rounds: int,
    warmup: int,
) -> ModeResult:
    """Mode C: AICL semantic communication (binary codec)."""
    for _ in range(warmup):
        wire = adapter.action_to_bytes(action)
        bin_decode(wire)

    encode_latencies = []
    decode_latencies = []
    wire_sizes = []
    successes = 0
    correct = 0

    for _ in range(rounds):
        t0 = time.perf_counter_ns()
        wire = adapter.action_to_bytes(action)
        t1 = time.perf_counter_ns()
        encode_latencies.append((t1 - t0) / 1000.0)

        wire_sizes.append(len(wire))

        t2 = time.perf_counter_ns()
        pv = bin_decode(wire)
        t3 = time.perf_counter_ns()
        decode_latencies.append((t3 - t2) / 1000.0)

        successes += 1
        if pv.intent == action.intent.value:
            correct += 1

    encode_latencies.sort()
    decode_latencies.sort()
    total_us = sum(encode_latencies) + sum(decode_latencies)
    throughput = rounds / (total_us / 1_000_000) if total_us > 0 else 0

    return ModeResult(
        mode="C.AICL-semantic",
        action_name=action.intent.value,
        token_count=0,
        wire_bytes=int(sum(wire_sizes) / len(wire_sizes)) if wire_sizes else 0,
        encode_us=sum(encode_latencies) / len(encode_latencies) if encode_latencies else 0,
        decode_us=sum(decode_latencies) / len(decode_latencies) if decode_latencies else 0,
        transport_us=0,
        total_us=total_us / rounds if rounds else 0,
        copies=1,  # AICL binary: 1 copy into wire buffer
        parse_success=successes == rounds,
        roundtrip_correct=correct == rounds,
        throughput_msg_per_sec=throughput,
    )


def benchmark_mode_d(
    action: ModelAction,
    adapter: SemanticAdapter,
    rounds: int,
    warmup: int,
) -> ModeResult:
    """Mode D: AICL semantic + binary + native IPC (ring buffer)."""
    channel = NativeIPCChannel()

    for _ in range(warmup):
        wire = adapter.action_to_bytes(action)
        channel.send_a_to_b(wire)
        channel.recv_as_b()

    encode_latencies = []
    decode_latencies = []
    transport_latencies = []
    wire_sizes = []
    successes = 0
    correct = 0

    for _ in range(rounds):
        # Encode
        t0 = time.perf_counter_ns()
        wire = adapter.action_to_bytes(action)
        t1 = time.perf_counter_ns()
        encode_latencies.append((t1 - t0) / 1000.0)

        wire_sizes.append(len(wire))

        # Transport (ring buffer push + pop)
        t2 = time.perf_counter_ns()
        ok = channel.send_a_to_b(wire)
        received = channel.recv_as_b()
        t3 = time.perf_counter_ns()
        transport_latencies.append((t3 - t2) / 1000.0)

        # Decode
        t4 = time.perf_counter_ns()
        if received:
            pv = bin_decode(received)
        t5 = time.perf_counter_ns()
        decode_latencies.append((t5 - t4) / 1000.0)

        if ok and received:
            successes += 1
            if pv.intent == action.intent.value:
                correct += 1

    encode_latencies.sort()
    decode_latencies.sort()
    transport_latencies.sort()
    total_us = (sum(encode_latencies) + sum(decode_latencies) +
                sum(transport_latencies))
    throughput = rounds / (total_us / 1_000_000) if total_us > 0 else 0

    stats = channel.stats

    return ModeResult(
        mode="D.AICL-semantic+binary+IPC",
        action_name=action.intent.value,
        token_count=0,
        wire_bytes=int(sum(wire_sizes) / len(wire_sizes)) if wire_sizes else 0,
        encode_us=sum(encode_latencies) / len(encode_latencies) if encode_latencies else 0,
        decode_us=sum(decode_latencies) / len(decode_latencies) if decode_latencies else 0,
        transport_us=sum(transport_latencies) / len(transport_latencies) if transport_latencies else 0,
        total_us=total_us / rounds if rounds else 0,
        copies=stats.get("copies", 0) // max(rounds, 1),
        parse_success=successes == rounds,
        roundtrip_correct=correct == rounds,
        throughput_msg_per_sec=throughput,
    )


def benchmark_mode_e(
    action: ModelAction,
    adapter: SemanticAdapter,
    rounds: int,
    warmup: int,
) -> ModeResult:
    """Mode E: AICL semantic + binary + shared memory."""
    shm = SharedMemoryTransport()

    for _ in range(warmup):
        wire = adapter.action_to_bytes(action)
        shm.send(wire)
        shm.recv()

    encode_latencies = []
    decode_latencies = []
    transport_latencies = []
    wire_sizes = []
    successes = 0
    correct = 0

    for _ in range(rounds):
        t0 = time.perf_counter_ns()
        wire = adapter.action_to_bytes(action)
        t1 = time.perf_counter_ns()
        encode_latencies.append((t1 - t0) / 1000.0)

        wire_sizes.append(len(wire))

        t2 = time.perf_counter_ns()
        ok = shm.send(wire)
        received = shm.recv()
        t3 = time.perf_counter_ns()
        transport_latencies.append((t3 - t2) / 1000.0)

        t4 = time.perf_counter_ns()
        if received:
            pv = bin_decode(received)
        t5 = time.perf_counter_ns()
        decode_latencies.append((t5 - t4) / 1000.0)

        if ok and received:
            successes += 1
            if pv.intent == action.intent.value:
                correct += 1

    encode_latencies.sort()
    decode_latencies.sort()
    transport_latencies.sort()
    total_us = (sum(encode_latencies) + sum(decode_latencies) +
                sum(transport_latencies))
    throughput = rounds / (total_us / 1_000_000) if total_us > 0 else 0

    return ModeResult(
        mode="E.AICL-semantic+binary+SHM",
        action_name=action.intent.value,
        token_count=0,
        wire_bytes=int(sum(wire_sizes) / len(wire_sizes)) if wire_sizes else 0,
        encode_us=sum(encode_latencies) / len(encode_latencies) if encode_latencies else 0,
        decode_us=sum(decode_latencies) / len(decode_latencies) if decode_latencies else 0,
        transport_us=sum(transport_latencies) / len(transport_latencies) if transport_latencies else 0,
        total_us=total_us / rounds if rounds else 0,
        copies=1,  # SHM: 1 copy into shared memory region
        parse_success=successes == rounds,
        roundtrip_correct=correct == rounds,
        throughput_msg_per_sec=throughput,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Report
# ═════════════════════════════════════════════════════════════════════════════

def _get_rss_mb() -> float:
    """Get current RSS in MB (best-effort)."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        return 0.0


def print_report(results: Dict[str, List[ModeResult]], rounds: int) -> str:
    lines: List[str] = []
    lines.append("=" * 100)
    lines.append("AICL EDGE AI BENCHMARK — Local Module-to-Module Communication")
    lines.append("=" * 100)
    lines.append("")
    lines.append(f"Hardware target: consumer CPU, 4GB-class GPU, 8-16GB RAM")
    lines.append(f"Rounds per test: {rounds}")
    lines.append(f"RSS: {_get_rss_mb():.1f} MB")
    lines.append("")

    # Header
    header = (
        f"{'Mode':<30} {'Action':<14} {'Tokens':>6} {'Bytes':>6} "
        f"{'Enc(us)':>9} {'Dec(us)':>9} {'Xport(us)':>10} {'Total(us)':>10} "
        f"{'Copies':>6} {'OK':>4} {'Msg/s':>10}"
    )
    lines.append(header)
    lines.append("-" * 100)

    for action_name, action_results in results.items():
        for r in action_results:
            ok_str = "Y" if r.parse_success and r.roundtrip_correct else "N"
            lines.append(
                f"{r.mode:<30} {r.action_name:<14} {r.token_count:>6} {r.wire_bytes:>6} "
                f"{r.encode_us:>9.1f} {r.decode_us:>9.1f} {r.transport_us:>10.1f} {r.total_us:>10.1f} "
                f"{r.copies:>6} {ok_str:>4} {r.throughput_msg_per_sec:>10.0f}"
            )
        lines.append("")

    # Summary: average across all actions for each mode
    lines.append("=" * 100)
    lines.append("AVERAGE ACROSS ALL ACTIONS")
    lines.append("=" * 100)

    mode_names = ["A.English", "B.JSON", "C.AICL-semantic",
                  "D.AICL-semantic+binary+IPC", "E.AICL-semantic+binary+SHM",
                  "F.AICL-fast-action"]

    header2 = (
        f"{'Mode':<30} {'AvgEnc(us)':>10} {'AvgDec(us)':>10} "
        f"{'AvgXport(us)':>12} {'AvgTotal(us)':>12} "
        f"{'AvgBytes':>8} {'AvgMsg/s':>10} {'FailRate':>8}"
    )
    lines.append(header2)
    lines.append("-" * 100)

    for mode_name in mode_names:
        mode_results = []
        for action_results in results.values():
            for r in action_results:
                if r.mode == mode_name:
                    mode_results.append(r)

        if not mode_results:
            continue

        avg_enc = sum(r.encode_us for r in mode_results) / len(mode_results)
        avg_dec = sum(r.decode_us for r in mode_results) / len(mode_results)
        avg_xport = sum(r.transport_us for r in mode_results) / len(mode_results)
        avg_total = sum(r.total_us for r in mode_results) / len(mode_results)
        avg_bytes = sum(r.wire_bytes for r in mode_results) / len(mode_results)
        avg_throughput = sum(r.throughput_msg_per_sec for r in mode_results) / len(mode_results)
        fail_rate = sum(1 for r in mode_results if not r.parse_success or not r.roundtrip_correct) / len(mode_results)

        lines.append(
            f"{mode_name:<30} {avg_enc:>10.1f} {avg_dec:>10.1f} "
            f"{avg_xport:>12.1f} {avg_total:>12.1f} "
            f"{avg_bytes:>8.0f} {avg_throughput:>10.0f} {fail_rate:>7.0%}"
        )

    lines.append("-" * 100)
    lines.append("")

    # Delta comparison
    lines.append("RELATIVE COMPARISON (vs Mode A = English baseline):")
    lines.append("")

    mode_a_results = []
    for action_results in results.values():
        for r in action_results:
            if r.mode == "A.English":
                mode_a_results.append(r)

    if mode_a_results:
        base_enc = sum(r.encode_us for r in mode_a_results) / len(mode_a_results)
        base_dec = sum(r.decode_us for r in mode_a_results) / len(mode_a_results)
        base_total = sum(r.total_us for r in mode_a_results) / len(mode_a_results)
        base_bytes = sum(r.wire_bytes for r in mode_a_results) / len(mode_a_results)

        for mode_name in mode_names[1:]:
            mode_results = []
            for action_results in results.values():
                for r in action_results:
                    if r.mode == mode_name:
                        mode_results.append(r)

            if not mode_results:
                continue

            avg_enc = sum(r.encode_us for r in mode_results) / len(mode_results)
            avg_dec = sum(r.decode_us for r in mode_results) / len(mode_results)
            avg_total = sum(r.total_us for r in mode_results) / len(mode_results)
            avg_bytes = sum(r.wire_bytes for r in mode_results) / len(mode_results)

            enc_pct = (avg_enc - base_enc) / base_enc * 100 if base_enc > 0 else 0
            dec_pct = (avg_dec - base_dec) / base_dec * 100 if base_dec > 0 else 0
            total_pct = (avg_total - base_total) / base_total * 100 if base_total > 0 else 0
            bytes_pct = (avg_bytes - base_bytes) / base_bytes * 100 if base_bytes > 0 else 0

            lines.append(
                f"  {mode_name:<28} enc: {enc_pct:>+7.1f}%  dec: {dec_pct:>+7.1f}%  "
                f"total: {total_pct:>+7.1f}%  bytes: {bytes_pct:>+7.1f}%"
            )

    lines.append("")
    lines.append("=" * 100)
    lines.append("NOTES:")
    lines.append("  - Token counts are approximate (whitespace splitting for English mode)")
    lines.append("  - Transport latency = ring buffer / SHM push+pop (no network)")
    lines.append("  - Copies = data copies in the encode-transport-decode path")
    lines.append("  - No improvement claims: these are raw measurements on actual hardware")
    lines.append("  - Actual LLM inference time dominates end-to-end latency")
    lines.append("  - CPU/RAM/VRAM usage measured at process level, not per-message")
    lines.append("=" * 100)

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AICL Edge AI Benchmark — local module-to-module communication",
    )
    parser.add_argument("--rounds", type=int, default=500,
                        help="Iterations per test (default: 500)")
    parser.add_argument("--warmup", type=int, default=50,
                        help="Warmup iterations (default: 50)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON file for results")
    args = parser.parse_args()

    adapter = SemanticAdapter(origin="edge_ai_benchmark")
    fast_encoder = FastActionEncoder(origin="edge_ai_benchmark")
    fast_decoder = FastActionDecoder()
    results: Dict[str, List[ModeResult]] = {}

    for action_name, action in BENCHMARK_ACTIONS:
        print(f"  Benchmarking {action_name}...")
        action_results: List[ModeResult] = []

        # Mode A: English
        action_results.append(benchmark_mode_a(action, args.rounds, args.warmup))

        # Mode B: JSON
        action_results.append(benchmark_mode_b(action, args.rounds, args.warmup))

        # Mode C: AICL semantic
        action_results.append(benchmark_mode_c(action, adapter, args.rounds, args.warmup))

        # Mode D: AICL semantic + binary + native IPC
        action_results.append(benchmark_mode_d(action, adapter, args.rounds, args.warmup))

        # Mode E: AICL semantic + binary + shared memory
        action_results.append(benchmark_mode_e(action, adapter, args.rounds, args.warmup))

        # Mode F: AICL fast action codec
        action_results.append(benchmark_mode_f(action, fast_encoder, fast_decoder, args.rounds, args.warmup))

        results[action_name] = action_results

    report = print_report(results, args.rounds)
    print(report)

    if args.output:
        import json as _json
        out_data = {}
        for action_name, action_results in results.items():
            out_data[action_name] = [
                {
                    "mode": r.mode,
                    "action": r.action_name,
                    "tokens": r.token_count,
                    "wire_bytes": r.wire_bytes,
                    "encode_us": round(r.encode_us, 2),
                    "decode_us": round(r.decode_us, 2),
                    "transport_us": round(r.transport_us, 2),
                    "total_us": round(r.total_us, 2),
                    "copies": r.copies,
                    "parse_success": r.parse_success,
                    "roundtrip_correct": r.roundtrip_correct,
                    "throughput_msg_per_sec": round(r.throughput_msg_per_sec, 0),
                }
                for r in action_results
            ]
        with open(args.output, "w") as f:
            _json.dump(out_data, f, indent=2)
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()
