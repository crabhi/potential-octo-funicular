"""REVIEWED — refusals as values, and the guard-rule registry.

Rules live with the business area they govern (relay/cases/rules.py,
relay/thread/rules.py) and register here. Any matching deny refuses —
the first registered names the refusal; otherwise an allow must match;
silence denies. Every rule names the entities it governs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from boxkit import Policy
from relay.cases.model import Case
from relay.people import Actor
from relay.thread.model import Attachment, Comment


@dataclass(frozen=True)
class Denied:
    """A refusal, as a value: the rule that refused and its description."""
    rule: str
    reason: str


@dataclass(frozen=True)
class Affordance:
    """Whether `actor` may perform `action` right now, and if not, why."""
    action: str
    allowed: bool
    rule: str | None
    reason: str | None


@dataclass(frozen=True)
class Situation:
    """Everything a rule may look at. For thread/evidence decisions `case`
    is the live PARENT case — the kernel joins it in, never the caller."""
    actor: Actor
    action: str
    case: Case
    today: date
    comment: Comment | None = None
    attachment: Attachment | None = None

    @property
    def staff(self) -> bool:
        return self.actor.role in ("agent", "lead")

    @property
    def same_org(self) -> bool:
        return self.actor.org is not None and self.actor.org == self.case.org

    @property
    def mine(self) -> bool:
        return self.case.assignee is not None and self.case.assignee == self.actor.name

    @property
    def breached(self) -> bool:
        return self.case.sla_due is not None and self.case.sla_due < self.today


POLICY: Policy[Situation, Denied] = Policy(Denied)
ALL = ("case", "comment", "attachment")
CHILDREN = ("comment", "attachment")


@POLICY.deny("deny_inactive", "A deactivated account can do nothing at all.", on=ALL)
def _(s: Situation) -> bool:
    return not s.actor.active


def lifecycle_refusal(entity: str, action: str, state: str) -> Denied:
    return Denied("lifecycle", f"A {entity} in state '{state}' has no '{action}'.")
