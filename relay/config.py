"""Configuration. ALL webhook URLs come from environment / KMS — never from files.

In production the KMS provider writes the webhook URL into the env var named below.
The built-in stub provider is for local drills and tests only (fabricated values).
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Webhook URLs are intentionally NOT fields here: they are secrets resolved
    # at call time from KMS (see KMSProvider). Only non-secret tuning lives here.
    http_timeout_seconds: float = 5.0
    max_message_chars: int = 4096
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            http_timeout_seconds=float(os.environ.get("RELAY_HTTP_TIMEOUT", "5")),
            max_message_chars=int(os.environ.get("RELAY_MAX_MESSAGE_CHARS", "4096")),
            log_level=os.environ.get("RELAY_LOG_LEVEL", "INFO"),
        )


class KMSProvider:
    """Interface stub. Real deployment plugs a KMS SDK that returns the secret value."""

    def get_webhook(self, channel: str) -> str:
        raise NotImplementedError


class EnvKMSProvider(KMSProvider):
    """Stub: resolves the KMS secret name to an env var (fabricated in drills)."""

    ENV_MAP = {
        "wecom": "WECOM_WEBHOOK_URL",
        "feishu": "FEISHU_WEBHOOK_URL",
    }

    def get_webhook(self, channel: str) -> str:
        key = self.ENV_MAP.get(channel)
        if not key:
            return ""
        return os.environ.get(key, "")
