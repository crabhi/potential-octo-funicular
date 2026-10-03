"""boxkit CLI.

    python -m boxkit brief <app> <box>   what the implementer (an LLM) sees
    python -m boxkit check <app>         the gate (exit 1 on any failure)

<app> is the path of an app package laid out by the convention:

    <app>/            REVIEWED — model.py machine.py boxes.py shell.py tests/
    <app>/generated/  GENERATED — <box>.py (runs only inside Monty), tests/

Review happens in the pull request: everything outside generated/ is read
by a human; generated/ is marked `linguist-generated` (.gitattributes), so
the PR collapses it and the reviewed files are what is left on screen.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import pathlib
import sys

from .contract import Box, boxes_of
from .machine import Lifecycle, Policy

GENERATED = "generated"
IMPL_IMPORTS = {"__future__", "typing", "datetime", "dataclasses", "re", "json",
                "math", "collections", "itertools", "functools"}


# -- the app ---------------------------------------------------------------------

class App:
    def __init__(self, path: str):
        self.dir = pathlib.Path(path).resolve()
        self.name = self.dir.name
        sys.path.insert(0, str(self.dir.parent))
        self.boxes_mod = importlib.import_module(f"{self.name}.boxes")
        self.machine_mod = importlib.import_module(f"{self.name}.machine")
        self.generated = self.dir / GENERATED

    @property
    def boxes(self) -> list[Box]:
        return boxes_of(self.boxes_mod)

    def lifecycles(self) -> list[Lifecycle]:
        return [v for v in vars(self.machine_mod).values() if isinstance(v, Lifecycle)]

    def policies(self) -> list[Policy]:
        return [v for v in vars(self.machine_mod).values() if isinstance(v, Policy)]

    def reviewed_sources(self) -> list[pathlib.Path]:
        return sorted(p for p in self.dir.rglob("*.py")
                      if "__pycache__" not in p.parts
                      and self.generated not in p.parents)


# -- lints ---------------------------------------------------------------------------

def lint_contracts(app: App) -> list[str]:
    """boxes.py holds types and contracts only: every function is a
    body-less @blackbox (docstring + `...`)."""
    out = []
    tree = ast.parse(pathlib.Path(app.boxes_mod.__file__).read_text())
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decos = [ast.unparse(d) for d in node.decorator_list]
            if "blackbox" not in decos:
                out.append(f"boxes.py: {node.name} is logic in a contract file "
                           f"(only @blackbox signatures belong here)")
                continue
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                body = body[1:]
            else:
                out.append(f"boxes.py: box {node.name} has no description (docstring)")
            if not (len(body) == 1 and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant) and body[0].value.value is ...):
                out.append(f"boxes.py: box {node.name} has a body — contracts are `...`")
    return out


def lint_boundary(app: App) -> list[str]:
    """Generated code is reachable only through the sandbox: no reviewed
    module imports generated/, and the box bodies in generated/ are
    self-contained Monty modules."""
    out = []
    names = {b.name for b in app.boxes}
    for path in app.reviewed_sources():
        rel = path.relative_to(app.dir).as_posix()
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""] + [a.name for a in node.names]
            if any(m == GENERATED or f".{GENERATED}" in m or m.startswith(f"{GENERATED}.")
                   for m in mods):
                out.append(f"{rel}:{node.lineno}: imports generated code directly "
                           f"(boxes run only in the sandbox)")
    for p in sorted(app.generated.glob("*.py")):
        rel = p.relative_to(app.dir).as_posix()
        if p.name == "__init__.py":
            continue
        if p.stem not in names:
            out.append(f"{rel}: implements no declared box (orphan)")
            continue
        tree = ast.parse(p.read_text())
        defined = set()
        for node in tree.body:
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
                           f"({type(node).__name__}) — box modules only define")
                continue
            if bad:
                out.append(f"{rel}:{node.lineno}: imports {bad} — not in the sandbox "
                           f"allowlist {sorted(IMPL_IMPORTS)}")
        if p.stem not in defined:
            out.append(f"{rel}: does not define `{p.stem}`")
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

    stage("1. contracts carry no logic", lint_contracts(app),
          f"{len(app.boxes)} body-less @blackbox declarations with descriptions")
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
          lint_boundary(app), f"no reviewed module imports {GENERATED}/; "
                              f"box bodies are self-contained")

    problems = []
    for b in app.boxes:
        spec = b.impl_spec()
        if spec is None:
            problems.append(f"{b.name}: MISSING {GENERATED}/{b.name}.py")
            continue
        if spec != b.spec_hash:
            problems.append(f"{b.name}: STALE — written against spec {spec or '?'}, "
                            f"contract is now {b.spec_hash} (regenerate)")
        diag = typecheck(b)
        if diag:
            problems.append(f"{b.name}: TYPE ERROR against its reviewed stub\n      "
                            + diag.replace("\n", "\n      "))
    stage("4. every box has a fresh, well-typed implementation (ty inside Monty)",
          problems, f"{len(app.boxes)} implementations type-check against their stubs")

    print(f"\n{'GATE FAIL' if failures else 'GATE PASS'} "
          f"({failures} problem{'s' if failures != 1 else ''})")
    return 1 if failures else 0


# -- brief: what the implementer sees ------------------------------------------------------

def brief(app: App, name: str) -> str:
    box = next((b for b in app.boxes if b.name == name), None)
    if box is None:
        raise SystemExit(f"no box {name!r}; boxes: {[b.name for b in app.boxes]}")
    return f"""# Implement black box `{box.name}`

Write `{app.name}/{GENERATED}/{box.name}.py`. Its FIRST line must be exactly:

{box.header}

Rules of the sandbox (Monty — a subset of Python):
- Define `def {box.name}(...)` with exactly the contract's parameters.
  Helper functions are fine; prefix them with `_`.
- The reviewed types below are injected as globals at run time: use them
  by name, do NOT import or redefine them. Construct results with them.
- Imports only from: {", ".join(sorted(IMPL_IMPORTS))}. No `html`, `enum`,
  `string`, `textwrap`, `dataclasses.replace`. No I/O of any kind.
- The world is reachable only through the parameters (capabilities).
- The result is checked against the declared return type on every call.

## Contract (reviewed — you cannot change it)

```python
{box.stub.rstrip()}
```

## Description (reviewed)

{box.description}
"""


def main() -> int:
    ap = argparse.ArgumentParser(prog="boxkit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("app")
    b = sub.add_parser("brief")
    b.add_argument("app")
    b.add_argument("box")
    args = ap.parse_args()
    app = App(args.app)
    if args.cmd == "check":
        return check(app)
    print(brief(app, args.box))
    return 0


if __name__ == "__main__":
    sys.exit(main())
