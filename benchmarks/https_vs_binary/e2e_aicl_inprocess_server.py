"""
End-to-end AICL *fully in-process* relay server — no HTTP, no TCP, no
"localhost" anywhere. The model is loaded directly via llama_cpp (the
Python binding to llama.cpp's C++ library) inside this process, and every
real generated token is forwarded to the client purely through the AICL
shared-memory ring. Compare against e2e_aicl_relay_server.py, which still
makes a real (if optimized) HTTP call to a separate llama-server process —
this script is the answer to "can we remove the network stack entirely."

Model load happens once per process lifetime, same as llama-server loading
its model once at startup — not repeated per request.
"""
from __future__ import annotations

import sys

from llama_cpp import Llama

from aicl.bin.codec_api import decode, encode
from aicl.bin.codec_packet import Packet
from aicl.bin.symbol_types import S_STRING
from aicl.bin.types import Symbol
from aicl.transport.shared_memory_ring import SharedMemoryRing

STOP_SENTINEL = b"__STOP__"
MODEL_PATH = "D:/New folder (6)/MODELS/Qwen__Qwen2.5-0.5B-Instruct-GGUF__qwen2.5-0.5b-instruct-fp16.gguf"
MAX_TOKENS = 40


def main() -> None:
    req_name, resp_name = sys.argv[1], sys.argv[2]
    req_ring = SharedMemoryRing.attach(req_name)
    resp_ring = SharedMemoryRing.attach(resp_name)

    llm = Llama(model_path=MODEL_PATH, n_ctx=2048, n_threads=4, verbose=False)

    while True:
        wire = req_ring.pop(timeout_s=120.0)
        if wire == STOP_SENTINEL:
            break
        view = decode(wire)
        prompt = view.symbols[0].value

        # Real streaming generation, straight out of llama.cpp — no
        # sockets, no HTTP framing, no JSON-over-the-wire between this
        # process and the model. Each token is forwarded to the client the
        # instant it's produced, exactly like the HTTP relay does, just
        # without anything resembling a network in between.
        for chunk in llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS, temperature=0.1, stream=True,
        ):
            delta = chunk["choices"][0].get("delta", {})
            text = delta.get("content")
            if not text:
                continue
            resp_ring.push(encode(Packet(operation=4, symbols=[Symbol(S_STRING, text)])))
        resp_ring.push(encode(Packet(operation=4, symbols=[], intent="end")))

    req_ring.close()
    resp_ring.close()


if __name__ == "__main__":
    main()
