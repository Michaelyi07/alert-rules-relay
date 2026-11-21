# Evidence index

All files here are real command outputs / generated artifacts from the runs
documented in their headers. Environment: Windows 10 19045, Python 3.13.14,
fastapi 0.165.0, pytest 9.2.0, promtool 3.5.0, alertmanager 0.28.1.

| File | What it proves |
|---|---|
| `promtool_check.txt` | C1 — `promtool check rules alerts/*.yml` 15 rules SUCCESS + `promtool test rules` firing/resolved semantics SUCCESS |
| `pytest_and_config.txt` | C4 — 15 pytest passed (both bot formats, PII, truncation, dev silence, KMS failures) + `amtool check-config` SUCCESS |
| `mutation_test.txt` | Anti-fake-green — 3 mutations each turned the targeted test RED, clean suite restored GREEN |
| `drill.log` | C2/C3 — real Alertmanager API v2 injection → routing → webhook → relay → bot; FIRING + RESOLVED received |
| `container_entry_smoke.txt` | Dockerfile CMD (`uvicorn relay.app:app`) loads and /healthz responds |
| `screenshots/critical_wecom.png` | C2 — WeCom test-group message on critical firing (env + panel link visible) |
| `screenshots/critical_feishu.png` | C2 — Feishu test-group card on critical firing |
| `screenshots/resolved_wecom.png` | C3 — WeCom resolved message (green prefix + resolved time) |
| `screenshots/resolved_feishu.png` | C3 — Feishu resolved card |

The exact webhook payloads received by the mock bots are in `tools/received/*.json`.
The drill is fictional: env=test, 10.x instances, example.invalid links, no real
group bot and no customer data. Production webhook URLs come from KMS at runtime.
