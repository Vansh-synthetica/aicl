"""AICL-BIN encode/decode API."""
from __future__ import annotations
import struct, zlib
import aicl.bin.constants as C
from aicl.bin.header import pack_header
from aicl.bin.codec_packet import Packet
from aicl.bin.codec_view import PacketView
from aicl.bin.exceptions import TruncatedPacketError, ChecksumError
from aicl.bin.validation import validate_header, validate_trailer, validate_flags

__all__ = ["encode", "decode"]


def encode(packet: Packet, checksum: bool = False) -> bytes:
    """Encode a Packet to AICL-BIN wire bytes.

    If checksum=True, appends a 4-byte CRC32 trailer (FLAG_HAS_TRAILER set).
    """
    payload = packet.build_tlvs()
    flags = packet.flags
    if checksum:
        flags |= C.FLAG_HAS_TRAILER
    header = pack_header(
        version=packet.version,
        flags=flags,
        session_id=bytes(packet.session_id),
        message_id=bytes(packet.message_id),
        correlation_id=bytes(packet.correlation_id),
        payload_length=len(payload),
        target_count=len(packet.targets),
    )
    result = header + payload
    if checksum:
        crc = zlib.crc32(result) & 0xFFFFFFFF
        result += struct.pack(">I", crc)
    return bytes(result)


def decode(data) -> PacketView:
    """Decode bytes into a zero-copy PacketView.

    Validates header magic, version, payload bounds, and CRC if present.
    Raises TruncatedPacketError if buffer is too short.
    """
    if isinstance(data, memoryview):
        raw = data
    else:
        raw = memoryview(data if isinstance(data, bytearray) else data)

    if len(raw) < C.HEADER_SIZE:
        raise TruncatedPacketError(
            f"Buffer too short for header: {len(raw)} < {C.HEADER_SIZE}"
        )
    validate_header(raw[:C.HEADER_SIZE])
    validate_flags(struct.unpack_from(">H", raw, 4)[0])

    payload_length = struct.unpack_from(">I", raw, 56)[0]
    hdr_end = C.HEADER_SIZE
    payload_end = hdr_end + payload_length

    if len(raw) < payload_end:
        raise TruncatedPacketError(
            f"Buffer truncated: declared payload_length={payload_length}, "
            f"available={len(raw) - hdr_end}"
        )
    if len(raw) > payload_end:
        # Trailer present (CRC32)
        expected_crc = struct.unpack_from(">I", raw, payload_end)[0]
        validate_trailer(bytes(raw[:payload_end]), expected_crc)
        payload_end += C.CHECKSUM_SIZE

    return PacketView(raw, hdr_end, payload_end)
