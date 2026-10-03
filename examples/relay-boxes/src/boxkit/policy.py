"""Guard rules: named deny/allow predicates, refusals as values.

The one piece of policy vocabulary boxkit provides. State transitions are
NOT part of it: they are plain reviewed data in the app's model (a dict
from (state, action) to the next state) and plain reviewed code in its
kernel.
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Generic, Literal, TypeVar

R = TypeVar("R")
S = TypeVar("S")


@dataclasses.dataclass(frozen=True)
class Rule(Generic[S]):
    id: str
    description: str
    effect: Literal["deny", "allow"]
    entities: tuple[str, ...]
    when: Callable[[S], bool]


class Policy(Generic[S, R]):
    """Guard rules: any matching deny refuses (first in declaration order
    names the refusal); otherwise some allow must match; silence denies.

    Every rule names the entities it governs — there is no default. (The
    rule-engine prototype defaulted untagged rules to the root entity,
    which failed OPEN for global denies; making the tag mandatory removes
    that sharp edge by construction.)"""

    def __init__(self, refusal: Callable[[str, str], R]):
        self.rules: list[Rule[S]] = []
        self.refusal = refusal

    def _add(self, effect: Literal["deny", "allow"], rule_id: str,
             description: str, entities: tuple[str, ...]):
        if not entities:
            raise ValueError(f"rule {rule_id}: name the entities it governs")
        if any(r.id == rule_id for r in self.rules):
            raise ValueError(f"duplicate rule id {rule_id}")

        def register(fn: Callable[[S], bool]) -> Callable[[S], bool]:
            self.rules.append(Rule(rule_id, " ".join(description.split()),
                                   effect, entities, fn))
            return fn
        return register

    def deny(self, rule_id: str, description: str, *, on: tuple[str, ...]):
        return self._add("deny", rule_id, description, on)

    def allow(self, rule_id: str, description: str, *, on: tuple[str, ...]):
        return self._add("allow", rule_id, description, on)

    def decide(self, entity: str, situation: S) -> R | None:
        """None = allowed; otherwise the refusal naming the rule."""
        mine = [r for r in self.rules if entity in r.entities]
        for r in mine:
            if r.effect == "deny" and r.when(situation):
                return self.refusal(r.id, r.description)
        if any(r.effect == "allow" and r.when(situation) for r in mine):
            return None
        return self.refusal("default_deny",
                            "No rule grants this — silence denies.")
