#!/usr/bin/env bash
# P2 one-command demo: bootstraps the venv, shows each subcommand on the
# example invariant sets, then runs the test suite.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  echo "[demo] creating venv"
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt pytest

PY=.venv/bin/python

echo "== check: consistent set (expect CONSISTENT + witness) =="
$PY -m oracle check examples/consistent.yaml

echo
echo "== check: contradictory set (expect IMPOSSIBLE + 2-invariant unsat core) =="
$PY -m oracle check examples/contradictory.yaml || true

echo
echo "== witness: surprising set (look for phase=contract with old_running=True) =="
$PY -m oracle witness examples/surprising.yaml -n 40 | grep -E "contract.*True|phase" | head -5 || true

echo
echo "== vacuity: consistent set (expect all OK) =="
$PY -m oracle vacuity examples/consistent.yaml

echo
echo "== claim: the forgotten guard, against the surprising set (expect SATISFIABLE) =="
$PY -m oracle claim examples/surprising.yaml \
  --claim 'implies(phase == "contract", not old_running)'

echo
echo "== tests =="
$PY -m pytest tests/ -q
