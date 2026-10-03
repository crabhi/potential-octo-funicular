"""boxkit CLI.

    python -m boxkit brief   <app> <box>   what the implementer (an LLM) sees
    python -m boxkit check   <app>         the gate (exit 1 on any failure)
    python -m boxkit status  <app>         what changed since the last review
    python -m boxkit digest  <app>         write <app>/REVIEW.md, the review surface
    python -m boxkit approve <app> --by N  a HUMAN re-stamps <app>/REVIEW.lock

<app> is the path of an app package laid out by the convention:

    <app>/model.py machine.py boxes.py shell.py tests/reviewed/  REVIEWED
    <app>/impl/<box>.py  tests/generated/                        GENERATED
"""

from __future__ import annotations

import argparse
import ast
import datetime
import hashlib
import importlib
import inspect
import json
import pathlib
import sys

from .contract import Box, boxes_of
from .machine import Lifecycle, Policy

FRAMEWORK = pathlib.Path(__file__).resolve().parent
GENERATED_DIRS = ("impl", "tests/generated")
DERIVED = ("REVIEW.lock", "REVIEW.md")
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
        self.lock_path = self.dir / "REVIEW.lock"

    @property
    def boxes(self) -> list[Box]:
        return boxes_of(self.boxes_mod)

    def lifecycles(self) -> list[Lifecycle]:
        return [v for v in vars(self.machine_mod).values() if isinstance(v, Lifecycle)]

    def policies(self) -> list[Policy]:
        return [v for v in vars(self.machine_mod).values() if isinstance(v, Policy)]

    def is_generated(self, p: pathlib.Path) -> bool:
        rel = p.relative_to(self.dir).as_posix()
        return any(rel.startswith(d + "/") for d in GENERATED_DIRS)

    def reviewed_files(self) -> dict[str, str]:
        out = {}
        for p in sorted(self.dir.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts or p.name in DERIVED:
                continue
            if self.is_generated(p):
                continue
            out[p.relative_to(self.dir).as_posix()] = _sha(p)
        for p in sorted(FRAMEWORK.glob("*.py")):
            out[f"[boxkit]/{p.name}"] = _sha(p)
        return out

    def generated_files(self) -> list[pathlib.Path]:
        return sorted(p for d in GENERATED_DIRS for p in (self.dir / d).rglob("*.py")
                      if "__pycache__" not in p.parts)

    def lock(self) -> dict:
        return json.loads(self.lock_path.read_text()) if self.lock_path.exists() else {}


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


# -- status: reviewed changes since the lock ---------------------------------------

def review_drift(app: App) -> list[str]:
    locked = app.lock().get("files", {})
    now = app.reviewed_files()
    out = []
    for f in sorted(set(locked) | set(now)):
        if f not in now:
            out.append(f"removed   {f}")
        elif f not in locked:
            out.append(f"new       {f}")
        elif locked[f] != now[f]:
            out.append(f"changed   {f}")
    locked_boxes = app.lock().get("boxes", {})
    for b in app.boxes:
        if locked_boxes.get(b.name) != b.spec_hash:
            out.append(f"contract  {b.name} (spec {locked_boxes.get(b.name)} -> {b.spec_hash})")
    return out


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
    module imports impl/, and impl/ files are self-contained Monty modules."""
    out = []
    names = {b.name for b in app.boxes}
    for rel in app.reviewed_files():
        if rel.startswith("[boxkit]") or not rel.endswith(".py"):
            continue
        tree = ast.parse((app.dir / rel).read_text())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""] + [a.name for a in node.names]
            if any(m == "impl" or ".impl" in m or m.startswith("impl.") for m in mods):
                out.append(f"{rel}:{node.lineno}: imports generated code directly "
                           f"(boxes run only in the sandbox)")
    for p in sorted((app.dir / "impl").glob("*.py")):
        rel = p.relative_to(app.dir).as_posix()
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
                           f"({type(node).__name__}) — impl modules only define")
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

    drift = review_drift(app)
    stage("1. review lock: reviewed code is what a human approved", drift,
          f"{len(app.reviewed_files())} reviewed files, {len(app.boxes)} contracts "
          f"match REVIEW.lock (approved by {app.lock().get('approved_by', '?')})")
    stage("2. contracts carry no logic", lint_contracts(app),
          f"{len(app.boxes)} body-less @blackbox declarations with descriptions")
    lc = [p for l in app.lifecycles() for p in l.problems()]
    entities = {l.entity for l in app.lifecycles()}
    for pol in app.policies():
        for r in pol.rules:
            lc += [f"rule {r.id} governs undeclared entity {e!r}"
                   for e in r.entities if e not in entities]
    stage("3. lifecycles and rules are well-formed", lc,
          ", ".join(f"{l.entity}: {len(l.states)} states/{len(l.transitions)} transitions"
                    for l in app.lifecycles())
          + f"; {sum(len(p.rules) for p in app.policies())} rules")
    stage("4. boundary: generated code is reachable only through the sandbox",
          lint_boundary(app), "no reviewed module imports impl/; impl/ is self-contained")

    problems = []
    for b in app.boxes:
        spec = b.impl_spec()
        if spec is None:
            problems.append(f"{b.name}: MISSING impl/{b.name}.py")
            continue
        if spec != b.spec_hash:
            problems.append(f"{b.name}: STALE — written against spec {spec or '?'}, "
                            f"contract is now {b.spec_hash} (regenerate)")
        diag = typecheck(b)
        if diag:
            problems.append(f"{b.name}: TYPE ERROR against its reviewed stub\n      "
                            + diag.replace("\n", "\n      "))
    stage("5. every box has a fresh, well-typed implementation (ty inside Monty)",
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

Write `{app.name}/impl/{box.name}.py`. Its FIRST line must be exactly:

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


# -- digest: the review surface ---------------------------------------------------------------

def digest(app: App) -> str:
    out = [f"# {app.name} — review surface\n",
           "Generated by `python -m boxkit digest`. Everything below is REVIEWED "
           "code, summarised; generated code (impl/, tests/generated/) is not "
           "listed because no human reviews it — the gate does.\n"]
    model = importlib.import_module(f"{app.name}.model")
    import dataclasses as dc
    import typing
    out.append("## 1. Data model (`model.py`)\n")
    for name, obj in vars(model).items():
        if isinstance(obj, type) and dc.is_dataclass(obj) and obj.__module__ == model.__name__:
            fields = ", ".join(f"`{f.name}: {f.type}`" for f in dc.fields(obj))
            out.append(f"- **{name}** — {fields}")
    for name, obj in vars(model).items():
        if typing.get_origin(obj) is typing.Literal:
            out.append(f"- **{name}** ∈ {{{', '.join(map(str, typing.get_args(obj)))}}}")
    out.append("\n## 2. State transitions (`machine.py`)\n")
    for lc in app.lifecycles():
        out.append(f"### {lc.entity}\n\n```mermaid\n{lc.mermaid()}\n```\n")
        out.append("| action | from | to |\n|---|---|---|")
        out += [f"| {t.action} | {t.source} | {t.target} |" for t in lc.transitions]
        out.append("")
    out.append("## 3. Guard rules (`machine.py`) — deny wins, silence denies\n")
    out.append("| rule | effect | entities | description | when |\n|---|---|---|---|---|")
    for pol in app.policies():
        for r in pol.rules:
            src = inspect.getsource(r.when).strip().splitlines()[-1].strip()
            src = src.removeprefix("return ").replace("|", "\\|")
            out.append(f"| `{r.id}` | {r.effect} | {', '.join(r.entities)} | "
                       f"{r.description} | `{src}` |")
    out.append("\n## 4. Black boxes (`boxes.py`)\n")
    for b in app.boxes:
        status = "fresh" if b.impl_spec() == b.spec_hash else (
            "MISSING" if b.impl_spec() is None else "STALE")
        out.append(f"### `{b.name}` — spec `{b.spec_hash}` ({status})\n")
        out.append(f"```python\n{b.signature_text}\n```\n")
        out.append(b.description + "\n")
    out.append("## 5. Reviewed tests\n")
    for p in sorted((app.dir / "tests" / "reviewed").glob("test_*.py")):
        tree = ast.parse(p.read_text())
        tests = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name.startswith("test_")]
        out.append(f"- `{p.name}`: " + ", ".join(f"`{t}`" for t in tests))
    return "\n".join(out) + "\n"


# -- approve: a human re-stamps the lock --------------------------------------------------------

def approve(app: App, by: str) -> None:
    drift = review_drift(app)
    if not drift and app.lock_path.exists():
        print("nothing to approve: reviewed code matches REVIEW.lock")
        return
    for d in drift:
        print(f"  approving {d}")
    app.lock_path.write_text(json.dumps({
        "approved_by": by,
        "approved_at": datetime.date.today().isoformat(),
        "files": app.reviewed_files(),
        "boxes": {b.name: b.spec_hash for b in app.boxes},
    }, indent=2) + "\n")
    (app.dir / "REVIEW.md").write_text(digest(app))
    print(f"REVIEW.lock re-stamped by {by}; REVIEW.md regenerated")


def main() -> int:
    ap = argparse.ArgumentParser(prog="boxkit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("check", "status", "digest"):
        sub.add_parser(c).add_argument("app")
    b = sub.add_parser("brief")
    b.add_argument("app")
    b.add_argument("box")
    a = sub.add_parser("approve")
    a.add_argument("app")
    a.add_argument("--by", required=True, help="the human reviewer")
    args = ap.parse_args()
    app = App(args.app)
    if args.cmd == "check":
        return check(app)
    if args.cmd == "status":
        drift = review_drift(app)
        print("\n".join(drift) or "reviewed code matches REVIEW.lock")
        for bx in app.boxes:
            s = bx.impl_spec()
            if s != bx.spec_hash:
                print(f"impl      {bx.name}: {'MISSING' if s is None else 'STALE'}")
        return 0
    if args.cmd == "digest":
        (app.dir / "REVIEW.md").write_text(digest(app))
        print(f"wrote {app.dir / 'REVIEW.md'}")
        return 0
    if args.cmd == "brief":
        print(brief(app, args.box))
        return 0
    approve(app, args.by)
    return 0


if __name__ == "__main__":
    sys.exit(main())
