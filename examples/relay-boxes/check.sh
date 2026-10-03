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
echo "==== 2. the gate: review lock, contracts, lifecycles, boundary, fresh typed impls ===="
$PY -m boxkit check relay

echo
echo "==== 3. tests: reviewed (human-owned) then generated ===="
$PY -m pytest relay/tests/reviewed -q
$PY -m pytest relay/tests/generated -q

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
  cp -r boxkit relay "$d"/ && rm -rf "$d"/relay/REVIEW.md
  echo "$d"
}

S=$(scratch); cp variants/route_mistyped.py "$S/relay/impl/route.py"
sed -i "1s/.*/$(head -1 relay/impl/route.py | sed 's/[\/&]/\\&/g')/" "$S/relay/impl/route.py"
expect_fail "route body that mistypes its result (ty, stage 5)" \
  bash -c "cd $S && $PY -m boxkit check relay"

S=$(scratch); cp variants/case_page_unescaped.py "$S/relay/impl/case_page.py"
sed -i "1s/.*/$(head -1 relay/impl/case_page.py | sed 's/[\/&]/\\&/g')/" "$S/relay/impl/case_page.py"
expect_fail "case page that forgets to escape (reviewed XSS test)" \
  bash -c "cd $S && $PY -m pytest relay/tests/reviewed/test_boxes.py -q -x -k hostile"

S=$(scratch); echo "# an agent 'just tidying up' the kernel" >> "$S/relay/machine.py"
expect_fail "unapproved edit to reviewed code (review lock, stage 1)" \
  bash -c "cd $S && $PY -m boxkit check relay"

S=$(scratch); $PY - "$S/relay/machine.py" <<'EOF'
import re, sys
p = sys.argv[1]; s = open(p).read()
s2 = re.sub(r'@POLICY\.deny\("org_walls",.*?\n\n', '', s, count=1, flags=re.S)
assert s2 != s; open(p, "w").write(s2)
EOF
expect_fail "kernel without the org wall (reviewed policy grid)" \
  bash -c "cd $S && $PY -m pytest relay/tests/reviewed/test_policy.py -q -x"

S=$(scratch); $PY - "$S/relay/boxes.py" <<'EOF'
import sys
p = sys.argv[1]; s = open(p).read()
s2 = s.replace('severity (high, med, low), then by id ascending', 'severity (high, med, low), then by id descending')
assert s2 != s; open(p, "w").write(s2)
EOF
expect_fail "a changed description leaves its implementation STALE (stage 5)" \
  bash -c "cd $S && $PY -m boxkit approve relay --by test >/dev/null && $PY -m boxkit check relay"

echo
echo "==== 5. mutation: deleting ANY guard rule must break a reviewed test ===="
$PY mutants.py

echo
echo "==== 6. live: the app boots and seeds through the kernel (mail via the robot) ===="
$PY -m relay.shell --seed-only --port 0

echo
echo "ALL CHECKS PASSED"
