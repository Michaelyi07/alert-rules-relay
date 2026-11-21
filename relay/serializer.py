"""Alertmanager webhook -> format-neutral AlertEvent.

Whitelist field mapping: ONLY alert name, env, instance, start time, panel link
(and resolved_at, runbook) are transferred. All other labels/annotations —
including business-data-like or PII-like keys — are dropped here.
"""
import logging
from typing import Any, Dict, List

from .models import AlertEvent, WebhookPayload

log = logging.getLogger("alert-relay.serializer")

ALLOWED_LABELS = ("alertname", "env", "severity", "instance")
ALLOWED_ANNOTATIONS = ("dashboard_url", "runbook_url", "summary")
KNOWN_ENVS = {"dev", "test", "staging", "prod"}
KNOWN_SEVERITIES = {"critical", "warning"}


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def serialize_alert(raw: Dict[str, Any]) -> AlertEvent:
    raw_labels = raw.get("labels") or {}
    raw_annotations = raw.get("annotations") or {}
    if not isinstance(raw_labels, dict):
        raw_labels = {}
    if not isinstance(raw_annotations, dict):
        raw_annotations = {}
    # Explicit whitelist: ONLY these keys survive. Any PII/business-data key is
    # discarded here before the model is built (defense in depth for renderers).
    labels = {k: v for k, v in raw_labels.items() if k in ALLOWED_LABELS}
    annotations = {k: v for k, v in raw_annotations.items() if k in ALLOWED_ANNOTATIONS}

    env = _safe_str(labels.get("env")).strip().lower()
    severity = _safe_str(labels.get("severity")).strip().lower()
    if env not in KNOWN_ENVS:
        log.warning("unknown env %r -> fallback 'unknown'", env)
        env = env or "unknown"
    if severity not in KNOWN_SEVERITIES:
        log.warning("unknown severity %r -> fallback 'unknown'", severity)
        severity = severity or "unknown"

    status = _safe_str(raw.get("status")).strip().lower()
    if status not in {"firing", "resolved"}:
        status = "firing"  # safe default

    return AlertEvent(
        status=status,
        alertname=_safe_str(labels.get("alertname")) or "UnnamedAlert",
        env=env,
        severity=severity,
        instance=_safe_str(labels.get("instance")),
        starts_at=_safe_str(raw.get("startsAt")),
        resolved_at=_safe_str(raw.get("endsAt")) or None,
        dashboard_url=_safe_str(annotations.get("dashboard_url")),
        runbook_url=_safe_str(annotations.get("runbook_url")),
        summary=_safe_str(annotations.get("summary")),
    )


def serialize(payload: Dict[str, Any]) -> WebhookPayload:
    if not isinstance(payload, dict):
        payload = {}
    raw_alerts: List[Dict[str, Any]] = payload.get("alerts") or []
    if not isinstance(raw_alerts, list):
        raw_alerts = []
    events: List[AlertEvent] = []
    for a in raw_alerts:
        if isinstance(a, dict):
            events.append(serialize_alert(a))
    return WebhookPayload(
        receiver=_safe_str(payload.get("receiver")),
        status=_safe_str(payload.get("status")),
        alerts=events,
    )
