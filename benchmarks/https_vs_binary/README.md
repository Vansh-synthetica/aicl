# AICL vs FastAPI/HTTPS benchmark

See [`../../BENCHMARKS.md`](../../BENCHMARKS.md) for full results,
methodology, and honest caveats.

## Pure transport (no model inference)

```bash
pip install -r requirements.txt
python gen_cert.py                        # generates cert.pem/key.pem (gitignored)

python cross_process_client.py 5000       # AICL, cross-process

# In one terminal:
python -m uvicorn server:app --host 127.0.0.1 --port 8443 \
    --ssl-keyfile key.pem --ssl-certfile cert.pem --log-level warning
# In another:
python client.py 5000                     # FastAPI/HTTPS, cross-process
```

Streaming (many small chunks, matching Orcha's real SSE token-delta
pattern): `streaming_aicl_server.py` / `streaming_aicl_client.py` and
`streaming_sse_server.py` / `streaming_sse_client.py`, same pattern as
above.

## End-to-end with real model inference

The test that actually answers "does this matter": real 40-token
generation against a local GGUF model via `llama-server`, relayed through
each transport, interleaved round-by-round against a no-relay baseline.

```bash
# 1. Start llama-server on port 8099 (see BENCHMARKS.md for the command)
# 2. Start the SSE relay: uvicorn e2e_sse_relay_server:app --host 127.0.0.1 \
#      --port 8443 --ssl-keyfile key.pem --ssl-certfile cert.pem --log-level warning
# 3.
python e2e_combined.py 40
```

`e2e_aicl_relay_server.py` is spawned automatically by `e2e_combined.py` —
don't run it directly.
