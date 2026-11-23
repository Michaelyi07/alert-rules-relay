#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""End-to-end acceptance drill through a REAL Alertmanager.

Two modes:

* default (mock): Alertmanager API v2 -> routing/inhibition -> webhook POST ->
  relay -> local mock group bot -> PNG cards. Proves routing + resolved are
  emitted. The PNGs are FABRICATED local renders and are NOT, by themselves,
  proof that a real group received a message.

* --live (real groups): identical chain, but relay reads REAL webhook URLs from
  tools/.live_webhooks.env (gitignored, never printed or written to evidence)
  and POSTs to the real WeCom / Feishu group bots. No mock bot is started and no
  fabricated PNG is rendered. The operator captures AC2/AC3 screenshots from the
  actual group chat window after this drill completes.

Usage:
  python tools/drill_alertmanager.py           # mock drill
  python tools/drill_alertmanager.py --live    # real group delivery
Requires alertmanager.exe on PATH or AM_BIN env var.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

for _s in (sys.stdout, sys.stderr):
    _enc = getattr(_s, "encoding", "") or ""
    if _enc.lower().replace("-", "") not in ("utf8", "utf"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AM_BIN = os.environ.get("AM_BIN", "alertmanager")
AM_PORT = 19093
RELAY_PORT = 18081
BOT_PORT = 18080
PY = sys.executable
LIVE = "--live" in sys.argv[1:]
SECRET_FILE = os.path.join(ROOT, "tools", ".live_webhooks.env")


def load_live_webhooks():
    """Read KEY=VALUE webhook secrets from the gitignored local file.

    Values are returned to the child process env only — never printed, never
    written into evidence. Missing file / empty value simply disables that
    channel. At least one real webhook is required in LIVE mode.
    """
    hooks = {}
    if os.path.isfile(SECRET_FILE):
        with open(SECRET_FILE, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key in ("WECOM_WEBHOOK_URL", "FEISHU_WEBHOOK_URL"):
                    hooks[key] = value.strip().strip('"').strip("'")
    return hooks


def http(url, method="GET", payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read().decode("utf-8", "replace")


def wait(url, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if http(url)[0] == 200:
                return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    # In LIVE mode keep screenshots intact: the operator writes real group
    # captures there. In mock mode clean artifacts so evidence is from THIS run.
    for d in ("tools/received",):
        full = os.path.join(ROOT, d)
        os.makedirs(full, exist_ok=True)
        for f in os.listdir(full):
            try:
                os.remove(os.path.join(full, f))
            except OSError:
                pass
    shots_dir = os.path.join(ROOT, "evidence", "screenshots")
    os.makedirs(shots_dir, exist_ok=True)
    if not LIVE:
        for f in os.listdir(shots_dir):
            try:
                os.remove(os.path.join(shots_dir, f))
            except OSError:
                pass

    env = dict(os.environ)
    channels = []
    if LIVE:
        hooks = load_live_webhooks()
        for key, channel in (("WECOM_WEBHOOK_URL", "wecom"),
                             ("FEISHU_WEBHOOK_URL", "feishu")):
            value = hooks.get(key, "")
            if value:
                env[key] = value
                channels.append(channel)
        if not channels:
            raise SystemExit(
                "LIVE mode needs at least one real webhook in tools/.live_webhooks.env "
                "(WECOM_WEBHOOK_URL and/or FEISHU_WEBHOOK_URL). See README."
            )
        env["RELAY_CHANNELS"] = ",".join(channels)  # only fan out to configured groups
        env["MOCK_BOT_NO_SHOT"] = "1"  # belt-and-braces: never render a fake PNG
    else:
        env["WECOM_WEBHOOK_URL"] = f"http://127.0.0.1:{BOT_PORT}/wecom/test-group"
        env["FEISHU_WEBHOOK_URL"] = f"http://127.0.0.1:{BOT_PORT}/feishu/test-group"
    env["PYTHONPATH"] = ROOT

    am = os.path.join(ROOT, "tools", "alertmanager.drill.yml")
    procs = []
    if not LIVE:
        procs.append(subprocess.Popen(
            [PY, os.path.join(ROOT, "tools", "mock_group_bot.py"), str(BOT_PORT)],
            env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    procs.append(subprocess.Popen(
        [PY, "-m", "uvicorn", "relay.app:app", "--host", "127.0.0.1",
         "--port", str(RELAY_PORT)], env=env, cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    procs.append(subprocess.Popen(
        [AM_BIN, "--config.file=" + am,
         "--web.listen-address=127.0.0.1:" + str(AM_PORT),
         "--storage.path=" + os.path.join(ROOT, "tools", "_amdata_live" if LIVE else "_amdata")],
        env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

    log = []
    try:
        assert wait(f"http://127.0.0.1:{RELAY_PORT}/healthz"), "relay not ready"
        assert wait(f"http://127.0.0.1:{AM_PORT}/-/healthy"), "alertmanager not ready"
        log.append(f"MODE={'LIVE real group webhooks' if LIVE else 'MOCK local group bot'}")
        if LIVE:
            # REDACTED: log channel NAMES only, never the webhook URL (it is a secret).
            log.append("delivery channels (URLs redacted): " + ", ".join(channels))
        st, ver = http(f"http://127.0.0.1:{AM_PORT}/api/v2/status")
        log.append("$ alertmanager --version -> " + json.loads(ver).get("versionInfo", {}).get("version", "?"))

        # critical firing alert via real API v2
        alert = {
            "labels": {"alertname": "HostDiskUsageCritical", "env": "test",
                       "severity": "critical", "family": "host", "instance": "10.0.0.7:9100"},
            "annotations": {"summary": "Host disk usage > 95%",
                            "runbook_url": "https://runbook.example.invalid/ops/host#disk-usage",
                            "dashboard_url": "https://grafana.example.invalid/d/host-overview?var-instance=10.0.0.7:9100"},
            "startsAt": "2026-11-21T10:00:00Z",
        }
        st, _ = http(f"http://127.0.0.1:{AM_PORT}/api/v2/alerts", "POST", [alert])
        log.append(f"POST /api/v2/alerts (firing critical) -> HTTP {st}")
        time.sleep(6)  # group_wait 1s + interval + webhook fanout

        # resolve via real API v2 (endsAt in the past)
        resolved = dict(alert)
        resolved["endsAt"] = "2026-11-21T10:00:01Z"
        st, _ = http(f"http://127.0.0.1:{AM_PORT}/api/v2/alerts", "POST", [resolved])
        log.append(f"POST /api/v2/alerts (resolved) -> HTTP {st}")
        time.sleep(6)

        st, body = http(f"http://127.0.0.1:{AM_PORT}/api/v2/alerts")
        active = json.loads(body)
        log.append(f"GET /api/v2/alerts -> HTTP {st}, active_alerts={len(active)}")

        if LIVE:
            log.append("LIVE: messages were POSTed to the real group bots named above.")
            log.append("AC2/AC3 screenshots must be captured from the real group chat "
                       "window (group name + message time + env=test + panel link).")
            log.append("Relay delivery is logged by relay (channel + http status, URL redacted); "
                       "see relay stdout in the operator's run.")
            out_name = "drill_live.log"
        else:
            log.append("received bot payloads:")
            for f in sorted(os.listdir(os.path.join(ROOT, "tools", "received"))):
                p = os.path.join(ROOT, "tools", "received", f)
                obj = json.load(open(p, encoding="utf-8"))
                msg = obj["message"]
                marker = "RESOLVED" if ("RESOLVED" in str(msg) or
                          (isinstance(msg, dict) and msg.get("card", {}).get("header", {})
                           .get("template") == "green")) else "FIRING"
                log.append(f"  {f}: {marker}")
            out_name = "drill.log"

        log.append("screenshots: NONE generated by this LIVE drill (by design).")
        log.append("AC2/AC3 evidence = real chat-window captures taken by the operator AFTER this run")
        log.append("and saved to evidence/screenshots/critical_feishu.png + resolved_feishu.png.")
        text = "\n".join(log)
        print(text)
        with open(os.path.join(ROOT, "evidence", out_name), "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    finally:
        for p in reversed(procs):
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()


if __name__ == "__main__":
    main()
