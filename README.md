# Alert rules & group-bot notification relay

Prometheus alert rules (6 families) + Alertmanager routing + a small FastAPI
service that converts Alertmanager webhooks into WeCom (企业微信) and Feishu (飞书)
group-bot messages. Fiction-only test data; no customer names, no real webhooks,
no PII in any notification.

## Layout

```
alerts/                 6 rule files (host/database/redis/queue/api/cert)
alertmanager/           alertmanager.yml (routing, inhibition, 5m/4h timing, dev silent)
relay/                  FastAPI service: serializer + 2 renderers + forwarder + tests
                        includes Dockerfile + requirements.txt
tools/mock_group_bot.py local bot receiver + PNG screenshot renderer (drill only)
tools/drill_alertmanager.py  C2/C3 FULL drill: real Alertmanager API -> routing -> webhook -> relay -> bot
tools/alertmanager.drill.yml drill config (same routing, short group_wait)
tools/rules_test.yml    promtool unit tests (firing/resolved semantics)
tools/mutation_test.py  anti-fake-green proof (mutate impl -> tests must go RED)
THRESHOLDS.md           alert threshold table + integration points
evidence/               real command outputs + screenshots (see evidence/README)
docker-compose.yml      optional compose wiring
```

## Run & test

```bash
# Unit tests (C4: both bot formats + PII + truncation + dev silence)
python -m pytest relay/tests/ -q

# Rule syntax check (C1) + firing/resolved semantics
promtool check rules alerts/*.yml
promtool test rules tools/rules_test.yml

# Alertmanager config validation
amtool check-config alertmanager/alertmanager.yml

# Anti-fake-green proof (mutate impl -> targeted tests must go RED)
python tools/mutation_test.py

# FULL end-to-end notification drill (C2/C3): real Alertmanager -> relay -> bot
export AM_BIN=<path to alertmanager.exe>   # Windows: set AM_BIN=<path>
python tools/drill_alertmanager.py
#   -> evidence/screenshots/{critical,resolved}_{wecom,feishu}.png
#   -> tools/received/*.json   (exact webhook payloads received)
#   -> evidence/drill.log
```

## Configuration (KMS, env-only)

Webhook URLs are **never** stored in a file. The deployment reads them from KMS
and exports:

- `WECOM_WEBHOOK_URL` — WeCom group-bot webhook
- `FEISHU_WEBHOOK_URL` — Feishu group-bot webhook
- `RELAY_HTTP_TIMEOUT` (default 5s), `RELAY_MAX_MESSAGE_CHARS` (default 4096)

`relay/config.py` defines the `KMSProvider` interface and an `EnvKMSProvider`
stub for drills. Plug your KMS SDK by implementing `get_webhook(channel)`.

## Message contract

Only: alert name, environment, instance, start time, panel link, runbook link,
(and resolved time on recovery). The serializer uses a label/annotation
whitelist; PII-like fields are dropped and asserted absent by tests. Long
messages are truncated with an explicit `…(truncated)` marker. dev env sends
nothing; unknown env/severity falls back with a warning (never silently dropped).

## Timing & routing

group_wait 5m; group_interval 5m; repeat_interval 4h; send_resolved true.
critical inhibits warning on the same (family, instance); disk critical also
inhibits disk warning explicitly. dev → noop receiver.

## Integration points (stubs)

Metrics that may differ in the target stack are isolated to rule expressions in
`alerts/` — see THRESHOLDS.md §Integration points. Webhook delivery is via real
group-bot HTTP endpoints; the receiver in `tools/` is a local mock for the drill.
