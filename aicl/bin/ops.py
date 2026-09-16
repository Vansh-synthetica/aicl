"""AICL-BIN operation codes (OPCVMES)."""
from __future__ import annotations

OP_REQUEST: int = 0x01
OP_RESPONSE: int = 0x02
OP_CLS: int = 0x03
OP_GEN: int = 0x04
OP_RSN: int = 0x05
OP_EMB: int = 0x06
OP_RNK: int = 0x07
OP_SUM: int = 0x08
OP_SYN: int = 0x09
OP_VRF: int = 0x0A
OP_XTR: int = 0x0B
OP_TRN: int = 0x0C
OP_PLN: int = 0x0D
OP_EVL: int = 0x0E
OP_TRN_MODEL: int = 0x0F
OP_MEM_READ: int = 0x10
OP_MEM_WRITE: int = 0x11
OP_MEM_DELETE: int = 0x12
OP_IDX_QUERY: int = 0x13
OP_IDX_UPSERT: int = 0x14
OP_RTE_DISCOVER: int = 0x15
OP_RTE_ROUTE: int = 0x16
OP_RTE_STATS: int = 0x17
OP_EXE_RUN: int = 0x18
OP_EXE_TOOL: int = 0x19
OP_EXE_MODEL: int = 0x1A
OP_DBG_INFO: int = 0x1B
OP_SYS_HBT: int = 0x1C
OP_SYS_ERR: int = 0x1D
OP_SYS_ACK: int = 0x1E
OP_SYS_CANCEL: int = 0x1F

OPERATION_NAMES: dict[int, str] = {
    OP_REQUEST: "REQ",
    OP_RESPONSE: "RES",
    OP_CLS: "CLS",
    OP_GEN: "GEN",
    OP_RSN: "RSN",
    OP_EMB: "EMB",
    OP_RNK: "RNK",
    OP_SUM: "SUM",
    OP_SYN: "SYN",
    OP_VRF: "VRF",
    OP_XTR: "XTR",
    OP_TRN: "TRN",
    OP_PLN: "PLN",
    OP_EVL: "EVL",
    OP_TRN_MODEL: "TRN_MODEL",
    OP_MEM_READ: "MEM_READ",
    OP_MEM_WRITE: "MEM_WRITE",
    OP_MEM_DELETE: "MEM_DELETE",
    OP_IDX_QUERY: "IDX_QUERY",
    OP_IDX_UPSERT: "IDX_UPSERT",
    OP_RTE_DISCOVER: "ROUTE_DISCOVER",
    OP_RTE_ROUTE: "ROUTE",
    OP_RTE_STATS: "ROUTE_STATS",
    OP_EXE_RUN: "EXE_RUN",
    OP_EXE_TOOL: "EXE_TOOL",
    OP_EXE_MODEL: "EXE_MODEL",
    OP_DBG_INFO: "DBG_INFO",
    OP_SYS_HBT: "HBT",
    OP_SYS_ERR: "ERR",
    OP_SYS_ACK: "ACK",
    OP_SYS_CANCEL: "CANCEL",
}

# Convenience categories
REQUEST_OPS: frozenset[int] = frozenset({
    OP_REQUEST, OP_CLS, OP_GEN, OP_RSN, OP_EMB, OP_RNK, OP_SUM,
    OP_SYN, OP_VRF, OP_XTR, OP_TRN, OP_PLN, OP_EVL, OP_TRN_MODEL,
    OP_MEM_READ, OP_MEM_WRITE, OP_MEM_DELETE, OP_IDX_QUERY,
    OP_IDX_UPSERT, OP_RTE_DISCOVER, OP_RTE_ROUTE, OP_RTE_STATS,
    OP_EXE_RUN, OP_EXE_TOOL, OP_EXE_MODEL, OP_DBG_INFO, OP_SYS_CANCEL,
})

RESPONSE_OPS: frozenset[int] = frozenset({
    OP_RESPONSE, OP_SYS_ACK, OP_SYS_ERR, OP_SYS_CANCEL,
})

SYSTEM_OPS: frozenset[int] = frozenset({
    OP_REQUEST, OP_RESPONSE, OP_SYS_HBT, OP_SYS_ERR, OP_SYS_ACK, OP_SYS_CANCEL,
})