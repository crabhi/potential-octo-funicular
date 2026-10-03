"""Running a generated body inside a Monty micro-sandbox.

What a box body can touch is exactly what its reviewed signature hands it:

  * DATA parameters arrive as read-only views of reviewed dataclasses
    (attribute writes stay inside the sandbox; the host object is never
    mutated);
  * FUNCTION capabilities (`Callable[...]` parameters) arrive as host
    functions — every call's arguments and result are conformance-checked
    against the reviewed `Callable` type;
  * OBJECT capabilities (`Protocol` parameters) arrive as host objects
    whose callable surface is exactly the protocol's methods — nothing
    else on the object exists for the sandbox, and each call is checked
    against the protocol's annotations;
  * CONSTRUCTORS for the reviewed dataclasses in the box's closure.

No filesystem, no network, no environment, no clock beyond what is
passed in; CPU and memory are bounded. The result is conformance-checked
against the reviewed return type before reviewed code ever sees it.
"""

from __future__ import annotations

import atexit
import collections.abc
import dataclasses
import functools
import inspect
import threading
import typing
from typing import Any, get_args, get_origin

from pydantic_monty import (ClassInstance, ClassType, Monty, MontyError,
                            MontyRuntimeError, MontySyntaxError, MontyTypingError)

from .conform import ContractViolation, conform

LIMITS = {"max_feed_duration_secs": 2.0, "max_memory": 64 * 1024 * 1024,
          "max_recursion_depth": 200}

_pool: Monty | None = None
_lock = threading.Lock()


def pool() -> Monty:
    global _pool
    with _lock:
        if _pool is None:
            _pool = Monty(min_processes=1, max_processes=8)
            _pool.__enter__()
            atexit.register(_pool.__exit__, None, None, None)
        return _pool


class BoxError(RuntimeError):
    """A generated body failed: raised, timed out, or broke its contract."""

    def __init__(self, box: str, message: str):
        super().__init__(f"box `{box}`: {message}")
        self.box = box
        self.message = message


# -- crossing the boundary ----------------------------------------------------

class _Types:
    """ClassType wrappers for reviewed dataclasses (constructible only if the
    box's closure names them)."""

    def __init__(self, constructible: dict[str, type]):
        self.wrappers: dict[type, _TypeWrap] = {}
        for cls in constructible.values():
            self.wrappers[cls] = _TypeWrap(cls, self, init=True,
                                           instance_eager_attrs="all")

    def of(self, cls: type) -> _TypeWrap:
        if cls not in self.wrappers:  # visible, never constructible
            self.wrappers[cls] = _TypeWrap(cls, self, init=False,
                                           instance_eager_attrs="all")
        return self.wrappers[cls]

    def into(self, v: Any) -> Any:
        if dataclasses.is_dataclass(v) and not isinstance(v, type):
            return _DataWrap(v, self, eager_attrs="all", class_type=self.of(type(v)))
        if isinstance(v, list):
            return [self.into(x) for x in v]
        if isinstance(v, tuple):
            return tuple(self.into(x) for x in v)
        if isinstance(v, dict):
            return {k: self.into(x) for k, x in v.items()}
        return v


class _DataWrap(ClassInstance):
    def __init__(self, value: Any, types: _Types, **kw: Any):
        super().__init__(value, **kw)
        self._types = types

    def convert_value(self, name: str, value: Any) -> Any:
        return self._types.into(value)


class _TypeWrap(ClassType):
    def __init__(self, value: type, types: _Types, **kw: Any):
        super().__init__(value, **kw)
        self._types = types

    def convert_value(self, name: str, value: Any) -> Any:
        return self._types.into(value)

    def instance_wrapper(self, instance: Any) -> ClassInstance:
        return _DataWrap(instance, self._types, eager_attrs="all", class_type=self)


def protocol_methods(proto: type) -> dict[str, dict[str, Any]]:
    out = {}
    for name, fn in vars(proto).items():
        if not name.startswith("_") and inspect.isfunction(fn):
            out[name] = typing.get_type_hints(fn)
    return out


class _Capability(ClassInstance):
    """A host object seen through a reviewed Protocol: its methods, checked."""

    def __init__(self, obj: Any, proto: type, types: _Types, box: str, param: str):
        self._methods = protocol_methods(proto)
        super().__init__(obj, allowed_methods=set(self._methods))
        self._types, self._box, self._param = types, box, param
        self._proto = proto

    def call_method(self, name: str, args: tuple, kwargs: dict) -> Any:
        hints = self._methods.get(name)
        if hints is None:
            raise AttributeError(name)
        sig = inspect.signature(getattr(self._proto, name))
        bound = sig.bind(None, *args, **kwargs)
        for pname, val in list(bound.arguments.items())[1:]:
            _check(val, hints.get(pname, Any),
                   f"{self._box}: {self._param}.{name}({pname}=…)")
        result = getattr(self.value, name)(*args, **kwargs)
        _check(result, hints.get("return", Any),
               f"{self._box}: {self._param}.{name}() returned")
        return self._types.into(result)


def _check(value: Any, tp: Any, where: str) -> None:
    try:
        conform(value, tp, where)
    except ContractViolation as e:
        raise ContractViolation(str(e)) from None


def _function_capability(fn: Any, tp: Any, types: _Types, box: str, param: str):
    args = get_args(tp)
    params, ret = (args[0], args[1]) if args else (..., Any)

    def call(*a: Any) -> Any:
        if params is not ...:
            if len(a) != len(params):
                raise TypeError(f"{param}() takes {len(params)} arguments")
            for i, (v, t) in enumerate(zip(a, params)):
                _check(v, t, f"{box}: {param}(arg {i})")
        result = fn(*a)
        _check(result, ret, f"{box}: {param}() returned")
        return types.into(result)
    return call


def _is_protocol(tp: Any) -> bool:
    return isinstance(tp, type) and bool(getattr(tp, "_is_protocol", False))


def _is_callable(tp: Any) -> bool:
    return get_origin(tp) is collections.abc.Callable or tp is collections.abc.Callable


@functools.lru_cache(maxsize=None)
def _types_for(box: Any) -> _Types:
    return _Types(box.constructors)


# -- the call -----------------------------------------------------------------

def run_box(box: Any, args: tuple, kwargs: dict) -> Any:
    bound = box.signature.bind(*args, **kwargs)
    bound.apply_defaults()
    types = _types_for(box)
    inputs: dict[str, Any] = {name: w for cls, w in types.wrappers.items()
                              for name in [cls.__name__]}
    external: dict[str, Any] = {}
    call_args = []
    for pname, value in bound.arguments.items():
        tp = box.hints.get(pname, Any)
        var = f"_bx_{pname}"
        if _is_protocol(tp):
            inputs[var] = _Capability(value, tp, types, box.name, pname)
        elif _is_callable(tp):
            external[var] = _function_capability(value, tp, types, box.name, pname)
        else:
            _check(value, tp, f"{box.name}: argument {pname}")
            inputs[var] = types.into(value)
        call_args.append(f"{pname}={var}")
    if not box.impl_path.exists():
        raise BoxError(box.name, f"no implementation at {box.impl_path.name} "
                                 f"(generate one: python -m boxkit brief … {box.name})")
    code = box.impl_source() + f"\n\n{box.name}({', '.join(call_args)})\n"
    try:
        with pool().checkout(limits=LIMITS, script_name=f"impl/{box.name}.py") as s:
            result = s.feed_run(code, inputs=inputs, external_lookup=external)
    except ContractViolation:
        raise
    except (MontyRuntimeError, MontySyntaxError, MontyTypingError) as e:
        raise BoxError(box.name, e.display().strip().splitlines()[-1]) from None
    except MontyError as e:
        raise BoxError(box.name, f"sandbox failure: {e}") from None
    _check(result, box.hints.get("return", Any), f"{box.name}: result")
    return result


def typecheck(box: Any) -> str | None:
    """Type-check the generated body against the box's reviewed stub, inside
    Monty (ty). Returns the diagnostics, or None when clean."""
    code = box.impl_source() + f"\n\n_bx_contract: BoxkitContract = {box.name}\n"
    try:
        with pool().checkout(type_check=True, type_check_stubs=box.stub,
                             type_check_format="concise", limits=LIMITS,
                             script_name=f"impl/{box.name}.py") as s:
            s.feed_run(code)
    except MontyTypingError as e:
        return e.display().strip()
    except MontySyntaxError as e:
        return e.display().strip()
    except MontyRuntimeError:
        return None  # well-typed; runtime of a module body is not our concern
    return None
