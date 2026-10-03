"""REVIEWED — `sort_into_queues` (relay.cases.queues): order, labels, and the
cross-state SLA-breached queue."""

from __future__ import annotations

from datetime import date

from relay.cases.model import Case
from relay.cases.queues import sort_into_queues
from relay.web.seed import TODAY


def mk(i, state, sev="med", due=None):
    return Case(i, f"c{i}", "acme", "dana", state, sev, None, due)


def test_queues_order_labels_and_cross_state_breach():
    past, future = date(2026, 8, 1), date(2026, 9, 1)
    cases = [mk(1, "new", "low", past), mk(2, "new", "high"), mk(3, "open", "med", past),
             mk(4, "waiting", "high", past), mk(5, "resolved", "high", past),
             mk(6, "closed", "low", past), mk(7, "new", "high", future)]
    qs = sort_into_queues(cases, TODAY)
    assert [(q.key, q.label) for q in qs] == [
        ("inbox", "Inbox"), ("working", "Working"), ("waiting", "On hold"),
        ("breached", "SLA breached"), ("resolved", "Resolved"), ("closed", "Closed")]
    got = {q.key: q.case_ids for q in qs}
    assert got["inbox"] == [2, 7, 1]            # high before low, then id
    assert got["breached"] == [4, 3, 1]         # resolved/closed never breach
    assert got["resolved"] == [5] and got["closed"] == [6]
    assert sort_into_queues([], TODAY)[0].case_ids == []


def test_due_today_is_not_breached():
    qs = sort_into_queues([mk(1, "open", due=TODAY)], TODAY)
    assert {q.key: q.case_ids for q in qs}["breached"] == []
