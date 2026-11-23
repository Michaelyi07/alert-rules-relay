# Evidence index

All files here are real command outputs / captured artifacts from the runs
documented in their headers. Environment: Windows 10 19045, Python 3.13.14,
fastapi 0.165.0, pytest 9.2.0, promtool 3.5.0, alertmanager 0.28.1.

| File | What it proves |
|---|---|
| `promtool_check.txt` | C1 — `promtool check rules alerts/*.yml` 15 rules SUCCESS + `promtool test rules` firing/resolved semantics SUCCESS |
| `pytest_and_config.txt` | C4 — 15 pytest passed (both bot formats, PII, truncation, dev silence, KMS failures) + `amtool check-config` SUCCESS |
| `mutation_test.txt` | Anti-fake-green — 3 mutations each turned the targeted test RED, clean suite restored GREEN |
| `drill.log` | Mock-mode technical proof — real Alertmanager API v2 injection → routing → webhook → relay → local mock bot; FIRING + RESOLVED received |
| `drill_live.log` | C2/C3 — LIVE drill via real Alertmanager → relay → REAL Feishu group webhook; critical firing + resolved, URLs redacted |
| `container_entry_smoke.txt` | Dockerfile CMD (`uvicorn relay.app:app`) loads and /healthz responds |
| `screenshots/critical_feishu.png` | C2 — REAL Feishu test group (`3195-alert-test`), group name + message time 16:30 + FIRING card with `环境 test`, instance, start time, panel link, runbook |
| `screenshots/resolved_feishu.png` | C3 — REAL Feishu test group, group name + message time 16:30 + green RESOLVED card with `环境 test`, `恢复时间 2026-11-21T10:00:01Z`, panel link |

The two screenshots are direct screen captures of the real Feishu group chat
window (not locally rendered cards). The group is a self-only test group; its
webhook was created by adding a custom bot in group settings and injected into
the relay via a gitignored local env file (`tools/.live_webhooks.env`), never
committed or printed. All message content is fictional: env=test, 10.x instance,
example.invalid links, no customer data, no PII. WeCom format coverage is by the
C4 pytest suite (both renderers), as the live drill exercised the Feishu channel;
the customer accepts either platform for the "test group received message" proof.
Production webhook URLs come from KMS at runtime.
