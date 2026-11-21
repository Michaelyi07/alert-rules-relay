"""Two renderers from one format-neutral model: WeCom markdown card + Feishu interactive card.

Content contract: ONLY alert name, env, instance, start time, panel link.
No business data, no PII. Long text is truncated with an explicit marker.
"""
from .config import Settings
from .models import AlertEvent

TRUNCATE_MARKER = "…(truncated)"


def _body_lines(event: AlertEvent, resolved: bool) -> list:
    lines = [
        f"**告警**: {event.alertname}",
        f"**环境**: {event.env}",
        f"**实例**: {event.instance or '-'}",
        f"**开始时间**: {event.starts_at or '-'}",
    ]
    if resolved:
        lines.append(f"**恢复时间**: {event.resolved_at or '-'}")
    if event.dashboard_url:
        lines.append(f"**面板**: [查看面板]({event.dashboard_url})")
    if event.runbook_url:
        lines.append(f"**处置手册**: [Runbook]({event.runbook_url})")
    return lines


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    keep = max(0, limit - len(TRUNCATE_MARKER))
    return text[:keep] + TRUNCATE_MARKER


# ---- WeCom (企业微信) markdown message ----

def render_wecom(event: AlertEvent, settings: Settings) -> dict:
    resolved = event.status == "resolved"
    prefix = "✅ [RESOLVED]" if resolved else "🔴 [FIRING]"
    title = f"{prefix} {event.alertname} ({event.env}, {event.severity})"
    content = title + "\n" + "\n".join(_body_lines(event, resolved))
    content = _truncate(content, settings.max_message_chars)
    return {"msgtype": "markdown", "markdown": {"content": content}}


# ---- Feishu (飞书) interactive card ----

def render_feishu(event: AlertEvent, settings: Settings) -> dict:
    resolved = event.status == "resolved"
    template = "green" if resolved else "red"
    header_title = ("✅ RESOLVED " if resolved else "🔴 FIRING ") + event.alertname
    elements = []
    for line in _body_lines(event, resolved):
        # Feishu markdown lark_md understands **bold** and [text](url).
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": line}})
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": header_title},
            "template": template,
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md",
             "content": f"环境 **{event.env}** · 级别 **{event.severity}**"}},
            {"tag": "hr"},
            *elements,
        ],
    }
    # Enforce content budget while ALWAYS keeping a legal Feishu card shape.
    # Never emit {"__raw__": ...} — Feishu rejects an unknown top-level field.
    # Budget is measured on the FULL message envelope (what tests assert).
    import json
    def envelope_len():
        return len(json.dumps({"msg_type": "interactive", "card": card}, ensure_ascii=False))

    if envelope_len() > settings.max_message_chars:
        for el in card["elements"]:
            if el.get("tag") == "div" and "text" in el:
                el["text"]["content"] = _truncate(el["text"]["content"], 160)
        # If still oversized, drop optional elements but keep header + legal shape.
        while envelope_len() > settings.max_message_chars and len(card["elements"]) > 1:
            card["elements"].pop()
    return {"msg_type": "interactive", "card": card}
