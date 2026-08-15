#!/usr/bin/env bash
# One-command entry for Clearance, the manual's worked example: the
# static gate (expect PASS), the preserved round-1 draft held to the
# FROZEN gate (must FAIL: dead four-eyes rule + no P3 witness), and the
# frozen features replayed over real HTTP.
set -euo pipefail
cd "$(dirname "$0")"

ENGINE=../rule-driven-cms
if [[ ! -d $ENGINE/.venv ]]; then
  echo "[check] creating venv in $ENGINE"
  python3 -m venv $ENGINE/.venv
fi
$ENGINE/.venv/bin/pip install -q -r $ENGINE/requirements.txt
PY=$(cd $ENGINE && pwd)/.venv/bin/python
RS=$(pwd)/rulesets

echo "==== 1. static gate: the Clearance rule base (expect PASS) ===="
(cd $ENGINE && $PY -m analysis.analyze "$RS/approvals")

echo
echo "==== 2. the real round-1 draft, held to the FROZEN gate (expect FAIL: dead no_self_decision, no P3 witness) ===="
if (cd $ENGINE && $PY -m analysis.analyze "$RS/approvals-round1" --gate "$RS/approvals"); then
  echo "ERROR: the round-1 draft passed the gate — the gate is broken"; exit 1
else
  echo "[check] good: the frozen gate still catches the round-1 bug"
fi

echo
echo "==== 3. live: frozen features replayed over real HTTP ===="
(cd $ENGINE && $PY live_demo.py "$RS/approvals")

echo
echo "ALL CHECKS PASSED"
