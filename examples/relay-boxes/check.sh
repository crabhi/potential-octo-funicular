#!/usr/bin/env bash
# One-command entry for Relay-on-boxes (a uv project). Both directions:
#   PASS  framework guarantees, the gate, reviewed + generated tests, boot
#   FAIL  each preserved bad variant must be caught by the stage named for it
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(pwd)
uv sync -q
PY="uv run --project $ROOT -q python"

echo "==== 1. framework: the sandbox holds against hostile bodies ===="
$PY -m pytest -q test/boxkit

echo
echo "==== 2. the gate: contracts, boundary, fresh typed bodies ===="
$PY -m boxkit check src/relay
if git rev-parse --git-dir >/dev/null 2>&1; then
  for f in src/generated/relay/cases/queues.py test/generated/relay/cases/test_queues.py; do
    [[ $(git check-attr linguist-generated "$f" | awk '{print $NF}') == true ]] \
      || { echo "  FAIL $f is not marked linguist-generated"; exit 1; }
  done
  echo "  ok   src/generated/ and test/generated/ are collapsed in pull-request diffs"
fi

echo
echo "==== 3. tests: reviewed (test/relay) then generated (test/generated) ===="
$PY -m pytest -q test/relay
$PY -m pytest -q test/generated

echo
echo "==== 4. the other direction: every preserved bad variant must FAIL ===="
expect_fail() {  # <label> <command...> — run in a scratch copy of the project
  local label=$1; shift
  if "$@" >/tmp/relay-boxes-variant.log 2>&1; then
    echo "  ERROR: $label PASSED — the gate is not holding"; tail -20 /tmp/relay-boxes-variant.log; exit 1
  fi
  echo "  good: $label is caught — $(grep -m1 -E '^FAILED|  FAIL ' /tmp/relay-boxes-variant.log | head -c 150)"
}
scratch() {  # fresh copy of src/ + test/ in a temp dir; prints its path
  local d; d=$(mktemp -d)
  cp -r src test pyproject.toml "$d"/
  echo "$d"
}
in_scratch() {  # <dir> <python args...> — run with the scratch copy's src/ first on the path
  local d=$1; shift
  (cd "$d" && PYTHONPATH="$d/src" uv run --project "$ROOT" -q python "$@")
}

S=$(scratch); cat variants/route_mistyped.py >> "$S/src/generated/relay/web/routes.py"
expect_fail "route body that mistypes its result (ty, gate stage 3)" \
  in_scratch "$S" -m boxkit check src/relay

S=$(scratch); cat variants/case_page_unescaped.py >> "$S/src/generated/relay/cases/pages.py"
expect_fail "case page that forgets to escape (reviewed XSS test)" \
  in_scratch "$S" -m pytest -q -x -p no:cacheprovider test/relay/cases/test_pages.py -k hostile

S=$(scratch); echo "from generated.relay.web import routes  # a 'shortcut' around the sandbox" \
  >> "$S/src/relay/web/server.py"
expect_fail "reviewed code importing generated code directly (boundary, gate stage 2)" \
  in_scratch "$S" -m boxkit check src/relay

S=$(scratch); $PY - "$S/src/relay/cases/rules.py" <<'PYEOF'
import re, sys
p = sys.argv[1]; s = open(p).read()
s2 = re.sub(r'@POLICY\.deny\("org_walls",.*?\n\n', '', s, count=1, flags=re.S)
assert s2 != s; open(p, "w").write(s2)
PYEOF
expect_fail "kernel without the org wall (reviewed policy grid)" \
  in_scratch "$S" -m pytest -q -x -p no:cacheprovider test/relay/test_policy.py

S=$(scratch); $PY - "$S/src/relay/cases/queues.py" <<'PYEOF'
import sys
p = sys.argv[1]; s = open(p).read()
s2 = s.replace('severity (high, med, low), then by id ascending', 'severity (high, med, low), then by id descending')
assert s2 != s; open(p, "w").write(s2)
PYEOF
expect_fail "a changed description leaves its body STALE (gate stage 3)" \
  in_scratch "$S" -m boxkit check src/relay

echo
echo "==== 5. mutation: deleting ANY guard rule must break a reviewed test ===="
$PY mutants.py

echo
echo "==== 6. live: the app boots and seeds through the kernel (mail via the robot) ===="
uv run -q relay --seed-only --port 0

echo
echo "ALL CHECKS PASSED"
