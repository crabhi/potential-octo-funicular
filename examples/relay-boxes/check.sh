#!/usr/bin/env bash
# One-command entry for Relay-on-boxes. Both directions:
#   PASS  framework guarantees, the gate, reviewed + generated tests, boot
#   FAIL  each preserved bad variant must be caught by the stage named for it
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(pwd)

if [[ ! -d .venv ]]; then
  echo "[check] creating .venv"
  python3 -m venv .venv
fi
.venv/bin/pip install -q "pydantic-monty==1.0.0" pytest
PY=$ROOT/.venv/bin/python

echo "==== 1. framework: the sandbox holds against hostile bodies ===="
$PY -m pytest boxkit/tests -q

echo
echo "==== 2. the gate: contracts, lifecycles, boundary, fresh typed bodies ===="
$PY -m boxkit check relay
if git rev-parse --git-dir >/dev/null 2>&1; then
  attr=$(git check-attr linguist-generated relay/generated/route.py | awk '{print $NF}')
  [[ $attr == true ]] || { echo "  FAIL relay/generated/ is not marked linguist-generated"; exit 1; }
  echo "  ok   relay/generated/ is collapsed in pull-request diffs (linguist-generated)"
fi

echo
echo "==== 3. tests: reviewed (relay/tests) then generated (relay/generated/tests) ===="
$PY -m pytest relay/tests -q
$PY -m pytest relay/generated/tests -q

echo
echo "==== 4. the other direction: every preserved bad variant must FAIL ===="
expect_fail() {  # <label> <command...> — run in a scratch copy of the app
  local label=$1; shift
  if "$@" >/tmp/relay-boxes-variant.log 2>&1; then
    echo "  ERROR: $label PASSED — the gate is not holding"; tail -20 /tmp/relay-boxes-variant.log; exit 1
  fi
  echo "  good: $label is caught — $(grep -m1 -E '^FAILED|  FAIL ' /tmp/relay-boxes-variant.log | head -c 150)"
}
scratch() {  # fresh copy of the app + framework in a temp dir; prints its path
  local d; d=$(mktemp -d)
  cp -r boxkit relay "$d"/
  echo "$d"
}
with_header() {  # <variant> <box>: install a variant body under the box's current header
  cp "variants/$1" "$S/relay/generated/$2.py"
  sed -i "1s/.*/$(head -1 "relay/generated/$2.py" | sed 's/[\/&]/\\&/g')/" "$S/relay/generated/$2.py"
}

S=$(scratch); with_header route_mistyped.py route
expect_fail "route body that mistypes its result (ty, gate stage 4)" \
  bash -c "cd $S && $PY -m boxkit check relay"

S=$(scratch); with_header case_page_unescaped.py case_page
expect_fail "case page that forgets to escape (reviewed XSS test)" \
  bash -c "cd $S && $PY -m pytest relay/tests/test_boxes.py -q -x -k hostile"

S=$(scratch); echo "from .generated import route  # a 'shortcut' around the sandbox" >> "$S/relay/shell.py"
expect_fail "reviewed code importing generated code directly (boundary, gate stage 3)" \
  bash -c "cd $S && $PY -m boxkit check relay"

S=$(scratch); $PY - "$S/relay/machine.py" <<'EOF'
import re, sys
p = sys.argv[1]; s = open(p).read()
s2 = re.sub(r'@POLICY\.deny\("org_walls",.*?\n\n', '', s, count=1, flags=re.S)
assert s2 != s; open(p, "w").write(s2)
EOF
expect_fail "kernel without the org wall (reviewed policy grid)" \
  bash -c "cd $S && $PY -m pytest relay/tests/test_policy.py -q -x"

S=$(scratch); $PY - "$S/relay/boxes.py" <<'EOF'
import sys
p = sys.argv[1]; s = open(p).read()
s2 = s.replace('severity (high, med, low), then by id ascending', 'severity (high, med, low), then by id descending')
assert s2 != s; open(p, "w").write(s2)
EOF
expect_fail "a changed description leaves its body STALE (gate stage 4)" \
  bash -c "cd $S && $PY -m boxkit check relay"

echo
echo "==== 5. mutation: deleting ANY guard rule must break a reviewed test ===="
$PY mutants.py

echo
echo "==== 6. live: the app boots and seeds through the kernel (mail via the robot) ===="
$PY -m relay.shell --seed-only --port 0

echo
echo "ALL CHECKS PASSED"
