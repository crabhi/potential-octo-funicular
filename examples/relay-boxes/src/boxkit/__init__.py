"""boxkit — reviewed contracts, generated bodies, Monty micro-sandboxes.

The DSL is plain Python plus a folder convention (src layout):

    src/<app>/            REVIEWED  — the app, organised by business area
    src/generated/<app>/  GENERATED — module generated.<app>.X holds the bodies
                          of every box declared in <app>.X; runs only in Monty
    test/<app>/, test/generated/<app>/   reviewed and generated tests

Provided:
    @blackbox            a typed, body-less signature + reviewed description
    Policy               guard rules; refusals are typed values naming the rule

Everything else (data model, state transitions, effects) is plain reviewed
Python in the app.
"""

from .contract import Box, blackbox, boxes_of
from .conform import ContractViolation, conform
from .policy import Policy, Rule
from .sandbox import BoxError

__all__ = ["Box", "BoxError", "ContractViolation", "Policy", "Rule",
           "blackbox", "boxes_of", "conform"]
