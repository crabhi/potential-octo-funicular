"""The reviewed side of a black box: its contract, extracted from source.

A box is declared in REVIEWED code as a body-less, typed function whose
docstring is its description:

    @blackbox
    def sort_into_queues(cases: list[Case], today: date) -> list[Queue]:
        \"\"\"Partition the cases a viewer can see into the desk's queues…\"\"\"
        ...

From that declaration boxkit derives, mechanically:

  * the STUB — exactly the reviewed types the box can see (the transitive
    closure of names in its signature, copied verbatim from the reviewed
    modules, dependencies first) plus a `BoxkitContract_<name>` protocol
    for its signature. The generated module is type-checked against the
    stub of all its boxes inside Monty (ty), and the stub is all the
    implementer is shown;
  * the SPEC HASH — sha256 over the text of those types + the signature +
    the description. The generated module records, per box, the hash it
    was written against; if a reviewed type or the description changes,
    that body is STALE until regenerated;
  * the CONSTRUCTORS — the reviewed dataclasses in the closure, the only
    host classes sandbox code may instantiate.

Where the body lives mirrors where the contract lives: module
`relay.cases.queues` ↔ module `generated.relay.cases.queues`.
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import hashlib
import inspect
import pathlib
import re
import sys
import typing
from typing import Any, Callable

STDLIB_OK = {"__future__", "dataclasses", "datetime", "typing", "collections.abc"}


@dataclasses.dataclass(frozen=True)
class Symbol:
    name: str
    module: str
    order: tuple[int, int]
    source: str
    deps: frozenset[str]


def _names_in(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


@functools.lru_cache(maxsize=None)
def _module_symbols(modname: str) -> tuple[dict[str, Symbol], list[str], list[str]]:
    """Top-level type symbols of one reviewed module, its stdlib import
    lines, and the app-internal modules it imports from."""
    mod = sys.modules[modname]
    path = pathlib.Path(mod.__file__)
    src = path.read_text()
    lines = src.splitlines()
    tree = ast.parse(src)
    pkg_root = modname.split(".")[0]
    syms: dict[str, Symbol] = {}
    imports: list[str] = []
    internal: list[str] = []
    rank = _module_rank(modname)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            target = node.module or ""
            if node.level:
                base = modname.rsplit(".", node.level)[0]
                target = f"{base}.{target}" if target else base
            if target.split(".")[0] == pkg_root:
                internal.append(target)
            elif target in STDLIB_OK:
                imports.append(ast.unparse(node))
            continue
        if isinstance(node, ast.Import):
            continue
        name = None
        if isinstance(node, ast.ClassDef):
            name = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and "TypeAlias" in ast.unparse(node.annotation):
            name = node.target.id
        if name is None or name.isupper() and not isinstance(node, ast.ClassDef):
            continue  # functions and CONSTANTS are not types
        first = min([node.lineno] + [d.lineno for d in
                                     getattr(node, "decorator_list", [])])
        text = "\n".join(lines[first - 1:node.end_lineno])
        syms[name] = Symbol(name, modname, (rank, first), text,
                            frozenset(_names_in(node)) - {name})
    return syms, imports, internal


def _module_rank(modname: str) -> int:
    # tie-break only: the stub is ordered by dependencies first
    return {"model": 0}.get(modname.rsplit(".", 1)[-1], 1)


def _ordered(syms: list[Symbol]) -> list[Symbol]:
    """Dependencies before dependents (a type alias must follow the classes
    it names), otherwise reviewed-source order."""
    by_name = {s.name: s for s in syms}
    out: list[Symbol] = []
    seen: set[str] = set()

    def visit(s: Symbol) -> None:
        if s.name in seen:
            return
        seen.add(s.name)
        for d in sorted(s.deps & by_name.keys(), key=lambda n: by_name[n].order):
            visit(by_name[d])
        out.append(s)

    for s in sorted(syms, key=lambda s: s.order):
        visit(s)
    return out


def _all_symbols(modname: str) -> tuple[dict[str, Symbol], list[str]]:
    seen, todo = set(), [modname]
    syms: dict[str, Symbol] = {}
    imports: list[str] = []
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        s, imp, internal = _module_symbols(m)
        for k, v in s.items():
            syms.setdefault(k, v)
        imports += [i for i in imp if i not in imports]
        todo += internal
    return syms, imports


class Box:
    """A reviewed contract with a generated body that runs in Monty.

    The body of a box declared in module `relay.cases.queues` lives in module
    `generated.relay.cases.queues` — file `src/generated/relay/cases/queues.py`
    next to `src/relay/` — together with the bodies of every other box that
    module declares (and any private helpers they share)."""

    def __init__(self, fn: Callable[..., Any]):
        functools.update_wrapper(self, fn)
        self.fn = fn
        self.name = fn.__name__
        self.module = fn.__module__
        self.description = inspect.cleandoc(fn.__doc__ or "")
        src_file = pathlib.Path(sys.modules[self.module].__file__)
        parts = self.module.split(".")
        self.src_root = src_file.parents[len(parts) - 1]
        self.generated_module = f"generated.{self.module}"
        self.impl_path = self.src_root.joinpath("generated", *parts[:-1], f"{parts[-1]}.py")

    # -- the reviewed declaration ------------------------------------------
    @functools.cached_property
    def _node(self) -> ast.FunctionDef:
        tree = ast.parse(pathlib.Path(sys.modules[self.module].__file__).read_text())
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == self.name:
                return node
        raise LookupError(self.name)

    @functools.cached_property
    def hints(self) -> dict[str, Any]:
        return typing.get_type_hints(self.fn)

    @functools.cached_property
    def signature(self) -> inspect.Signature:
        return inspect.signature(self.fn)

    @property
    def signature_text(self) -> str:
        n = self._node
        return f"def {self.name}({ast.unparse(n.args)}) -> {ast.unparse(n.returns)}"

    @property
    def contract_text(self) -> str:
        n = self._node
        return (f"class BoxkitContract_{self.name}(Protocol):\n"
                f"    def __call__(self, {ast.unparse(n.args)}) -> "
                f"{ast.unparse(n.returns)}: ...")

    @functools.cached_property
    def closure(self) -> list[Symbol]:
        syms, _ = _all_symbols(self.module)
        want: set[str] = set()
        todo = list(_names_in(self._node.args) | _names_in(self._node.returns))
        while todo:
            n = todo.pop()
            if n in want or n not in syms:
                continue
            want.add(n)
            todo += syms[n].deps
        return _ordered([syms[n] for n in want])

    @property
    def stub(self) -> str:
        return stub_for([self])

    @functools.cached_property
    def spec_hash(self) -> str:
        """Over the TEXT of the reviewed types the box can see, its signature
        and its description — not over where they live: moving a contract to
        another module keeps its bodies fresh; changing it makes them STALE."""
        parts = sorted(s.source for s in self.closure)
        parts += [self.signature_text, self.description]
        return hashlib.sha256("\n---\n".join(parts).encode()).hexdigest()[:16]

    @functools.cached_property
    def constructors(self) -> dict[str, type]:
        """Reviewed dataclasses in the closure: what sandbox code may build."""
        out = {}
        for s in self.closure:
            obj = getattr(sys.modules[s.module], s.name, None)
            if isinstance(obj, type) and dataclasses.is_dataclass(obj):
                out[s.name] = obj
        return out

    @property
    def header(self) -> str:
        return f"# boxkit: generated implementation of `{self.name}` against spec {self.spec_hash}"

    # -- the generated body --------------------------------------------------
    def impl_source(self) -> str:
        return self.impl_path.read_text()

    def impl_spec(self) -> str | None:
        """The spec hash this box's body was written against: None when the
        generated module or the body is missing, "" when it carries no header."""
        if not self.impl_path.exists():
            return None
        src = self.impl_path.read_text()
        if not re.search(rf"^def {self.name}\(", src, re.M):
            return None
        m = re.search(rf"^# boxkit: generated implementation of `{self.name}` "
                      rf"against spec (\w+)\s*$", src, re.M)
        return m.group(1) if m else ""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        from .sandbox import run_box
        return run_box(self, args, kwargs)

    def __repr__(self) -> str:
        return f"<box {self.name} spec={self.spec_hash}>"


def stub_for(boxes: list[Box]) -> str:
    """The stub for one generated module: every reviewed type its boxes can
    see, plus one contract protocol per box."""
    imports: list[str] = []
    syms: dict[str, Symbol] = {}
    for b in boxes:
        imports += [i for i in _all_symbols(b.module)[1] if i not in imports]
        for s in b.closure:
            syms.setdefault(s.name, s)
    head = sorted(imports, key=lambda i: (not i.startswith("from __future__"), i))
    head.append("from typing import Protocol")
    body = "\n\n".join(s.source for s in _ordered(list(syms.values())))
    contracts = "\n\n\n".join(b.contract_text for b in boxes)
    return "\n".join(head) + "\n\n\n" + body + "\n\n\n" + contracts + "\n"


def blackbox(fn: Callable[..., Any]) -> Box:
    """Declare a black box: a reviewed, typed, body-less signature whose
    docstring is the reviewed description. The body is generated, lives in
    the mirror module `generated.<module>`, and only ever runs inside the
    Monty sandbox."""
    return Box(fn)


def boxes_of(module: Any) -> list[Box]:
    return [v for v in vars(module).values()
            if isinstance(v, Box) and v.module == module.__name__]
