"""boxkit CLI.

    python -m boxkit check <package>            the gate (exit 1 on any failure)
    python -m boxkit brief <package> <module>   what the implementer (an LLM) sees

<package> is the path of a reviewed package in a src layout; generated code
mirrors it module for module:

    src/relay/cases/queues.py              REVIEWED   relay.cases.queues
    src/generated/relay/cases/queues.py    GENERATED  generated.relay.cases.queues
    test/relay/cases/test_queues.py        REVIEWED tests
    test/generated/relay/cases/...         GENERATED tests

Review happens in the pull request: src/generated/ and test/generated/ are
marked `linguist-generated` (.gitattributes), so the PR collapses them and
what is left on screen is exactly the code a human reads.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import pathlib
import pkgutil
import sys
from types import ModuleType

from .contract import Box, boxes_of, stub_for
from .machine import Lifecycle, Policy

GENERATED = "generated"
IMPL_IMPORTS = {"__future__", "typing", "datetime", "dataclasses", "re", "json",
                "math", "collections", "itertools", "functools"}


# -- the app ---------------------------------------------------------------------

class App:
    def __init__(self, path: str):
        self.dir = pathlib.Path(path).resolve()          # src/relay
        self.name = self.dir.name                        # relay
        self.src = self.dir.parent                       # src
        self.generated = self.src / GENERATED / self.name
        if str(self.src) not in sys.path:
            sys.path.insert(0, str(self.src))
        pkg = importlib.import_module(self.name)
        self.modules: list[ModuleType] = [pkg] + [
            importlib.import_module(m.name)
            for m in pkgutil.walk_packages(pkg.__path__, prefix=f"{self.name}.")]

    @property
    def boxes(self) -> list[Box]:
        return [b for m in self.modules for b in boxes_of(m)]

    def boxes_by_module(self) -> dict[str, list[Box]]:
        out: dict[str, list[Box]] = {}
        for b in self.boxes:
            out.setdefault(b.module, []).append(b)
        return out

    def _instances(self, cls: type) -> list:
        seen, out = set(), []
        for m in self.modules:
            for v in vars(m).values():
                if isinstance(v, cls) and id(v) not in seen:
                    seen.add(id(v))
                    out.append(v)
        return out

    def lifecycles(self) -> list[Lifecycle]:
        return self._instances(Lifecycle)

    def policies(self) -> list[Policy]:
        return self._instances(Policy)

    def reviewed_sources(self) -> list[pathlib.Path]:
        return sorted(p for p in self.dir.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(app: App, p: pathlib.Path) -> str:
    return p.relative_to(app.src.parent).as_posix()


# -- lints ---------------------------------------------------------------------------

def lint_contracts(app: App) -> list[str]:
    """A module that declares black boxes holds types and contracts only:
    every function in it is a body-less @blackbox (docstring + `...`)."""
    out = []
    for module in app.boxes_by_module():
        path = pathlib.Path(sys.modules[module].__file__)
        rel = _rel(app, path)
        for node in ast.parse(path.read_text()).body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if "blackbox" not in [ast.unparse(d) for d in node.decorator_list]:
                out.append(f"{rel}: {node.name} is logic in a contract module "
                           f"(only @blackbox signatures belong here)")
                continue
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                body = body[1:]
            else:
                out.append(f"{rel}: box {node.name} has no description (docstring)")
            if not (len(body) == 1 and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant) and body[0].value.value is ...):
                out.append(f"{rel}: box {node.name} has a body — contracts are `...`")
    return out


def lint_boundary(app: App) -> list[str]:
    """Generated code is reachable only through the sandbox: no reviewed
    module imports `generated`, and every generated module is the
    self-contained mirror of a reviewed module that declares boxes."""
    out = []
    for path in app.reviewed_sources():
        for node in ast.walk(ast.parse(path.read_text())):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            if any(m == GENERATED or m.startswith(f"{GENERATED}.") for m in mods):
                out.append(f"{_rel(app, path)}:{node.lineno}: imports generated code "
                           f"directly (box bodies run only in the sandbox)")
    by_module = app.boxes_by_module()
    for p in sorted(app.generated.rglob("*.py")):
        if p.name == "__init__.py" or "__pycache__" in p.parts:
            continue
        rel = _rel(app, p)
        mirror = ".".join((app.name, *p.relative_to(app.generated).with_suffix("").parts))
        boxes = by_module.get(mirror)
        if not boxes:
            out.append(f"{rel}: mirrors {mirror}, which declares no boxes (orphan)")
            continue
        defined = set()
        for node in ast.parse(p.read_text()).body:
            if isinstance(node, ast.Import):
                bad = [a.name for a in node.names if a.name.split(".")[0] not in IMPL_IMPORTS]
            elif isinstance(node, ast.ImportFrom):
                bad = [] if (node.module or "").split(".")[0] in IMPL_IMPORTS else [node.module]
            elif isinstance(node, ast.FunctionDef):
                defined.add(node.name)
                continue
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.ClassDef)):
                continue
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue  # a docstring
            else:
                out.append(f"{rel}:{node.lineno}: top-level statement "
                           f"({type(node).__name__}) — generated modules only define")
                continue
            if bad:
                out.append(f"{rel}:{node.lineno}: imports {bad} — not in the sandbox "
                           f"allowlist {sorted(IMPL_IMPORTS)}")
        extra = {n for n in defined if not n.startswith("_")} - {b.name for b in boxes}
        if extra:
            out.append(f"{rel}: public functions {sorted(extra)} are not boxes of {mirror} "
                       f"(helpers start with `_`)")
    return out


# -- check: the gate -------------------------------------------------------------------

def check(app: App) -> int:
    from .sandbox import typecheck
    failures = 0

    def stage(title: str, problems: list[str], ok: str) -> None:
        nonlocal failures
        print(f"\n== {title}")
        if problems:
            failures += len(problems)
            for p in problems:
                print(f"  FAIL {p}")
        else:
            print(f"  ok   {ok}")

    by_module = app.boxes_by_module()
    stage("1. contracts carry no logic", lint_contracts(app),
          f"{len(app.boxes)} body-less @blackbox declarations in {len(by_module)} modules")
    lc = [p for l in app.lifecycles() for p in l.problems()]
    entities = {l.entity for l in app.lifecycles()}
    for pol in app.policies():
        for r in pol.rules:
            lc += [f"rule {r.id} governs undeclared entity {e!r}"
                   for e in r.entities if e not in entities]
    stage("2. lifecycles and rules are well-formed", lc,
          ", ".join(f"{l.entity}: {len(l.states)} states/{len(l.transitions)} transitions"
                    for l in app.lifecycles())
          + f"; {sum(len(p.rules) for p in app.policies())} rules")
    stage("3. boundary: generated code is reachable only through the sandbox",
          lint_boundary(app), f"no reviewed module imports {GENERATED}; every "
                              f"{GENERATED} module mirrors a contract module")

    problems = []
    for module, boxes in by_module.items():
        present = []
        for b in boxes:
            spec = b.impl_spec()
            if spec is None:
                problems.append(f"{b.name}: MISSING — no `def {b.name}` in {b.generated_module}")
                continue
            present.append(b)
            if spec != b.spec_hash:
                problems.append(f"{b.name}: STALE — written against spec {spec or '?'}, "
                                f"contract is now {b.spec_hash} (regenerate)")
        if present and len(present) == len(boxes):
            diag = typecheck(boxes)
            if diag:
                problems.append(f"{boxes[0].generated_module}: TYPE ERROR against the "
                                f"reviewed stub\n      " + diag.replace("\n", "\n      "))
    stage("4. every box has a fresh, well-typed body (ty inside Monty)", problems,
          f"{len(by_module)} generated modules ({len(app.boxes)} boxes) type-check "
          f"against their stubs")

    print(f"\n{'GATE FAIL' if failures else 'GATE PASS'} "
          f"({failures} problem{'s' if failures != 1 else ''})")
    return 1 if failures else 0


# -- brief: what the implementer sees ------------------------------------------------------

def brief(app: App, target: str) -> str:
    """The brief for one generated module: all boxes its mirror declares.
    `target` is a module (relay.cases.pages) or one of its boxes (case_page)."""
    by_module = app.boxes_by_module()
    module = target if target in by_module else next(
        (b.module for b in app.boxes if b.name == target), None)
    if module is None:
        raise SystemExit(f"no contract module or box {target!r}; modules: {sorted(by_module)}")
    boxes = by_module[module]
    first = boxes[0]
    headers = "\n".join(b.header for b in boxes)
    descriptions = "\n\n".join(f"### `{b.name}`\n\n{b.description}" for b in boxes)
    return f"""# Implement `{first.generated_module}`

Write `{_rel(app, first.impl_path)}` — the generated mirror of the reviewed
module `{module}`, holding the bodies of its {len(boxes)} black box(es).
Start the file with exactly these lines:

{headers}

Rules of the sandbox (Monty — a subset of Python):
- Define {", ".join(f"`def {b.name}(...)`" for b in boxes)} with exactly the
  contracts' parameters. Shared helpers are fine; prefix them with `_`.
- The reviewed types below are injected as globals at run time: use them
  by name, do NOT import or redefine them. Construct results with them.
- Imports only from: {", ".join(sorted(IMPL_IMPORTS))}. No `html`, `enum`,
  `string`, `textwrap`, `dataclasses.replace`. No I/O of any kind.
- The world is reachable only through the parameters (capabilities).
- Every result is checked against its declared return type on every call.

## Contracts (reviewed — you cannot change them)

```python
{stub_for(boxes).rstrip()}
```

## Descriptions (reviewed)

{descriptions}
"""


def main() -> int:
    ap = argparse.ArgumentParser(prog="boxkit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("package")
    b = sub.add_parser("brief")
    b.add_argument("package")
    b.add_argument("target", help="a contract module (relay.cases.pages) or a box name")
    args = ap.parse_args()
    app = App(args.package)
    if args.cmd == "check":
        return check(app)
    print(brief(app, args.target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
