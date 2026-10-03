"""REVIEWED — the policy, exhausted over a situation grid.

The guard rules are plain Python predicates over finite vocabularies, so
the safety properties of the rule-engine Relay (S1–S29) and its
witnesses (P1–P16) can be checked over every combination of
representative values: every role × org × active flag × case state ×
assignee × SLA × subject × comment/attachment shape × action. Each
property is the frozen gate item it was in rulesets/helpdesk/safety.yaml.
"""

from __future__ import annotations

import itertools
from datetime import date

from relay.cases.lifecycle import CASE, CASE_ACTIONS
from relay.cases.model import Case
from relay.kernel import ActorView, Desk
from relay.people import Actor
from relay.thread.lifecycle import (
    ATTACHMENT,
    ATTACHMENT_ACTIONS,
    COMMENT,
    COMMENT_ACTIONS,
)
from relay.thread.model import Attachment, Comment

TODAY = date(2026, 8, 14)
DESK = Desk(TODAY, [])

ACTORS = [Actor(n, r, o, act)
          for (n, r, o) in [("cust", "customer", "acme"), ("cust", "customer", "zephyr"),
                            ("agent", "agent", None), ("lead", "lead", None),
                            ("bot", "mailbot", None), ("anon", "anonymous", None)]
          for act in (True, False)]
CASES = [Case(1, subj, org, "cust", state, "med", assignee, sla)
         for state in CASE.states
         for org in ("acme", "zephyr")
         for assignee in (None, "agent", "lead", "other")
         for sla in (None, date(2026, 8, 1), date(2026, 9, 1))
         for subj in ("", "Printer on fire")]
COMMENTS = [Comment(1, 1, author, body, internal, state)
            for author in ("cust", "agent", "lead", "bot", "other")
            for body in ("", "hello")
            for internal in (False, True)
            for state in COMMENT.states]
ATTACHMENTS = [Attachment(1, 1, author, fn, state)
               for author in ("cust", "agent", "lead", "bot", "other")
               for fn in ("", "trace.log")
               for state in ATTACHMENT.states]


def case_grid():
    for a, c, act in itertools.product(ACTORS, CASES, CASE_ACTIONS):
        yield a, c, act, DESK.decide_case(a, act, c) is None


def comment_grid():
    for a, c, m, act in itertools.product(ACTORS, CASES[::2], COMMENTS, COMMENT_ACTIONS):
        yield a, c, m, act, DESK.decide_comment(a, act, c, m) is None


def attachment_grid():
    for a, c, x, act in itertools.product(ACTORS, CASES[::2], ATTACHMENTS, ATTACHMENT_ACTIONS):
        yield a, c, x, act, DESK.decide_attachment(a, act, c, x) is None


CASE_G = list(case_grid())
COMMENT_G = list(comment_grid())
ATTACH_G = list(attachment_grid())
STAFF = ("agent", "lead")


def breached(c: Case) -> bool:
    return c.sla_due is not None and c.sla_due < TODAY


def test_grid_is_large_enough_to_mean_something():
    assert len(CASE_G) == 12 * 240 * 9          # 25,920 case situations
    assert len(COMMENT_G) == 12 * 120 * 40 * 3  # 172,800 thread situations
    assert len(ATTACH_G) == 12 * 120 * 20 * 3   # 86,400 evidence situations


# ---- safety: never ---------------------------------------------------------

def test_S1_S14_S21_org_walls_in_every_entity():
    for a, c, act, ok in CASE_G:
        if a.role == "customer" and a.org != c.org:
            assert not ok, (a, c, act)
    for a, c, _, act, ok in COMMENT_G + ATTACH_G:
        if a.role == "customer" and a.org != c.org:
            assert not ok, (a, c, act)


def test_S2_S20_S27_public_sees_and_does_nothing():
    for row in CASE_G + COMMENT_G + ATTACH_G:
        if row[0].role == "anonymous":
            assert not row[-1], row


def test_S3_S28_S29_inactive_accounts_do_nothing():
    for row in CASE_G + COMMENT_G + ATTACH_G:
        if not row[0].active:
            assert not row[-1], row


def test_S4_S17_S23_nothing_is_deleted_or_edited_after_the_fact():
    for cls in (Desk, ActorView):
        assert not [m for m in dir(cls) if "delete" in m or "purge" in m]
    assert "edit" not in COMMENT_ACTIONS and "edit" not in ATTACHMENT_ACTIONS
    assert COMMENT.terminal == ("redacted",) and ATTACHMENT.terminal == ("removed",)


def test_S5_no_case_without_subject():
    for a, c, act, ok in CASE_G:
        if act == "open" and not c.subject.strip():
            assert not ok


def test_S6_S11_staff_states_are_staff_only_and_closing_is_a_leads():
    for a, c, act, ok in CASE_G:
        if ok and act in ("triage", "wait", "resolve"):
            assert a.role in STAFF
        if ok and act == "close":
            assert a.role == "lead"


def test_S7_S8_resolution_is_assignee_or_lead_and_breaches_escalate():
    for a, c, act, ok in CASE_G:
        if ok and act == "resolve":
            assert a.role == "lead" or c.assignee == a.name
            if breached(c):
                assert a.role == "lead"


def test_S9_S10_resolved_is_sealed_and_closed_is_a_record():
    for a, c, act, ok in CASE_G:
        if ok and act == "edit":
            assert c.state not in ("resolved", "closed")
        if ok and c.state == "closed":
            assert act in ("read", "open")  # "open" judges a draft, not this row


def test_S12_staff_never_reopen():
    for a, c, act, ok in CASE_G:
        if ok and act == "reopen":
            assert a.role == "customer"


def test_S13_S19_S26_the_mail_robots_blast_radius():
    for a, c, act, ok in CASE_G:
        if ok and a.role == "mailbot":
            assert act in ("open", "reply")
    for a, c, m, act, ok in COMMENT_G:
        if ok and a.role == "mailbot":
            assert act == "post"
    for a, c, x, act, ok in ATTACH_G:
        if ok and a.role == "mailbot":
            assert act == "attach"


def test_S15_internal_notes_stay_inside():
    for a, c, m, act, ok in COMMENT_G:
        if ok and m.internal:
            assert a.role in STAFF


def test_S16_S25_closing_seals_thread_and_evidence():
    for a, c, _, act, ok in COMMENT_G + ATTACH_G:
        if ok and c.state == "closed":
            assert act == "read"


def test_S18_only_leads_redact():
    for a, c, m, act, ok in COMMENT_G:
        if ok and act == "redact":
            assert a.role == "lead" and m.state == "posted"


def test_S22_evidence_only_while_working():
    for a, c, x, act, ok in ATTACH_G:
        if ok and act == "attach":
            assert c.state in ("new", "open", "waiting") and x.filename.strip()


def test_S24_removal_is_author_or_lead():
    for a, c, x, act, ok in ATTACH_G:
        if ok and act == "remove":
            assert a.role == "lead" or x.author == a.name


def test_comments_need_a_body():
    for a, c, m, act, ok in COMMENT_G:
        if ok and act == "post":
            assert m.body.strip()


# ---- liveness: witnesses (the gate's other direction) ----------------------

def exists(grid, pred) -> bool:
    return any(pred(*row) for row in grid)


def test_P_witnesses_every_feature_is_actually_possible():
    W = {
        "P1 customers open":       exists(CASE_G, lambda a, c, act, ok: ok and act == "open" and a.role == "customer"),
        "P2 agents triage":        exists(CASE_G, lambda a, c, act, ok: ok and act == "triage" and a.role == "agent"),
        "P3 assignee resolves":    exists(CASE_G, lambda a, c, act, ok: ok and act == "resolve" and a.role == "agent"),
        "P4 lead resolves breach": exists(CASE_G, lambda a, c, act, ok: ok and act == "resolve" and breached(c)),
        "P5 customers reply":      exists(CASE_G, lambda a, c, act, ok: ok and act == "reply" and a.role == "customer"),
        "P6 customers reopen":     exists(CASE_G, lambda a, c, act, ok: ok and act == "reopen"),
        "P7 leads close":          exists(CASE_G, lambda a, c, act, ok: ok and act == "close"),
        "P8 robot opens":          exists(CASE_G, lambda a, c, act, ok: ok and act == "open" and a.role == "mailbot"),
        "P9 staff cross-org":      exists(CASE_G, lambda a, c, act, ok: ok and a.role == "agent" and c.org == "zephyr"),
        "P10 customers discuss":   exists(COMMENT_G, lambda a, c, m, act, ok: ok and act == "post" and a.role == "customer"),
        "P11 staff note internally": exists(COMMENT_G, lambda a, c, m, act, ok: ok and act == "post" and m.internal),
        "P12 leads redact":        exists(COMMENT_G, lambda a, c, m, act, ok: ok and act == "redact"),
        "P13 closed thread readable": exists(COMMENT_G, lambda a, c, m, act, ok: ok and act == "read" and c.state == "closed" and a.role == "customer"),
        "P14 robot files bodies":  exists(COMMENT_G, lambda a, c, m, act, ok: ok and act == "post" and a.role == "mailbot"),
        "P15 customers attach":    exists(ATTACH_G, lambda a, c, x, act, ok: ok and act == "attach" and a.role == "customer"),
        "P16 authors remove":      exists(ATTACH_G, lambda a, c, x, act, ok: ok and act == "remove" and a.role == "agent"),
        # P17–P21 were added after a rule-deletion mutation run (DEVLOG):
        # each of these allows could be deleted with P1–P16 still green
        "P17 customers follow":    exists(CASE_G, lambda a, c, act, ok: ok and act == "read" and a.role == "customer"),
        "P18 customers maintain":  exists(CASE_G, lambda a, c, act, ok: ok and act == "edit" and a.role == "customer"),
        "P19 staff attach":        exists(ATTACH_G, lambda a, c, x, act, ok: ok and act == "attach" and a.role in STAFF),
        "P20 leads remove others'": exists(ATTACH_G, lambda a, c, x, act, ok: ok and act == "remove" and a.role == "lead" and x.author != a.name),
        "P21 robot attaches":      exists(ATTACH_G, lambda a, c, x, act, ok: ok and act == "attach" and a.role == "mailbot"),
    }
    assert all(W.values()), [k for k, v in W.items() if not v]


def test_lifecycles_are_well_formed_and_frozen():
    for lc in (CASE, COMMENT, ATTACHMENT):
        assert lc.problems() == []
    assert [(t.action, t.source, t.target) for t in CASE.transitions] == [
        ("triage", "new", "open"), ("wait", "open", "waiting"),
        ("reply", "waiting", "open"), ("resolve", "open", "resolved"),
        ("reopen", "resolved", "open"), ("close", "resolved", "closed")]
