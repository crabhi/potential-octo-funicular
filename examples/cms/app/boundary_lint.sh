#!/usr/bin/env bash
# boundary_lint.sh -- belt-and-suspenders check on top of the
# authz::Grant<Op> typestate (see ../proof-spike/src/authz.rs).
#
# The actual mechanical guarantee is the type system: `Grant<Op>` cannot be
# constructed except by `authz::require::<Op>`, so a protected handler that
# doesn't call it cannot compile with a `Grant<Op>` parameter it needs.
# What the type system does *not* prevent is a handler that calls
# `authz::require` and then silently discards an `Err` (or never uses the
# `Grant` it got back for anything), or that reimplements the same decision
# itself in parallel via a raw `Role::*` comparison instead of trusting the
# kernel's answer. This script is a textual check for exactly those two
# smells in `server/src/main.rs`'s four protected handlers:
#
#   1. each of get_article / edit_article / submit_article / publish_article
#      calls `authz::require`, and
#   2. none of them contains a direct `Role::` comparison of its own.
#
# This is pattern matching over source text, not a proof -- a determined
# rewrite that keeps a call to `authz::require` in the source while
# defeating it at runtime (ignoring the Result via `let _ =`, an early
# `return Ok(...)` before the check, etc.) would not be caught here. See
# proof-spike/README.md and authz.rs's module doc for what is/isn't
# actually type-enforced.
#
# Known, documented exception: admin user-management
# (admin_deactivate/admin_demote) is out of this refactor's stated scope
# (view/edit/submit/publish only) and still does its own `role != Role::Admin`
# check. This script does not scan those two functions, and says so below.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN="$HERE/server/src/main.rs"

PROTECTED_FNS=(get_article edit_article submit_article publish_article)
FAIL=0

extract_fn() {
    # Prints the body of the named top-level `async fn NAME(` through the
    # next `^}` at column 0. Relies on this file's rustfmt convention that
    # top-level items close at column 0 -- good enough for a lint, not a
    # parser.
    sed -n "/^async fn ${1}(/,/^}/p" "$MAIN"
}

for fn in "${PROTECTED_FNS[@]}"; do
    body="$(extract_fn "$fn")"
    if [[ -z "$body" ]]; then
        echo "boundary_lint: FAIL -- could not find function '${fn}' in main.rs (script rot -- update this list or the extraction pattern)"
        FAIL=1
        continue
    fi

    if grep -qE 'Role::' <<<"$body"; then
        echo "boundary_lint: FAIL -- '${fn}' contains a direct Role::* reference; access-control role logic must live in authz_spike::authz, not main.rs"
        grep -nE 'Role::' <<<"$body" | sed 's/^/    /'
        FAIL=1
    fi

    if ! grep -qE 'authz::require' <<<"$body"; then
        echo "boundary_lint: FAIL -- '${fn}' never calls authz::require; it cannot be enforcing the kernel's decision"
        FAIL=1
    fi
done

# Sanity-check the documented exception still describes reality: if
# admin_deactivate/admin_demote ever stop referencing Role::Admin directly
# (e.g. because someone routes them through the kernel too), this script's
# comment above becomes stale and should be updated to say so -- point that
# out rather than silently going quiet about it.
for admin_fn in admin_deactivate admin_demote; do
    admin_body="$(extract_fn "$admin_fn")"
    if [[ -n "$admin_body" ]] && ! grep -qE 'Role::Admin' <<<"$admin_body"; then
        echo "boundary_lint: NOTE -- '${admin_fn}' no longer contains a raw Role::Admin check; update this script's and the README's documented-exception note (this may be good news, but the doc claim needs to match)"
    fi
done

if [[ $FAIL -ne 0 ]]; then
    echo "boundary_lint: FAILED"
    exit 1
fi

echo "boundary_lint: OK -- get_article/edit_article/submit_article/publish_article contain no direct Role::* comparisons and each calls authz::require"
echo "boundary_lint: (admin_deactivate/admin_demote intentionally not scanned -- out of refactor scope, see README)"
