#!/usr/bin/env bash
# One-command entry for Flowdeck: unit tests (incl. exhaustive two-backend
# agreement), the static gate, the preserved round-2 draft held to the
# FROZEN gate (must fail with the historical findings), the frozen features
# replayed over real HTTP, and the app booting + seeding through the rules.
set -euo pipefail
cd "$(dirname "$0")"

ENGINE=../rule-driven-cms
if [[ ! -d $ENGINE/.venv ]]; then
  echo "[check] creating venv in $ENGINE"
  python3 -m venv $ENGINE/.venv
fi
$ENGINE/.venv/bin/pip install -q -r $ENGINE/requirements.txt pytest
PY=$(cd $ENGINE && pwd)/.venv/bin/python
RS=$(pwd)/rulesets

echo "==== 1. unit tests (incl. runtime<->Z3 agreement on all 34,560 situations) ===="
$PY -m pytest tests/ -q

echo
echo "==== 2. static gate: the Flowdeck rule base (expect PASS) ===="
(cd $ENGINE && $PY -m analysis.analyze "$RS/taskboard")

echo
echo "==== 3. the real round-2 draft, held to the FROZEN gate (expect FAIL: S2, S5, 2 probes) ===="
if (cd $ENGINE && $PY -m analysis.analyze "$RS/taskboard-round2" --gate "$RS/taskboard"); then
  echo "ERROR: the round-2 draft passed the gate — the gate is broken"; exit 1
else
  echo "[check] good: the frozen gate still catches the development-history bugs"
fi

echo
echo "==== 4. live: frozen features replayed over real HTTP + visibility probe ===="
(cd $ENGINE && $PY live_demo.py "$RS/taskboard")

echo
echo "==== 5. live: the app boots and seeds its demo board through the rules ===="
$PY app.py --seed-only --port 0

echo
echo "ALL CHECKS PASSED"
