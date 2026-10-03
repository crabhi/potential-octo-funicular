"""REVIEWED — who may do what to a case (HD-1…HD-7).

There are NO deny rules for "customers never triage", "staff never
reopen", "only leads close", "the mail robot does nothing else": the
allows are tight and silence denies; tests/relay/test_policy.py proves
each containment over the whole situation grid.
"""

from __future__ import annotations

from relay.policy import POLICY, Situation


@POLICY.deny("org_walls", """HD-1: customers see and touch only their own
    organization's cases — reading included, and a case can never be moved
    into or out of an organization by its customers.""", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and not s.same_org

@POLICY.deny("case_needs_subject", """HD-2: no case without a subject — a
    subjectless case cannot be triaged, routed or reported on.""", on=("case",))
def _(s: Situation) -> bool:
    return s.action == "open" and not s.case.subject.strip()

@POLICY.deny("only_assignee_resolves", """HD-4: a case is resolved by the agent
    it is assigned to; only a lead may resolve someone else's case.""", on=("case",))
def _(s: Situation) -> bool:
    return s.action == "resolve" and not s.mine and s.actor.role != "lead"

@POLICY.deny("breach_needs_lead", """HD-5: once the SLA is breached, an ordinary
    agent may no longer resolve the case — every breach gets senior eyes.""",
    on=("case",))
def _(s: Situation) -> bool:
    return s.action == "resolve" and s.breached and s.actor.role != "lead"

@POLICY.deny("sealed_after_resolution", """HD-2 + HD-6: a resolved or closed case
    is no longer editable, by anyone — reopen it (customers) or live with the
    record.""", on=("case",))
def _(s: Situation) -> bool:
    return s.case.state in ("resolved", "closed") and s.action == "edit"

@POLICY.allow("customer_opens", "HD-2: customers open cases (into their own org).",
              on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action == "open"

@POLICY.allow("customer_follows", "HD-1: everyone in the customer org follows "
              "the org's cases.", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action == "read"

@POLICY.allow("customer_edits", """HD-2: customers maintain their org's cases
    while they are being worked.""", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action == "edit"

@POLICY.allow("customer_replies", "HD-3: a customer reply pulls a waiting case "
              "back into the working queue.", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action == "reply"

@POLICY.allow("customer_reopens", "HD-4: the requester's side decides whether it "
              "is fixed — customers reopen resolved cases.", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "customer" and s.action == "reopen"

@POLICY.allow("staff_serve", """HD-3: staff work every org's cases: read, edit,
    open (a case taken by phone), triage, put on hold, resolve.""", on=("case",))
def _(s: Situation) -> bool:
    return s.staff and s.action in ("read", "edit", "open", "triage", "wait", "resolve")

@POLICY.allow("lead_closes", "HD-6: closing is the QA step, and it is a lead's.",
              on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "lead" and s.action == "close"

@POLICY.allow("mailbot_files", """HD-7: the mail robot opens cases from inbound
    email and files customer replies — its entire blast radius.""", on=("case",))
def _(s: Situation) -> bool:
    return s.actor.role == "mailbot" and s.action in ("open", "reply")
