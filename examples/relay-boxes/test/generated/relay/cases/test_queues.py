"""Generated, additive tests pinning the `sort_into_queues` description."""
from __future__ import annotations

from datetime import date, timedelta

from relay.cases.model import Case
from relay.cases.queues import Queue, sort_into_queues

TODAY = date(2026, 8, 14)
KEYS = ["inbox", "working", "waiting", "breached", "resolved", "closed"]
LABELS = ["Inbox", "Working", "On hold", "SLA breached", "Resolved", "Closed"]


def c(id, state="new", severity="med", sla=None, subject="s"):
    return Case(id, subject, "acme", "dana", state, severity, None, sla)


def by_key(qs):
    return {q.key: q for q in qs}


def test_all_six_queues_in_order_with_labels_even_when_empty():
    qs = sort_into_queues([], TODAY)
    assert [q.key for q in qs] == KEYS
    assert [q.label for q in qs] == LABELS
    assert all(q.case_ids == [] for q in qs)


def test_returns_queue_objects():
    qs = sort_into_queues([c(1)], TODAY)
    assert all(isinstance(q, Queue) for q in qs)


def test_state_to_queue_mapping():
    cases = [c(1, "new"), c(2, "open"), c(3, "waiting"), c(4, "resolved"), c(5, "closed")]
    q = by_key(sort_into_queues(cases, TODAY))
    assert q["inbox"].case_ids == [1]
    assert q["working"].case_ids == [2]
    assert q["waiting"].case_ids == [3]
    assert q["resolved"].case_ids == [4]
    assert q["closed"].case_ids == [5]
    assert q["breached"].case_ids == []


def test_order_within_queue_is_severity_then_id():
    cases = [c(5, severity="low"), c(2, severity="med"), c(9, severity="high"),
             c(1, severity="low"), c(7, severity="high"), c(3, severity="med")]
    q = by_key(sort_into_queues(cases, TODAY))
    assert q["inbox"].case_ids == [7, 9, 2, 3, 1, 5]


def test_input_order_does_not_matter():
    cases = [c(i, state=s, severity=v, sla=TODAY - timedelta(days=i))
             for i, (s, v) in enumerate([("new", "low"), ("open", "high"), ("waiting", "med"),
                                         ("new", "high"), ("open", "low"), ("closed", "med")], start=1)]
    a = sort_into_queues(cases, TODAY)
    b = sort_into_queues(list(reversed(cases)), TODAY)
    assert a == b


def test_breached_is_cross_state_and_cases_are_also_in_state_queue():
    past = TODAY - timedelta(days=3)
    cases = [c(1, "new", sla=past), c(2, "open", sla=past), c(3, "waiting", sla=past)]
    q = by_key(sort_into_queues(cases, TODAY))
    assert q["breached"].case_ids == [1, 2, 3]
    assert q["inbox"].case_ids == [1]
    assert q["working"].case_ids == [2]
    assert q["waiting"].case_ids == [3]


def test_resolved_and_closed_are_never_breached():
    past = TODAY - timedelta(days=30)
    cases = [c(1, "resolved", sla=past), c(2, "closed", sla=past)]
    q = by_key(sort_into_queues(cases, TODAY))
    assert q["breached"].case_ids == []
    assert q["resolved"].case_ids == [1]
    assert q["closed"].case_ids == [2]


def test_due_today_or_later_or_none_is_not_breached():
    cases = [c(1, "open", sla=TODAY), c(2, "open", sla=TODAY + timedelta(days=1)), c(3, "open", sla=None)]
    q = by_key(sort_into_queues(cases, TODAY))
    assert q["breached"].case_ids == []
    assert q["working"].case_ids == [1, 2, 3]


def test_breached_boundary_is_strictly_before_today():
    cases = [c(1, "open", sla=TODAY - timedelta(days=1)), c(2, "open", sla=TODAY)]
    q = by_key(sort_into_queues(cases, TODAY))
    assert q["breached"].case_ids == [1]


def test_today_parameter_is_honoured():
    cases = [c(1, "open", sla=date(2026, 8, 20))]
    assert by_key(sort_into_queues(cases, date(2026, 8, 20)))["breached"].case_ids == []
    assert by_key(sort_into_queues(cases, date(2026, 8, 21)))["breached"].case_ids == [1]


def test_breached_queue_is_ordered_by_severity_then_id_not_by_state_or_date():
    far, near = TODAY - timedelta(days=30), TODAY - timedelta(days=1)
    cases = [c(4, "new", "low", far), c(2, "open", "high", near), c(8, "waiting", "high", far),
             c(1, "open", "med", near), c(3, "new", "low", near)]
    q = by_key(sort_into_queues(cases, TODAY))
    assert q["breached"].case_ids == [2, 8, 1, 3, 4]


def test_every_case_in_exactly_one_state_queue():
    cases = [c(i, s) for i, s in enumerate(["new", "open", "waiting", "resolved", "closed", "new", "open"], 1)]
    q = by_key(sort_into_queues(cases, TODAY))
    ids = sum((q[k].case_ids for k in ["inbox", "working", "waiting", "resolved", "closed"]), [])
    assert sorted(ids) == [1, 2, 3, 4, 5, 6, 7]


def test_does_not_mutate_input():
    cases = [c(3, severity="low"), c(1, severity="high")]
    snapshot = list(cases)
    sort_into_queues(cases, TODAY)
    assert cases == snapshot


def test_case_ids_are_ints_in_lists():
    qs = sort_into_queues([c(1)], TODAY)
    assert all(isinstance(q.case_ids, list) for q in qs)
    assert qs[0].case_ids == [1] and isinstance(qs[0].case_ids[0], int)


def test_resolved_and_closed_ordered_by_severity_then_id():
    cases = [c(1, "resolved", "low"), c(2, "resolved", "high"), c(3, "closed", "med"), c(4, "closed", "high")]
    q = by_key(sort_into_queues(cases, TODAY))
    assert q["resolved"].case_ids == [2, 1]
    assert q["closed"].case_ids == [4, 3]
