"""REVIEWED — who uses Relay (HD-1, HD-7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["anonymous", "customer", "agent", "lead", "mailbot"]


@dataclass(frozen=True)
class Actor:
    """Someone (or something) using Relay. Staff and the robot have no org."""
    name: str
    role: Role
    org: str | None = None
    active: bool = True


ANONYMOUS = Actor("anonymous", "anonymous")
