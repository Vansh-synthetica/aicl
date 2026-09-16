# AICL vs FastAPI/HTTPS benchmark

See [`../../BENCHMARKS.md`](../../BENCHMARKS.md) for full results,
methodology, and honest caveats.

Quick start:

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
