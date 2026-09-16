"""pytest tests for AICL-SL debug formatter."""
from __future__ import annotations
from aicl import encode, Packet
from aicl.bin.types import Symbol, Identity
from aicl.bin.symbol_types import S_STRING, S_NUMBER
from aicl.bin.constants import FLAG_REQUEST
from aicl.bin.ops import OP_CLS
from aicl.sl import format_packet, format_symbol, format_tlv, format_view


def test_format_symbol_string():
    s = Symbol(S_STRING, "hello")
    assert format_symbol(s) == 'S:"hello"'


def test_format_symbol_number():
    s = Symbol(S_NUMBER, 0.5)
    assert format_symbol(s) == "N:0.5"


def test_format_symbol_null():
    s = Symbol(0x0C, None)
    assert format_symbol(s) == "NULL"


def test_format_packet_basic():
    pkt = Packet(
        flags=FLAG_REQUEST, operation=OP_CLS,
        origin=Identity(0x01, "test"),
        targets=["module_a"],
        symbols=[Symbol(S_STRING, "hello world")],
    )
    data = encode(pkt)
    text = format_packet(data)
    assert "AICL-BIN Packet" in text
    assert "REQUEST" in text
    assert "CLS" in text
    assert "hello world" in text
    assert "module_a" in text


def test_format_packet_does_not_include_unset():
    pkt = Packet()
    data = encode(pkt)
    text = format_packet(data)
    # Minimal packet shouldn't show confidence/intent/targets/etc.
    assert "AICL-BIN Packet" in text
    assert "targets" not in text.lower()
    assert "intent" not in text.lower()