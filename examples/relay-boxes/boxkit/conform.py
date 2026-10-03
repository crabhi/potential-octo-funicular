"""Runtime conformance: does a value inhabit a (reviewed) type annotation?

Every value crossing a box boundary is checked here, in both directions:
data going in, results coming out, arguments a sandbox passes to a host
capability and what that capability returns. The sandbox can construct
host dataclasses, but a dataclass does not validate its own fields — so
`Queue(key=5)` from generated code is caught here, by path, not later as
a confusing crash in reviewed code.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import types
import typing
from typing import Any, Literal, Union, get_args, get_origin


class ContractViolation(TypeError):
    """A value does not inhabit the type its reviewed contract declares."""


_hints_cache: dict[type, dict[str, Any]] = {}


def hints(cls: type) -> dict[str, Any]:
    if cls not in _hints_cache:
        _hints_cache[cls] = typing.get_type_hints(cls)
    return _hints_cache[cls]


def conform(value: Any, tp: Any, path: str = "value") -> None:
    """Raise ContractViolation (naming the path) unless `value` : `tp`."""
    if tp is Any or tp is object:
        return
    if tp is None or tp is type(None):
        if value is not None:
            raise ContractViolation(f"{path}: expected None, got {_show(value)}")
        return
    origin = get_origin(tp)

    if origin is Literal:
        if not any(value == a and type(value) is type(a) for a in get_args(tp)):
            raise ContractViolation(
                f"{path}: expected one of {list(get_args(tp))}, got {_show(value)}")
        return
    if origin is Union or origin is types.UnionType:
        errors = []
        for alt in get_args(tp):
            try:
                conform(value, alt, path)
                return
            except ContractViolation as e:
                errors.append(str(e))
        raise ContractViolation(
            f"{path}: {_show(value)} matches no alternative of {_name(tp)}")
    if origin in (list, collections.abc.Sequence):
        if not isinstance(value, list):
            raise ContractViolation(f"{path}: expected list, got {_show(value)}")
        (item,) = get_args(tp) or (Any,)
        for i, v in enumerate(value):
            conform(v, item, f"{path}[{i}]")
        return
    if origin is tuple:
        if not isinstance(value, tuple):
            raise ContractViolation(f"{path}: expected tuple, got {_show(value)}")
        args = get_args(tp)
        if len(args) == 2 and args[1] is Ellipsis:
            for i, v in enumerate(value):
                conform(v, args[0], f"{path}[{i}]")
        else:
            if len(args) != len(value):
                raise ContractViolation(f"{path}: expected {len(args)}-tuple")
            for i, (v, a) in enumerate(zip(value, args)):
                conform(v, a, f"{path}[{i}]")
        return
    if origin in (dict, collections.abc.Mapping):
        if not isinstance(value, dict):
            raise ContractViolation(f"{path}: expected dict, got {_show(value)}")
        k_tp, v_tp = get_args(tp) or (Any, Any)
        for k, v in value.items():
            conform(k, k_tp, f"{path} key")
            conform(v, v_tp, f"{path}[{k!r}]")
        return
    if origin is collections.abc.Callable or tp is collections.abc.Callable:
        if not callable(value):
            raise ContractViolation(f"{path}: expected a callable, got {_show(value)}")
        return
    if isinstance(tp, type) and getattr(tp, "_is_protocol", False):
        return  # capabilities are checked method by method at call time
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        if type(value) is not tp:
            raise ContractViolation(
                f"{path}: expected {tp.__name__}, got {_show(value)}")
        for f in dataclasses.fields(tp):
            conform(getattr(value, f.name), hints(tp)[f.name], f"{path}.{f.name}")
        return
    if tp is bool:
        if type(value) is not bool:
            raise ContractViolation(f"{path}: expected bool, got {_show(value)}")
        return
    if tp is int:
        if type(value) is not int:  # bool is not an int here
            raise ContractViolation(f"{path}: expected int, got {_show(value)}")
        return
    if tp is float:
        if type(value) not in (int, float):
            raise ContractViolation(f"{path}: expected float, got {_show(value)}")
        return
    if tp is datetime.date:
        if type(value) is not datetime.date:
            raise ContractViolation(f"{path}: expected date, got {_show(value)}")
        return
    if isinstance(tp, type):
        if not isinstance(value, tp):
            raise ContractViolation(
                f"{path}: expected {tp.__name__}, got {_show(value)}")
        return
    raise ContractViolation(f"{path}: unsupported contract type {tp!r}")


def _show(v: Any) -> str:
    r = repr(v)
    return f"{type(v).__name__} {r[:60]}{'…' if len(r) > 60 else ''}"


def _name(tp: Any) -> str:
    return getattr(tp, "__name__", None) or str(tp).replace("typing.", "")
