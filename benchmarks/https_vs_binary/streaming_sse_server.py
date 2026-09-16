"""
FastAPI SSE streaming server — mirrors Orcha's actual production streaming
pattern (orcha/api/agent_stream.py): StreamingResponse, text/event-stream,
one `data: {json}\\n\\n` line per token/event.
"""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

# Same shape Orcha's real token-delta events use.
_CHUNK_TEXT = " token"
_N_CHUNKS = 50


def _stream():
    for i in range(_N_CHUNKS):
        wire = {"kind": "delta", "seq": i, "text": _CHUNK_TEXT}
        yield f"data: {json.dumps(wire)}\n\n"
    yield f"data: {json.dumps({'kind': 'end', 'seq': _N_CHUNKS})}\n\n"


@app.get("/stream")
def stream():
    return StreamingResponse(_stream(), media_type="text/event-stream")
