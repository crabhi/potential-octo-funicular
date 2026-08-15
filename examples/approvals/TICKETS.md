# Clearance — the product spec, in product-owner English

Clearance is a miniature expense-claims service. It exists as the worked
example of the manual (`docs/manual.md`): small enough to read whole,
real enough to carry every mechanism — the rules below are the entire
application logic, and `./check.sh` holds them to the frozen gate.

## EX-1 — Organizations

Employees and managers belong to an organization and act only inside it:
they see, file and touch their own org's claims and nobody else's.
Finance is central — it belongs to no org and serves all of them.

## EX-2 — Receipts

A claim can be drafted freely, but it cannot be *submitted* without a
receipt attached. No receipt, no reimbursement request.

## EX-3 — Four eyes

Managers decide claims: approve or reject. Managers have expenses too,
so managers also file claims — and **nobody ever decides their own
claim**, manager or not. Someone else's eyes, always.

## EX-4 — Money

Only finance pays, and finance does nothing else: it reads and it pays.
A paid claim is a frozen record — nothing about it ever changes again.

## EX-5 — The loop, and leavers

Rejection is a loop, not a verdict: the author revises a rejected claim
back into draft, fixes it, and resubmits. Once anything is submitted it
is part of the record — drafts are the only thing you edit or delete.
Deactivated accounts can do nothing at all.
