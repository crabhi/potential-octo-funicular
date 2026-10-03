"""The reviewed core vocabulary: lifecycles (state transitions) and guard
rules. Both are plain data + small predicates a developer reads in one
sitting; both are mechanically checked (`Lifecycle.problems`) and
rendered into the review digest (`python -m boxkit digest`).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Generic, Literal, TypeVar, get_args

R = TypeVar("R")
S = TypeVar("S")


@dataclasses.dataclass(frozen=True)
class T:
    """One transition: `action` moves an entity from `source` to `target`."""
    action: str
    source: str
    target: str


class Lifecycle:
    """A finite state machine over a `Literal[...]` state type."""

    def __init__(self, entity: str, states: Any, initial: str,
                 transitions: list[T], terminal: tuple[str, ...] = ()):
        self.entity = entity
        self.states: tuple[str, ...] = get_args(states)
        self.initial = initial
        self.transitions = list(transitions)
        self.terminal = terminal

    @property
    def actions(self) -> list[str]:
        return list(dict.fromkeys(t.action for t in self.transitions))

    def step(self, state: str, action: str) -> str | None:
        for t in self.transitions:
            if t.source == state and t.action == action:
                return t.target
        return None

    def actions_from(self, state: str) -> list[str]:
        return [t.action for t in self.transitions if t.source == state]

    def reachable(self) -> set[str]:
        seen, todo = set(), [self.initial]
        while todo:
            s = todo.pop()
            if s not in seen:
                seen.add(s)
                todo += [t.target for t in self.transitions if t.source == s]
        return seen

    def problems(self) -> list[str]:
        """Structural defects: undeclared states, nondeterminism, states no
        path reaches, dead ends that are not declared terminal, and
        terminal states that still have exits."""
        out = []
        declared = set(self.states)
        if self.initial not in declared:
            out.append(f"{self.entity}: initial state {self.initial!r} undeclared")
        seen = set()
        for t in self.transitions:
            for s in (t.source, t.target):
                if s not in declared:
                    out.append(f"{self.entity}: {t.action} uses undeclared state {s!r}")
            if (t.source, t.action) in seen:
                out.append(f"{self.entity}: {t.action} from {t.source} is ambiguous")
            seen.add((t.source, t.action))
        for s in sorted(declared - self.reachable()):
            out.append(f"{self.entity}: state {s!r} is unreachable from {self.initial!r}")
        for s in self.states:
            exits = self.actions_from(s)
            if not exits and s not in self.terminal:
                out.append(f"{self.entity}: {s!r} is a dead end but not declared terminal")
            if exits and s in self.terminal:
                out.append(f"{self.entity}: terminal {s!r} has exits {exits}")
        return out

    def mermaid(self) -> str:
        lines = ["stateDiagram-v2", f"    [*] --> {self.initial}"]
        lines += [f"    {t.source} --> {t.target}: {t.action}" for t in self.transitions]
        lines += [f"    {s} --> [*]" for s in self.terminal]
        return "\n".join(lines)


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
