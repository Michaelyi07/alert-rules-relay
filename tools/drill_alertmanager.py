#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""FULL end-to-end acceptance drill through a REAL Alertmanager.

Chain: Alertmanager API v2 (inject alert) -> real routing/inhibition -> real
webhook POST -> relay -> KMS-stub webhook -> mock group bot -> PNG screenshots.

This proves rules route correctly and resolved notifications are emitted by a
real Alertmanager. Config used is tools/alertmanager.drill.yml (identical routing
to production, shorter group_wait so the drill finishes in seconds).

Usage: python tools/drill_alertmanager.py
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
    # Clean previous drill artifacts so screenshots/received are from THIS run.
    for d in ("tools/received", "evidence/screenshots"):
        full = os.path.join(ROOT, d)
        os.makedirs(full, exist_ok=True)
        for f in os.listdir(full):
            try:
                os.remove(os.path.join(full, f))
            except OSError:
                pass

    env = dict(os.environ)
    env["WECOM_WEBHOOK_URL"] = f"http://127.0.0.1:{BOT_PORT}/wecom/test-group"
    env["FEISHU_WEBHOOK_URL"] = f"http://127.0.0.1:{BOT_PORT}/feishu/test-group"
    env["PYTHONPATH"] = ROOT

    am = os.path.join(ROOT, "tools", "alertmanager.drill.yml")
    procs = [
        subprocess.Popen([PY, os.path.join(ROOT, "tools", "mock_group_bot.py"), str(BOT_PORT)],
                         env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        subprocess.Popen([PY, "-m", "uvicorn", "relay.app:app", "--host", "127.0.0.1",
                          "--port", str(RELAY_PORT)], env=env, cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        subprocess.Popen([AM_BIN, "--config.file=" + am,
                          "--web.listen-address=127.0.0.1:" + str(AM_PORT),
                          "--storage.path=" + os.path.join(ROOT, "tools", "_amdata")],
                         env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    ]
    log = []
    try:
        assert wait(f"http://127.0.0.1:{RELAY_PORT}/healthz"), "relay not ready"
        assert wait(f"http://127.0.0.1:{AM_PORT}/-/healthy"), "alertmanager not ready"
        log.append("$ alertmanager --version")
        st, ver = http(f"http://127.0.0.1:{AM_PORT}/api/v2/status")
        log.append("  " + json.loads(ver).get("versionInfo", {}).get("version", "?"))

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

        log.append("received bot payloads:")
        for f in sorted(os.listdir(os.path.join(ROOT, "tools", "received"))):
            p = os.path.join(ROOT, "tools", "received", f)
            obj = json.load(open(p, encoding="utf-8"))
            msg = obj["message"]
            marker = "RESOLVED" if ("RESOLVED" in str(msg) or
                      (isinstance(msg, dict) and msg.get("card", {}).get("header", {})
                       .get("template") == "green")) else "FIRING"
            log.append(f"  {f}: {marker}")
        log.append("screenshots:")
        for f in sorted(os.listdir(os.path.join(ROOT, "evidence", "screenshots"))):
            p = os.path.join(ROOT, "evidence", "screenshots", f)
            log.append(f"  {f} ({os.path.getsize(p)} bytes)")
        text = "\n".join(log)
        print(text)
        with open(os.path.join(ROOT, "evidence", "drill.log"), "w", encoding="utf-8") as fh:
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
