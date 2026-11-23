"""Routing + forwarding. One serializer output -> two renderers -> bot webhook.

Channel selection is by env + severity. dev sends nothing. Unknown severity/env
falls back to the default channel WITH a warning (never silently dropped).
Webhook URLs are resolved from KMS at call time — never stored in config files.
"""
import json
import logging
import os
import urllib.request
from typing import List

from .config import KMSProvider, Settings
from .models import AlertEvent, WebhookPayload
from .renderers import render_feishu, render_wecom

log = logging.getLogger("alert-relay.forwarder")


def _default_channels() -> List[str]:
    """Both formats by default; RELAY_CHANNELS narrows the fan-out for a live
    drill where only some groups have a real webhook. Unknown names are ignored
    and an empty/invalid value falls back to both (never silently drop alerts).
    """
    raw = os.environ.get("RELAY_CHANNELS", "").strip()
    if not raw:
        return ["wecom", "feishu"]
    picked = [c.strip() for c in raw.split(",") if c.strip() in ("wecom", "feishu")]
    return picked or ["wecom", "feishu"]


def choose_channels(event: AlertEvent) -> List[str]:
    if event.env == "dev":
        log.info("env=dev -> suppress notification for %s", event.alertname)
        return []
    channels = _default_channels()
    if event.env in ("test", "staging", "prod"):
        return channels
    log.warning("unknown env %r -> fallback channels %s (not dropped)", event.env, channels)
    return channels


def build_message(event: AlertEvent, channel: str, settings: Settings) -> dict:
    if channel == "wecom":
        return render_wecom(event, settings)
    if channel == "feishu":
        return render_feishu(event, settings)
    log.warning("unknown channel %r -> fallback to wecom renderer", channel)
    return render_wecom(event, settings)


def post_webhook(url: str, message: dict, settings: Settings, timeout: float = None) -> int:
    if not url:
        # Do NOT report success on an empty webhook: a missing KMS secret must be
        # loud, otherwise every alert is silently discarded while callers see OK.
        raise ValueError("empty webhook URL (KMS secret not injected)")
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    t = timeout if timeout is not None else settings.http_timeout_seconds
    with urllib.request.urlopen(req, timeout=t) as resp:
        return resp.status


def forward(payload: WebhookPayload, settings: Settings, kms: KMSProvider) -> dict:
    stats = {"received": len(payload.alerts), "sent": 0, "suppressed": 0, "errors": 0}
    for event in payload.alerts:
        channels = choose_channels(event)
        if not channels:
            stats["suppressed"] += 1
            continue
        for channel in channels:
            try:
                url = kms.get_webhook(channel)  # KMS may raise on lookup failure
                message = build_message(event, channel, settings)
                status = post_webhook(url, message, settings)
                # Log the confirmed delivery WITHOUT ever printing the webhook URL.
                log.info("delivered channel=%s alert=%s http=%s", channel, event.alertname, status)
                stats["sent"] += 1  # count ONLY confirmed successful POSTs
            except Exception as exc:  # noqa: BLE001 - log and surface in stats
                stats["errors"] += 1
                log.error("send to %s failed for %s: %s", channel, event.alertname, exc)
    return stats
