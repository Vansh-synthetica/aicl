"""AICL-BIN identity types and reference types."""
from __future__ import annotations

IDENTITY_MODULE: int = 0x01
IDENTITY_AGENT: int = 0x02
IDENTITY_MODEL: int = 0x03
IDENTITY_RUNTIME: int = 0x04
IDENTITY_SYSTEM: int = 0x05
IDENTITY_EXTERNAL: int = 0x06

IDENTITY_NAMES: dict[int, str] = {
    IDENTITY_MODULE: "module",
    IDENTITY_AGENT: "agent",
    IDENTITY_MODEL: "model",
    IDENTITY_RUNTIME: "runtime",
    IDENTITY_SYSTEM: "system",
    IDENTITY_EXTERNAL: "external",
}

# ─── QoS constants ──────────────────────────────────────────

PRIORITY_CRITICAL: int = 0
PRIORITY_HIGH: int = 1
PRIORITY_NORMAL: int = 2
PRIORITY_LOW: int = 3
PRIORITY_BACKGROUND: int = 4

RELIABILITY_AT_MOST_ONCE: int = 0
RELIABILITY_AT_LEAST_ONCE: int = 1
RELIABILITY_EXACTLY_ONCE: int = 2

ORDERING_UNORDERED: int = 0
ORDERING_FIFO: int = 1
ORDERING_STRICT: int = 2

DELIVERY_BEST_EFFORT: int = 0
DELIVERY_GUARANTEED: int = 1

# ─── Blob reference types ───────────────────────────────────

REF_SHMEM: int = 0x01
REF_FILE: int = 0x02
REF_S3: int = 0x03
REF_URL: int = 0x04
REF_GPU_BUFFER: int = 0x05

# ─── Authentication methods ─────────────────────────────────

AUTH_HMAC_SHA256: int = 0x01
AUTH_ED25519: int = 0x02
AUTH_TLS_CLIENT_CERT: int = 0x03