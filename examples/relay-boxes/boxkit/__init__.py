"""boxkit — reviewed contracts, generated bodies, Monty micro-sandboxes.

The DSL is plain Python plus a file convention (see README):

    REVIEWED  <app>/model.py, machine.py, boxes.py, shell.py, tests/reviewed/
              — hash-locked in <app>/REVIEW.lock
    GENERATED <app>/impl/<box>.py (runs only inside Monty), tests/generated/

Decorators and helpers:
    @blackbox            a typed, body-less signature + reviewed description
    Lifecycle, T         state transitions (checked, rendered for review)
    Policy               guard rules; refusals are typed values naming the rule
"""

from .contract import Box, blackbox, boxes_of
from .conform import ContractViolation, conform
from .machine import Lifecycle, Policy, Rule, T
from .sandbox import BoxError

__all__ = ["Box", "BoxError", "ContractViolation", "Lifecycle", "Policy",
           "Rule", "T", "blackbox", "boxes_of", "conform"]
