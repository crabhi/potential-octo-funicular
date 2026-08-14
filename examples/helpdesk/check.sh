#!/usr/bin/env bash
# One-command entry for Relay: tests at all three layers (model agreement,
# kernel boundary, app over HTTP), the static gate, the boundary lint in
# both directions (the app must pass; the preserved bypass variant must
# FAIL), and the app booting + seeding through the kernel.
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

echo "==== 1. tests: model agreement (19,200 situations), kernel, app over HTTP ===="
$PY -m pytest tests/ -q

echo
echo "==== 2. static gate: the Relay rule base (expect PASS) ===="
(cd $ENGINE && $PY -m analysis.analyze "$RS/helpdesk")

echo
echo "==== 3. boundary lint: the UI imports engine.kernel and nothing beneath it ===="
(cd $ENGINE && $PY -m analysis.boundary "$(pwd)/../helpdesk/app.py" \
                                        "$(pwd)/../helpdesk/screenshots.py")

echo
echo "==== 4. boundary lint on the preserved bypass variant (expect FAIL) ===="
if (cd $ENGINE && $PY -m analysis.boundary "$(pwd)/../helpdesk/bypass_variant"); then
  echo "ERROR: the bypass variant passed the lint — the boundary is not held"; exit 1
else
  echo "[check] good: the lint refuses the store-writing shortcut by name"
fi

echo
echo "==== 5. live: the app boots and seeds its demo desk through the kernel ===="
$PY app.py --seed-only --port 0

echo
echo "ALL CHECKS PASSED"
