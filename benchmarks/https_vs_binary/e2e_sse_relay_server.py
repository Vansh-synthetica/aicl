"""
End-to-end FastAPI/SSE relay server — receives a generate request over
HTTPS, calls llama-server's real streaming completion endpoint, and
re-streams each real token chunk to the client as an SSE event as it
arrives. This is the same relay job e2e_aicl_relay_server.py does, over
the transport Orcha's production streaming actually uses today.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

LLAMA_URL = "http://127.0.0.1:8099/v1/chat/completions"
MAX_TOKENS = 40


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One persistent AsyncClient for the server's whole lifetime, not a
    # fresh one per request — see e2e_combined.py's baseline_call for the
    # full reasoning: a fresh AsyncClient() costs ~160-220ms to construct
    # regardless of what it talks to (confirmed via direct measurement).
    # llama-server's keep-alive problem is solved with an explicit
    # `Connection: close` header per request instead.
    app.state.client = httpx.AsyncClient(timeout=60.0)
    yield
    await app.state.client.aclose()


app = FastAPI(lifespan=lifespan)


class GenerateRequest(BaseModel):
    prompt: str


async def _relay(client: httpx.AsyncClient, prompt: str):
    async with client.stream("POST", LLAMA_URL, headers={"Connection": "close"}, json={
        "model": "qwen2.5-0.5b",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.1,
        "stream": True,
    }) as resp:
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                break
            yield f"data: {payload}\n\n"
    yield "data: {\"kind\": \"end\"}\n\n"


@app.post("/generate")
def generate(req: GenerateRequest):
    return StreamingResponse(_relay(app.state.client, req.prompt), media_type="text/event-stream")
