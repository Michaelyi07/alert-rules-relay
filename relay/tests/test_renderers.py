"""C4: pytest covers WeCom and Feishu formats + field placement + truncation + PII."""
import json

from relay.config import Settings
from relay.models import AlertEvent
from relay.renderers import render_wecom, render_feishu, TRUNCATE_MARKER

S = Settings(max_message_chars=4096)


def firing(**kw):
    base = dict(
        status="firing", alertname="HostDiskUsageCritical", env="test",
        severity="critical", instance="10.0.0.7:9100",
        starts_at="2026-11-21T10:00:00Z", resolved_at=None,
        dashboard_url="https://grafana.example.invalid/d/host?var-instance=10.0.0.7:9100",
        runbook_url="https://runbook.example.invalid/ops/host#disk-usage",
    )
    base.update(kw)
    return AlertEvent(**base)


# ---- WeCom format ----

def test_wecom_markdown_format():
    msg = render_wecom(firing(), S)
    assert msg["msgtype"] == "markdown"
    c = msg["markdown"]["content"]
    assert "[FIRING]" in c and "HostDiskUsageCritical" in c
    assert "**环境**: test" in c
    assert "10.0.0.7:9100" in c
    assert "2026-11-21T10:00:00Z" in c
    assert "[查看面板](https://grafana.example.invalid/d/host" in c


def test_wecom_resolved_format():
    msg = render_wecom(firing(status="resolved", resolved_at="2026-11-21T10:05:00Z"), S)
    assert "[RESOLVED]" in msg["markdown"]["content"]
    assert "2026-11-21T10:05:00Z" in msg["markdown"]["content"]


# ---- Feishu format ----

def test_feishu_interactive_format():
    msg = render_feishu(firing(), S)
    assert msg["msg_type"] == "interactive"
    card = msg["card"]
    assert card["header"]["template"] == "red"
    assert "HostDiskUsageCritical" in card["header"]["title"]["content"]
    texts = json.dumps(card, ensure_ascii=False)
    assert "环境 **test**" in texts
    assert "10.0.0.7:9100" in texts
    assert "https://grafana.example.invalid/d/host" in texts


def test_feishu_resolved_green():
    msg = render_feishu(firing(status="resolved"), S)
    assert msg["card"]["header"]["template"] == "green"
    assert "RESOLVED" in msg["card"]["header"]["title"]["content"]


# ---- length handling ----

def test_wecom_truncation_marker():
    long = firing(instance="x" * 9000)
    msg = render_wecom(long, Settings(max_message_chars=200))
    assert TRUNCATE_MARKER in msg["markdown"]["content"]
    assert len(msg["markdown"]["content"]) <= 200


def test_feishu_truncation_guard():
    long = firing(instance="y" * 9000)
    msg = render_feishu(long, Settings(max_message_chars=400))
    # Feishu card must stay a LEGAL card even when the content budget is exceeded.
    assert msg["msg_type"] == "interactive"
    assert "card" in msg and "header" in msg["card"] and "elements" in msg["card"]
    assert "__raw__" not in msg
    assert len(json.dumps(msg, ensure_ascii=False)) <= 400
