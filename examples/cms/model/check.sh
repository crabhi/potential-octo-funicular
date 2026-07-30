#!/usr/bin/env bash
# CMS model checks. Requires: npm i -g @informalsystems/quint (>= 0.32);
# JVM for `quint verify`.
set -euo pipefail
cd "$(dirname "$0")"

echo "== typecheck =="
quint typecheck cms.qnt

echo "== simulate: live auth checks (expect: no violation) =="
quint run cms.qnt --main cms_live --invariant invAll \
  --backend typescript --max-samples 20000 --max-steps 20

echo "== simulate: cached session auth (expect: violation) =="
quint run cms.qnt --main cms_cached --invariant invAll \
  --backend typescript --max-samples 20000 --max-steps 20 && {
    echo "ERROR: expected a violation in cms_cached"; exit 1; } || true
# a reproducible seed for the deactivated-author trace:
#   --seed 0x141c88dab83c39

echo "== feature test: editorial workflow must remain possible =="
quint test cms.qnt --main cms_live --backend typescript

echo "== feature coverage witnesses (random exploration reaches the features) =="
quint run cms.qnt --main cms_live --invariant invAll \
  --witnesses featSubmitted featPublished \
  --backend typescript --max-samples 3000 --max-steps 20

echo "== symbolic verify (Apalache), live (expect: NoError) =="
quint verify cms.qnt --main cms_live --invariant invAll --max-steps 10

echo "== symbolic verify (Apalache), cached (expect: counterexample) =="
quint verify cms.qnt --main cms_cached --invariant invAll --max-steps 10 && {
    echo "ERROR: expected a counterexample in cms_cached"; exit 1; } || true

echo "All checks behaved as expected."
