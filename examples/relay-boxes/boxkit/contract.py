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
    modules) plus a `BoxkitContract` protocol for its signature. The
    generated implementation is type-checked against this stub inside
    Monty (ty), and the stub is all the implementer is shown;
  * the SPEC HASH — sha256 over stub + description. A generated file
    records the hash it was written against; if a reviewed type or the
    description changes, the implementation is STALE until regenerated;
  * the CONSTRUCTORS — the reviewed dataclasses in the closure, the only
    host classes sandbox code may instantiate.
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import hashlib
import inspect
import pathlib
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
    # model before contracts, so the stub reads in dependency order
    return {"model": 0}.get(modname.rsplit(".", 1)[-1], 1)


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
    """A reviewed contract with a generated body that runs in Monty."""

    def __init__(self, fn: Callable[..., Any]):
        functools.update_wrapper(self, fn)
        self.fn = fn
        self.name = fn.__name__
        self.module = fn.__module__
        self.description = inspect.cleandoc(fn.__doc__ or "")
        self.package_dir = pathlib.Path(sys.modules[self.module].__file__).parent
        self.impl_path = self.package_dir / "impl" / f"{self.name}.py"

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
        return sorted((syms[n] for n in want), key=lambda s: s.order)

    @functools.cached_property
    def stub(self) -> str:
        _, imports = _all_symbols(self.module)
        head = sorted(imports, key=lambda i: (not i.startswith("from __future__"), i))
        if not any("Protocol" in i for i in head):
            head.append("from typing import Protocol")
        body = "\n\n".join(s.source for s in self.closure)
        n = self._node
        contract = (f"class BoxkitContract(Protocol):\n"
                    f"    def __call__(self, {ast.unparse(n.args)}) -> "
                    f"{ast.unparse(n.returns)}: ...")
        return "\n".join(head) + "\n\n\n" + body + "\n\n\n" + contract + "\n"

    @functools.cached_property
    def spec_hash(self) -> str:
        h = hashlib.sha256((self.stub + "\n---\n" + self.description).encode())
        return h.hexdigest()[:16]

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
        if not self.impl_path.exists():
            return None
        first = self.impl_path.read_text().splitlines()[:1]
        if first and first[0].startswith("# boxkit:") and " spec " in first[0]:
            return first[0].rsplit(" spec ", 1)[1].strip()
        return ""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        from .sandbox import run_box
        return run_box(self, args, kwargs)

    def __repr__(self) -> str:
        return f"<box {self.name} spec={self.spec_hash}>"


def blackbox(fn: Callable[..., Any]) -> Box:
    """Declare a black box: a reviewed, typed, body-less signature whose
    docstring is the reviewed description. The body is generated, lives in
    `impl/<name>.py`, and only ever runs inside the Monty sandbox."""
    return Box(fn)


def boxes_of(module: Any) -> list[Box]:
    return [v for v in vars(module).values() if isinstance(v, Box)]
