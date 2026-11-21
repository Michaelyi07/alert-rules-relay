"""Format-neutral alert model: the single serializer output both renderers consume."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class AlertEvent:
    status: str            # "firing" | "resolved"
    alertname: str
    env: str               # dev | test | staging | prod | (unknown)
    severity: str          # critical | warning | (unknown)
    instance: str
    starts_at: str
    resolved_at: Optional[str]
    dashboard_url: str
    runbook_url: str
    summary: str = ""


@dataclass(frozen=True)
class WebhookPayload:
    receiver: str
    status: str
    alerts: List[AlertEvent] = field(default_factory=list)
