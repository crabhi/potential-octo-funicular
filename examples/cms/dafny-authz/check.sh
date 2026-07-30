#!/usr/bin/env bash
# check.sh — Track D end-to-end gate.
#
# 1. Verify authz.dfy (proves the ten YAML rules + feature guarantees for
#    ALL inputs, not sampled ones).
# 2. Compile authz.dfy to Go.
# 3. Build and run the Go demo program against a handful of scenarios; it
#    exits non-zero if the compiled artifact disagrees with any of them.
# 4. Verify that authz_buggy.dfy is REJECTED by the verifier, and that the
#    rejection names inv_deactivated_does_nothing.
#
# Any failure aborts with a non-zero exit and a clear step name so this can
# be wired into CI as the re-run-on-every-edit gate the research doc calls
# for.
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

step "1/4 dafny verify authz.dfy (the ten rules, proved for all inputs)"
dafny verify --solver-path "$Z3" authz.dfy

step "2/4 dafny build --target:go authz.dfy (regenerate authz-go/, keeping hand-written demo/)"
# dafny build only (re)writes its own generated files (authz.go, Authz/,
# System_/, dafny/) inside authz-go/src/ — it does not touch the
# hand-written authz-go/src/demo/ directory, so this regenerates the
# kernel bindings in place from the just-verified source.
dafny build --solver-path "$Z3" --target:go authz.dfy

step "3/4 build + run the Go demo embedding the verified kernel"
( cd authz-go && GOPATH="$HERE/authz-go" GO111MODULE=off go build -o "$HERE/demo.bin" ./src/demo )
"$HERE/demo.bin"

step "4/4 dafny verify authz_buggy.dfy must be REJECTED"
if dafny verify --solver-path "$Z3" authz_buggy.dfy > buggy_verify_output.txt 2>&1; then
  echo "FAIL: authz_buggy.dfy verified but should have been rejected!" >&2
  cat buggy_verify_output.txt
  exit 1
fi
# Dafny's error output cites the ensures clause's line/text, not the YAML
# invariant-name comment above it (comments aren't part of the AST it
# reports on) — so match on the clause body and cross-reference the name
# ourselves, the same way a human reading the output would.
if ! grep -q '!active ==> (!d.edit && !d.publish)' buggy_verify_output.txt; then
  echo "FAIL: rejection did not point at the inv_deactivated_does_nothing clause as expected" >&2
  cat buggy_verify_output.txt
  exit 1
fi
echo "Confirmed: verifier rejects the buggy variant, citing the ensures clause for"
echo "inv_deactivated_does_nothing (authz_buggy.dfy line 43: 'ensures !active ==> (!d.edit && !d.publish)'):"
cat buggy_verify_output.txt
rm -f buggy_verify_output.txt

echo
echo "ALL CHECKS PASSED."
