"""YAML loading for the restricted typed invariant schema.

File shape::

    variables:
      phase:
        type: enum
        values: [expand, backfill, contract, done]
      version_skew:
        type: int
        min: 0
        max: 3
      old_running:
        type: bool

    invariants:
      - name: inv_skew_bound
        description: "At most one version of skew may run concurrently."
        formula: "version_skew <= 1"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml
import z3

from .expr import ExprCompiler

VALID_TYPES = {"bool", "int", "enum"}


@dataclass
class VarSpec:
    name: str
    type: str
    min: Optional[int] = None
    max: Optional[int] = None
    values: Optional[List[str]] = None
    z3var: Any = None
    consts: Optional[Dict[str, Any]] = None


@dataclass
class Invariant:
    name: str
    description: str
    formula: str
    term: Any = None


@dataclass
class Model:
    variables: Dict[str, VarSpec]
    invariants: List[Invariant]
    domain_constraints: List[Any] = field(default_factory=list)
    compiler: Optional[ExprCompiler] = None

    def invariant(self, name: str) -> Invariant:
        for inv in self.invariants:
            if inv.name == name:
                return inv
        raise KeyError(f"no invariant named {name!r}")


class SchemaError(Exception):
    pass


def _build_variable(name: str, spec: dict) -> VarSpec:
    vtype = spec.get("type")
    if vtype not in VALID_TYPES:
        raise SchemaError(
            f"variable {name!r}: type must be one of {sorted(VALID_TYPES)}, got {vtype!r}"
        )
    if vtype == "bool":
        return VarSpec(name=name, type="bool", z3var=z3.Bool(name))
    if vtype == "int":
        return VarSpec(
            name=name,
            type="int",
            min=spec.get("min"),
            max=spec.get("max"),
            z3var=z3.Int(name),
        )
    # enum
    values = spec.get("values")
    if not values or not isinstance(values, list):
        raise SchemaError(f"variable {name!r}: enum requires a non-empty 'values' list")
    sort, consts = z3.EnumSort(f"{name}__T", values)
    return VarSpec(
        name=name,
        type="enum",
        values=values,
        z3var=z3.Const(name, sort),
        consts=dict(zip(values, consts)),
    )


def load_model(path: str) -> Model:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    raw_vars = data.get("variables") or {}
    variables: Dict[str, VarSpec] = {}
    for name, spec in raw_vars.items():
        variables[name] = _build_variable(name, spec)

    z3vars = {name: v.z3var for name, v in variables.items()}
    compiler = ExprCompiler(variables, z3vars)

    domain_constraints = []
    for v in variables.values():
        if v.type == "int":
            if v.min is not None:
                domain_constraints.append(v.z3var >= v.min)
            if v.max is not None:
                domain_constraints.append(v.z3var <= v.max)

    invariants: List[Invariant] = []
    for item in data.get("invariants") or []:
        try:
            name = item["name"]
            formula = item["formula"]
        except KeyError as e:
            raise SchemaError(f"invariant entry missing required key: {e}") from e
        description = item.get("description", "")
        inv = Invariant(name=name, description=description, formula=formula)
        try:
            inv.term = compiler.compile(formula)
        except Exception as e:
            raise SchemaError(f"invariant {name!r}: {e}") from e
        invariants.append(inv)

    names = [i.name for i in invariants]
    if len(names) != len(set(names)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise SchemaError(f"duplicate invariant names: {dupes}")

    return Model(
        variables=variables,
        invariants=invariants,
        domain_constraints=domain_constraints,
        compiler=compiler,
    )
