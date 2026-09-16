"""
End-to-end FastAPI/SSE relay server — receives a generate request over
HTTPS, calls llama-server's real streaming completion endpoint, and
re-streams each real token chunk to the client as an SSE event as it
arrives. This is the same relay job e2e_aicl_relay_server.py does, over
the transport Orcha's production streaming actually uses today.
"""
from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI()

LLAMA_URL = "http://localhost:8099/v1/chat/completions"
MAX_TOKENS = 40


class GenerateRequest(BaseModel):
    prompt: str


async def _relay(prompt: str):
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", LLAMA_URL, json={
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
    return StreamingResponse(_relay(req.prompt), media_type="text/event-stream")
