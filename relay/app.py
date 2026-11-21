"""FastAPI app: POST /webhook receives Alertmanager webhook, forwards to group bots."""
import logging
import sys

# Windows GBK stdout contract (AGENTS.md rule 3).
for _s in (sys.stdout, sys.stderr):
    _enc = getattr(_s, "encoding", "") or ""
    if _enc.lower().replace("-", "") not in ("utf8", "utf"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

import os

from fastapi import FastAPI, Header, HTTPException

from . import __version__
from .config import EnvKMSProvider, Settings
from .forwarder import forward
from .serializer import serialize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="alert-relay", version=__version__)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": __version__}


@app.post("/webhook")
def webhook(payload: dict, x_webhook_token: str = Header(default="")):
    """Synchronous handler: FastAPI runs it in a worker thread so the blocking
    urllib POST inside forward() never stalls the event loop for other requests.

    Optional shared-secret auth: when RELAY_WEBHOOK_TOKEN is set, requests must
    carry X-Webhook-Token. When unset, open (for local drill / trusted network).
    """
    expected = os.environ.get("RELAY_WEBHOOK_TOKEN", "")
    if expected and x_webhook_token != expected:
        raise HTTPException(status_code=401, detail="invalid webhook token")
    payload_obj = serialize(payload)
    settings = Settings.from_env()
    kms = EnvKMSProvider()
    stats = forward(payload_obj, settings, kms)
    return {"ok": stats["errors"] == 0, **stats}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
