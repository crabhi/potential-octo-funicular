#!/usr/bin/env bash
# One-command entry: bootstrap, unit tests (incl. exhaustive two-backend
# agreement), static analysis of all three rule bases (the buggy one is
# held to the FROZEN gate and must fail), then the live HTTP demos.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  echo "[check] creating venv"
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt pytest
PY=.venv/bin/python

echo "==== 1. engine unit tests (incl. runtime<->Z3 agreement on every situation) ===="
$PY -m pytest tests/ -q

echo
echo "==== 2. static gate: the CMS rule base (expect PASS) ===="
$PY -m analysis.analyze rulesets/cms

echo
echo "==== 3. static gate: buggy edit held to the FROZEN gate (expect FAIL, named findings) ===="
if $PY -m analysis.analyze rulesets/cms-buggy --gate rulesets/cms; then
  echo "ERROR: the buggy rule base passed the gate — the gate is broken"; exit 1
else
  echo "[check] good: the frozen gate rejected the buggy rule base"
fi

echo
echo "==== 4. static gate: naive nightly-import extension (expect FAIL, named findings) ===="
if $PY -m analysis.analyze rulesets/cms-import-naive --gate rulesets/cms; then
  echo "ERROR: the naive import extension passed the gate — the gate is broken"; exit 1
else
  echo "[check] good: the frozen gate rejected the naive import extension"
fi

echo
echo "==== 5. static gate: a second service (tickets) on the same engine (expect PASS) ===="
$PY -m analysis.analyze rulesets/tickets

echo
echo "==== 6. static gate: a third service (receivables, with time) — same engine (expect PASS) ===="
$PY -m analysis.analyze rulesets/receivables

echo
echo "==== 7. live: real HTTP server, frozen features replayed over the wire ===="
$PY live_demo.py rulesets/cms

echo
echo "==== 8. live: the tickets service — same engine, different rule base ===="
$PY live_demo.py rulesets/tickets

echo
echo "==== 9. live: the receivables service — time-dependent features over the wire ===="
$PY live_demo.py rulesets/receivables

echo
echo "==== 10. live: nightly import — mock publishers -> importer job -> editorial flow ===="
$PY import_demo.py

echo
echo "==== 11. live: receivables end to end — bank emails, matching, overdue, reminders ===="
$PY receivables_demo.py

echo
echo "ALL CHECKS PASSED"
