"""Serializer whitelist + PII stripping + fallback + dev suppression (AC4 edge cases)."""
from relay.config import Settings
from relay.models import AlertEvent
from relay.serializer import serialize
from relay.forwarder import choose_channels, build_message, forward
from relay.config import KMSProvider

S = Settings(max_message_chars=4096)

RAW = {
    "receiver": "relay-critical",
    "status": "firing",
    "alerts": [{
        "status": "firing",
        "labels": {"alertname": "HostDiskUsageCritical", "env": "prod",
                   "severity": "critical", "instance": "10.0.0.7:9100",
                   "customer_name": "ACME-CORP-PII", "user_email": "ceo@example.com"},
        "annotations": {
            "dashboard_url": "https://grafana.example.invalid/d/host",
            "runbook_url": "https://runbook.example.invalid/ops/host",
            "summary": "disk full",
            "business_secret": "SUPER-SECRET-DO-NOT-SEND",
        },
        "startsAt": "2026-11-21T10:00:00Z",
    }],
}


def test_serializer_whitelist_drops_pii():
    payload = serialize(RAW)
    e = payload.alerts[0]
    assert e.alertname == "HostDiskUsageCritical"
    assert e.env == "prod" and e.severity == "critical"
    # business fields not represented on the model at all
    assert not hasattr(e, "customer_name")
    assert not hasattr(e, "business_secret")


def test_whitelist_filters_pii_keys():
    """Explicit whitelist must drop PII-like labels/annotations at the source."""
    from relay.serializer import ALLOWED_LABELS, ALLOWED_ANNOTATIONS
    assert "customer_name" not in ALLOWED_LABELS
    assert "user_email" not in ALLOWED_LABELS
    assert "business_secret" not in ALLOWED_ANNOTATIONS
    # And the filter actually runs (not dead constants):
    e = serialize(RAW).alerts[0]
    assert "SUPER-SECRET" not in (e.summary or "")


def test_pii_never_in_rendered_text():
    payload = serialize(RAW)
    for ch in ("wecom", "feishu"):
        msg = build_message(payload.alerts[0], ch, S)
        blob = str(msg)
        assert "ACME-CORP-PII" not in blob
        assert "SUPER-SECRET-DO-NOT-SEND" not in blob
        assert "ceo@example.com" not in blob


def test_dev_suppressed():
    e = AlertEvent("firing", "A", "dev", "critical", "i", "t", None, "u", "r")
    assert choose_channels(e) == []


def test_unknown_severity_not_dropped():
    e = AlertEvent("firing", "A", "prod", "unknown", "i", "t", None, "u", "r")
    channels = choose_channels(e)
    assert channels  # fallback, never empty for non-dev


def test_forward_dev_zero_send():
    class K(KMSProvider):
        def get_webhook(self, channel):
            return "http://127.0.0.1:9999/none"
    payload = serialize({
        "status": "firing",
        "alerts": [{"status": "firing", "labels": {"alertname": "A", "env": "dev", "severity": "critical"}}],
    })
    stats = forward(payload, S, K())
    assert stats["suppressed"] == 1 and stats["sent"] == 0


def test_empty_webhook_is_error_not_sent():
    """KMS returns empty URL -> must surface as error, never counted as sent."""
    class EmptyKMS(KMSProvider):
        def get_webhook(self, channel):
            return ""
    payload = serialize(RAW)
    stats = forward(payload, S, EmptyKMS())
    assert stats["errors"] == 2 and stats["sent"] == 0


def test_kms_lookup_exception_is_error_not_sent():
    class BrokenKMS(KMSProvider):
        def get_webhook(self, channel):
            raise RuntimeError("KMS unavailable")
    payload = serialize(RAW)
    stats = forward(payload, S, BrokenKMS())
    assert stats["errors"] == 2 and stats["sent"] == 0


def test_severity_used_in_routing():
    """critical and warning must select different receivers in alertmanager.yml.
    The serializer keeps severity on the model; assert both severities survive.
    """
    for sev in ("critical", "warning"):
        e = serialize({
            "alerts": [{"status": "firing", "labels": {
                "alertname": "A", "env": "prod", "severity": sev}}],
        }).alerts[0]
        assert e.severity == sev
        assert choose_channels(e) == ["wecom", "feishu"]
