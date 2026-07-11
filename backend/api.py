"""
FastAPI WebSocket server — replaces the stdin/stdout JSON-RPC IPC layer.

Message protocol is identical to the old pipe protocol so the handler
functions in server.py require zero changes:

  Client → Server  {"id": 1, "method": "fetch_categories", "params": {}}
  Server → Client  {"id": 1, "result": [...]}
  Server → Client  {"type": "progress", "done": 3, "total": 10, "card": "..."}
"""
import asyncio
import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).parent))

import server as _server  # noqa: E402

# Route _send calls from any thread to the active WebSocket connection.
# Single-user semantics: only one optimizer session runs at a time.
_active_send = None


def _patched_send(obj):
    fn = _active_send
    if fn:
        fn(obj)


_server._send = _patched_send

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Pokemon art and app art files for the frontend.
app.mount("/art", StaticFiles(directory=str(_ROOT / "art")), name="art")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    global _active_send
    await ws.accept()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    async def drain():
        while True:
            msg = await queue.get()
            if msg is None:
                break
            try:
                await ws.send_json(msg)
            except Exception:
                break

    drainer = asyncio.create_task(drain())
    _active_send = lambda obj: asyncio.run_coroutine_threadsafe(queue.put(obj), loop)  # noqa: E731

    try:
        while True:
            data = await ws.receive_json()
            req_id = data.get("id")
            method = data.get("method", "")
            params = data.get("params", {})

            handler = _server.HANDLERS.get(method)
            if handler is None:
                await ws.send_json({"id": req_id, "error": f"unknown method: {method}"})
                continue

            def _run(h=handler, rid=req_id, p=params):
                try:
                    result = h(p)
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"id": rid, "result": result}), loop
                    )
                except Exception as e:
                    traceback.print_exc()
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"id": rid, "error": str(e)}), loop
                    )

            threading.Thread(target=_run, daemon=True).start()

    except WebSocketDisconnect:
        pass
    finally:
        _active_send = None
        await queue.put(None)
        await drainer


# ── local dev TLS ─────────────────────────────────────────────────────────────
#
# TCGPlayer's CSP `connect-src` blocks plain `ws:` but allows unrestricted
# `wss:`, so the cart bookmarklet (which runs on tcgplayer.com and talks to
# this server directly, see handle_get_pending_cart in server.py) can only
# reach us over TLS. In production Railway terminates TLS at its edge and
# forwards plain HTTP to us (signaled by the PORT env var it injects), so we
# only self-sign a cert for local dev, where nothing else provides one.
#
# The browser won't trust this self-signed cert automatically — visit
# https://localhost:8000 once and click through the warning; that exception
# is remembered per host:port regardless of which page opens the connection,
# so the bookmarklet's wss:// connection will then succeed silently.


def _dev_tls_paths():
    cert_dir = Path(os.path.expanduser("~")) / ".masterset" / "dev-tls"
    cert_dir.mkdir(parents=True, exist_ok=True)
    return cert_dir / "cert.pem", cert_dir / "key.pem"


def _ensure_dev_cert(cert_path, key_path):
    if cert_path.exists() and key_path.exists():
        return True
    try:
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(key_path), "-out", str(cert_path),
                "-days", "825", "-subj", "/CN=localhost",
                "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True, capture_output=True,
        )
        return True
    except Exception as e:
        sys.stderr.write(
            f"[api] could not generate local dev TLS cert ({e});"
            " falling back to plain HTTP — the cart bookmarklet won't work.\n"
        )
        return False


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    ssl_kwargs = {}
    if "PORT" not in os.environ:  # local dev only, not behind Railway's proxy
        cert_path, key_path = _dev_tls_paths()
        if _ensure_dev_cert(cert_path, key_path):
            ssl_kwargs = {"ssl_certfile": str(cert_path), "ssl_keyfile": str(key_path)}
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False, **ssl_kwargs)
