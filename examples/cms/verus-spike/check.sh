#!/usr/bin/env bash
# check.sh — Track L gate (session/identity state machine), Dafny fallback.
#
# Mirrors examples/cms/dafny-authz/check.sh's shape:
#   1. Verify identity_store.dfy (the state-machine theorems, for ALL
#      reachable states, not sampled ones).
#   2. Verify that identity_store_buggy.dfy is REJECTED, and that the
#      rejection names the RevocationImmediate ensures clause.
#
# No Go/Rust codegen step here (unlike dafny-authz/) -- see README.md
# "Extraction-fidelity gap" for why that would be the natural next step
# and what it would take.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

export PATH="$PATH:/root/.dotnet/tools:/root/go/bin"

Z3="$(command -v z3 || true)"
if [ -z "$Z3" ]; then
  echo "FAIL: z3 not found on PATH (needed by dafny verify)" >&2
  exit 1
fi

step() { echo; echo "=== $* ==="; }

step "1/2 dafny verify identity_store.dfy (state-machine theorems, proved for all reachable states)"
dafny verify --solver-path "$Z3" identity_store.dfy

step "2/2 dafny verify identity_store_buggy.dfy must be REJECTED"
if dafny verify --solver-path "$Z3" identity_store_buggy.dfy > buggy_verify_output.txt 2>&1; then
  echo "FAIL: identity_store_buggy.dfy verified but should have been rejected!" >&2
  cat buggy_verify_output.txt
  exit 1
fi
# Dafny cites the ensures clause's line/text. The seeded bug (active read
# from the session snapshot instead of the users map) breaks BOTH
# FreshnessLive and RevocationImmediate -- we assert on the latter, the
# one the task calls out, but check for both so a future refactor that
# accidentally weakens only one of them still trips this gate.
if ! grep -q 'ResolveLive(Deactivate(s, user), token) == Some((s.users\[user\].0, false))' buggy_verify_output.txt; then
  echo "FAIL: rejection did not point at the RevocationImmediate clause as expected" >&2
  cat buggy_verify_output.txt
  exit 1
fi
if ! grep -q 'ResolveLive(s, token) == Some(s.users\[s.sessions\[token\].0\])' buggy_verify_output.txt; then
  echo "FAIL: rejection did not also point at FreshnessLive as expected (bonus check)" >&2
  cat buggy_verify_output.txt
  exit 1
fi
echo "Confirmed: verifier rejects the buggy variant, citing both RevocationImmediate's"
echo "and FreshnessLive's ensures clauses (identity_store_buggy.dfy: ResolveLive reads"
echo "active from the session snapshot instead of the live users map):"
cat buggy_verify_output.txt
rm -f buggy_verify_output.txt

echo
echo "ALL CHECKS PASSED."
