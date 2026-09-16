"""
FastAPI HTTPS server — the "normal" AI-to-AI communication baseline.

Mirrors AICL's own bench_local_path.rs methodology: the endpoint returns a
fixed, realistic response (not a per-request model inference) so the
benchmark measures transport overhead (HTTPS handshake reuse, TLS record
framing, JSON serialize/deserialize, ASGI dispatch) — the same thing the
Rust side measures (encode + ring-buffer transmit + decode), not model
compute. The response payload is real model output, captured once from
Qwen2.5-0.5B-Instruct running locally via llama-server, not synthetic text.

Run: uvicorn server:app --host 127.0.0.1 --port 8443 --ssl-keyfile key.pem
     --ssl-certfile cert.pem --workers 1 --log-level warning
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class ClassifyRequest(BaseModel):
    text: str
    labels: list[str]
    model: str


class ClassifyResponse(BaseModel):
    label: str
    confidence: float


# Real output captured from Qwen2.5-0.5B-Instruct (see gen_payload.py) —
# not synthetic, matching AICL's own demo's approach of using real
# classification results rather than lorem-ipsum stand-ins.
_RESPONSE = ClassifyResponse(label="positive", confidence=1.0)


@app.post("/classify", response_model=ClassifyResponse)
def classify(req: ClassifyRequest) -> ClassifyResponse:
    return _RESPONSE
