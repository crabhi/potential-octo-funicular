#!/usr/bin/env bash
# P1 checks. Requires: npm i -g @informalsystems/quint (>= 0.32), and for
# `verify` a JVM (Apalache is fetched automatically on first use).
set -euo pipefail
cd "$(dirname "$0")"

echo "== typecheck =="
quint typecheck migration.qnt

echo "== simulate: correct protocol (expect: no violation) =="
quint run migration.qnt --main correct --invariant invAll \
  --backend typescript --max-samples 30000 --max-steps 30

echo "== simulate: broken protocol, no drain guard (expect: violation) =="
quint run migration.qnt --main broken --invariant invAll \
  --backend typescript --max-samples 20000 --max-steps 25 && {
    echo "ERROR: expected a violation in the broken config"; exit 1; } || true

echo "== symbolic verify (Apalache), correct protocol, 12 steps =="
quint verify migration.qnt --main correct --invariant invAll --max-steps 12

echo "== symbolic verify (Apalache), broken protocol (expect: counterexample) =="
quint verify migration.qnt --main broken --invariant invAll --max-steps 12 && {
    echo "ERROR: expected a counterexample in the broken config"; exit 1; } || true

echo "All checks behaved as expected."
