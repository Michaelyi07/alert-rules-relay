#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Mutation tests: prove the acceptance tests are NOT fake-green.

For each mutation: break the implementation, run the targeted test, expect RED,
restore, re-run clean suite. Writes evidence/mutation_test.txt.
Run from anywhere: python tools/mutation_test.py
"""
import os
import shutil
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    _enc = getattr(_s, "encoding", "") or ""
    if _enc.lower().replace("-", "") not in ("utf8", "utf"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "evidence", "mutation_test.txt")
PY = sys.executable

MUTATIONS = [
    {
        "name": "PII whitelist widened -> PII key survives the explicit filter",
        "file": "relay/serializer.py",
        "old": 'ALLOWED_ANNOTATIONS = ("dashboard_url", "runbook_url", "summary")',
        "new": 'ALLOWED_ANNOTATIONS = ("dashboard_url", "runbook_url", "summary", "business_secret")  # MUTATION',
        "expect_fail_test": "test_whitelist_filters_pii_keys",
    },
    {
        "name": "resolved template broken -> no RESOLVED marker",
        "file": "relay/renderers.py",
        "old": 'prefix = "✅ [RESOLVED]" if resolved else "🔴 [FIRING]"',
        "new": 'prefix = "🔴 [FIRING]"  # MUTATION',
        "expect_fail_test": "test_wecom_resolved_format",
    },
    {
        "name": "dev suppression broken -> dev sends",
        "file": "relay/forwarder.py",
        "old": '    if event.env == "dev":\n        log.info("env=dev -> suppress notification for %s", event.alertname)\n        return []',
        "new": '    if False:  # MUTATION dev suppression disabled\n        return []',
        "expect_fail_test": "test_dev_suppressed",
    },
]

results = []
for m in MUTATIONS:
    path = os.path.join(ROOT, m["file"])
    with open(path, encoding="utf-8") as f:
        original = f.read()
    assert m["old"] in original, f"anchor missing: {m['name']}"
    backup = path + ".bak"
    shutil.copy2(path, backup)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(original.replace(m["old"], m["new"], 1))
        r = subprocess.run(
            [PY, "-m", "pytest", "relay/tests/", "-q", "-k", m["expect_fail_test"]],
            cwd=ROOT, capture_output=True, text=True,
        )
        out = ((r.stdout or "") + (r.stderr or "")).lower()
        ran = "passed" in out or "failed" in out
        red = r.returncode == 1 and ran
        results.append(f"[{'PASS' if red else 'FAIL'}] {m['name']}: "
                       f"pytest rc={r.returncode} (expected rc=1 with failed test)")
        if not red:
            results.append(f"  !!! test stayed GREEN under mutation = fake-green risk; tail="
                           f"{out.strip().splitlines()[-1] if out.strip() else '(empty)'}")
    finally:
        shutil.move(backup, path)

r = subprocess.run([PY, "-m", "pytest", "relay/tests/", "-q"],
                   cwd=ROOT, capture_output=True, text=True)
last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
results.append(f"[INFO] restored code pytest rc={r.returncode}: {last}")

text = "$ python tools/mutation_test.py\n\n" + "\n".join(results) + "\n"
print(text)
with open(EV, "w", encoding="utf-8") as f:
    f.write(text)
sys.exit(0 if all("PASS" in x or x.startswith("[INFO]") for x in results) else 1)
