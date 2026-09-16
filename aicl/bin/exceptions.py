"""AICL-BIN exception types."""
from __future__ import annotations

__all__ = [
    "AICLBinError",
    "HeaderError",
    "TLVError",
    "SymbolError",
    "EncodeError",
    "DecodeError",
    "ChecksumError",
    "TruncatedPacketError",
    "InvalidPacketError",
]


class AICLBinError(Exception):
    """Base exception for AICL-BIN errors."""


class HeaderError(AICLBinError):
    """Header parsing or validation error."""


class TLVError(AICLBinError):
    """TLV parsing or validation error."""


class SymbolError(AICLBinError):
    """Symbol encoding/decoding error."""


class EncodeError(AICLBinError):
    """Encoding error (value out of range, type mismatch, etc.)."""


class DecodeError(AICLBinError):
    """Decoding error (malformed bytes, invalid magic, etc.)."""


class ChecksumError(AICLBinError):
    """CRC32 checksum validation failed."""


class TruncatedPacketError(DecodeError):
    """Packet is truncated (fewer bytes than header declares)."""


class InvalidPacketError(DecodeError):
    """Packet is structurally invalid (bad TLV ordering, version, etc.)."""
