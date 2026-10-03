"""REVIEWED — the desk's queues: a contract, with its body generated in
generated.relay.cases.queues."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal

from boxkit import blackbox
from relay.cases.model import Case

QueueKey = Literal["inbox", "working", "waiting", "breached", "resolved", "closed"]


@dataclass(frozen=True)
class Queue:
    key: QueueKey
    label: str
    case_ids: list[int]


QueueSorter = Callable[[list[Case], date], list[Queue]]


@blackbox
def sort_into_queues(cases: list[Case], today: date) -> list[Queue]:
    """Partition the cases a viewer can see into the desk's six queues, in
    this order and with these labels: inbox "Inbox" (state new), working
    "Working" (open), waiting "On hold" (waiting), breached "SLA breached",
    resolved "Resolved", closed "Closed". "SLA breached" is a cross-state
    view: every case in new/open/waiting whose sla_due is before `today`
    (such a case is ALSO in its state queue). Within a queue, cases are
    ordered by severity (high, med, low), then by id ascending. Every queue
    is returned, empty or not."""
    ...
