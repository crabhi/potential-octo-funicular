"""The framework's own guarantees, each tested against a hostile or broken
generated body (written into a throwaway app package per test)."""

from __future__ import annotations

import importlib
import sys
import textwrap
import time
import uuid

import pytest

from boxkit import BoxError, ContractViolation
from boxkit.sandbox import typecheck

MODEL = '''
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

Color = Literal["red", "blue"]

@dataclass(frozen=True)
class Item:
    name: str
    color: Color
    tags: list[str]

@dataclass(frozen=True)
class Summary:
    count: int
    names: list[str]

@dataclass(frozen=True)
class Secret:
    password: str
'''

BOXES = '''
from __future__ import annotations
from typing import Callable, Protocol
from boxkit import blackbox
from .model import Item, Summary

class Store(Protocol):
    def items(self) -> list[Item]: ...
    def named(self, name: str) -> Item | None: ...

@blackbox
def summarize(items: list[Item]) -> Summary:
    """Count the items and list their names."""
    ...

@blackbox
def via_store(store: Store, shout: Callable[[str], str]) -> str:
    """Shout the name of the first item in the store."""
    ...
'''

GOOD_SUMMARIZE = '''
def summarize(items: list[Item]) -> Summary:
    return Summary(count=len(items), names=[i.name for i in items])
'''


class HostStore:
    def __init__(self, items):
        self._items = items

    def items(self):
        return self._items

    def named(self, name):
        return next((i for i in self._items if i.name == name), None)

    def drop_all(self):  # not in the Store protocol
        self._items.clear()


@pytest.fixture()
def app(tmp_path):
    name = f"toy_{uuid.uuid4().hex[:8]}"
    pkg = tmp_path / name
    (pkg / "impl").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "model.py").write_text(MODEL)
    (pkg / "boxes.py").write_text(BOXES)
    sys.path.insert(0, str(tmp_path))
    boxes = importlib.import_module(f"{name}.boxes")
    model = importlib.import_module(f"{name}.model")

    def impl(box, body):
        (pkg / "impl" / f"{box.name}.py").write_text(
            box.header + "\n" + textwrap.dedent(body))
    yield boxes, model, impl
    sys.path.remove(str(tmp_path))


def items(model):
    return [model.Item("a", "red", ["x"]), model.Item("b", "blue", [])]


def test_a_good_body_returns_a_real_reviewed_value(app):
    boxes, model, impl = app
    impl(boxes.summarize, GOOD_SUMMARIZE)
    got = boxes.summarize(items(model))
    assert type(got) is model.Summary and got == model.Summary(2, ["a", "b"])
    assert typecheck(boxes.summarize) is None


def test_wrong_result_type_is_a_contract_violation_by_path(app):
    boxes, model, impl = app
    impl(boxes.summarize, '''
        def summarize(items):
            return Summary(count="two", names=[])
    ''')
    with pytest.raises(ContractViolation, match=r"summarize: result\.count: expected int"):
        boxes.summarize(items(model))


def test_type_errors_are_caught_before_running(app):
    boxes, model, impl = app
    impl(boxes.summarize, '''
        def summarize(items: list[Item]) -> Summary:
            return Summary(count=len(items), names=[i.title for i in items])
    ''')
    assert "unresolved-attribute" in typecheck(boxes.summarize)
    impl(boxes.summarize, '''
        def summarize(things: list[Item], extra: int) -> Summary:
            return Summary(count=0, names=[])
    ''')
    assert "BoxkitContract" in typecheck(boxes.summarize)


def test_no_filesystem_no_environment_no_host_modules(app):
    boxes, model, impl = app
    for body in ['open("/etc/passwd").read()', 'import os\nos.environ["HOME"]',
                 'import subprocess', 'import socket']:
        impl(boxes.summarize, f'''
def summarize(items):
    {body.replace(chr(10), chr(10) + "    ")}
    return Summary(count=0, names=[])
''')
        with pytest.raises(BoxError):
            boxes.summarize(items(model))


def test_only_contract_types_are_constructible(app):
    boxes, model, impl = app
    impl(boxes.summarize, '''
        def summarize(items):
            Secret("hunter2")
            return Summary(count=0, names=[])
    ''')
    with pytest.raises(BoxError, match="Secret"):
        boxes.summarize(items(model))


def test_host_data_is_never_mutated(app):
    boxes, model, impl = app
    impl(boxes.summarize, '''
        def summarize(items):
            items[0].tags.append("pwned")
            items.clear()
            return Summary(count=0, names=[])
    ''')
    data = items(model)
    boxes.summarize(data)
    assert data == items(model)


def test_capability_surface_is_exactly_the_protocol(app):
    boxes, model, impl = app
    store = HostStore(items(model))
    impl(boxes.via_store, '''
        def via_store(store, shout):
            return shout(store.items()[0].name)
    ''')
    assert boxes.via_store(store, str.upper) == "A"
    impl(boxes.via_store, '''
        def via_store(store, shout):
            store.drop_all()
            return "done"
    ''')
    with pytest.raises(BoxError, match="drop_all"):
        boxes.via_store(store, str.upper)
    assert len(store.items()) == 2
    impl(boxes.via_store, '''
        def via_store(store, shout):
            return store._items
    ''')
    with pytest.raises(BoxError):
        boxes.via_store(store, str.upper)


def test_capability_calls_are_conformance_checked(app):
    boxes, model, impl = app
    impl(boxes.via_store, '''
        def via_store(store, shout):
            store.named(42)
            return "x"
    ''')
    with pytest.raises((BoxError, ContractViolation), match="name"):
        boxes.via_store(HostStore(items(model)), str.upper)
    impl(boxes.via_store, '''
        def via_store(store, shout):
            return shout(7)
    ''')
    with pytest.raises((BoxError, ContractViolation), match="shout"):
        boxes.via_store(HostStore(items(model)), str.upper)


def test_runaway_bodies_are_stopped(app):
    boxes, model, impl = app
    impl(boxes.summarize, '''
        def summarize(items):
            while True:
                pass
    ''')
    t = time.time()
    with pytest.raises(BoxError, match="TimeoutError"):
        boxes.summarize(items(model))
    assert time.time() - t < 10
    impl(boxes.summarize, '''
        def summarize(items):
            x = [0] * 10**9
            return Summary(count=0, names=[])
    ''')
    with pytest.raises(BoxError, match="MemoryError"):
        boxes.summarize(items(model))


def test_spec_hash_tracks_exactly_the_reviewed_closure(app, tmp_path):
    boxes, model, impl = app
    s = boxes.summarize
    assert [x.name for x in s.closure] == ["Color", "Item", "Summary"]
    assert "Secret" not in s.stub and "password" not in s.stub
    assert set(s.constructors) == {"Item", "Summary"}
    impl(s, GOOD_SUMMARIZE)
    assert s.impl_spec() == s.spec_hash
