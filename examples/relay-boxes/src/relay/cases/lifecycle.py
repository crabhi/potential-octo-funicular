"""REVIEWED — the case's states and transitions (HD-2…HD-6)."""

from __future__ import annotations

from boxkit import Lifecycle, T
from relay.cases.model import CaseState

CASE = Lifecycle("case", CaseState, initial="new", terminal=("closed",), transitions=[
    T("triage",  "new",      "open"),       # HD-3
    T("wait",    "open",     "waiting"),    # HD-3
    T("reply",   "waiting",  "open"),       # HD-3: a customer reply pulls it back
    T("resolve", "open",     "resolved"),   # HD-4/5
    T("reopen",  "resolved", "open"),       # HD-4: the requester disputes
    T("close",   "resolved", "closed"),     # HD-6: the QA step
])


# Non-transition actions. There is no delete anywhere: HD-6 ("nothing in
# Relay is ever deleted") holds because no such method exists.
CASE_ACTIONS = ("open", "read", "edit", *CASE.actions)
