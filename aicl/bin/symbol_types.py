"""AICL-BIN symbol type tags."""
from __future__ import annotations

S_STRING: int = 0x01
"""UTF-8 text value."""

S_NUMBER: int = 0x02
"""64-bit floating point number (float64)."""

S_INTEGER: int = 0x03
"""64-bit signed integer (int64)."""

S_BOOLEAN: int = 0x04
"""Boolean value."""

S_TAG: int = 0x05
"""Categorical label or class name."""

S_KEY: int = 0x06
"""Reference key to a data element or memory slot."""

S_VECTOR: int = 0x07
"""Ordered list of symbols (Vector type)."""

S_REFERENCE: int = 0x08
"""Reference to another module's output field (e.g., "nlp.output.label")."""

S_JSON: int = 0x09
"""Inline JSON value (UTF-8)."""

S_DATETIME: int = 0x0A
"""Date/time (epoch millis int64 + nanoseconds int64)."""

S_UUID: int = 0x0B
"""UUID value (16 bytes)."""

S_NULL: int = 0x0C
"""Null/nil value."""

S_BLOB: int = 0x0D
"""Binary blob with 4-byte length prefix."""

SYMBOL_TYPE_NAMES: dict[int, str] = {
    S_STRING: "S",
    S_NUMBER: "N",
    S_INTEGER: "I",
    S_BOOLEAN: "B",
    S_TAG: "T",
    S_KEY: "K",
    S_VECTOR: "V",
    S_REFERENCE: "R",
    S_JSON: "J",
    S_DATETIME: "D",
    S_UUID: "U",
    S_NULL: "NULL",
    S_BLOB: "BLOB",
}