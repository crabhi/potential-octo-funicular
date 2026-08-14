"""The boundary lint: guardrail 10, held mechanically.

    python -m analysis.boundary <app-dir> [<app-dir> ...]

Application code — the hand-written UI, adapters, seed scripts — may
import exactly ONE thing from the engine: `engine.kernel`. Everything
else that could reach state around the kernel's decisions is refused:

  * `engine.store`, `engine.server`, `engine.ui`, `engine.features`,
    `engine.rulebase`, bare `import engine` — the layers beneath the
    boundary;
  * `sqlite3` — the store's substrate (an app talking to the database
    directly is the whole failure mode this lint exists for);
  * attribute access to the kernel module's internal aliases
    (`store`, `features_mod`, `rb_mod`) or to mangled kernel internals
    (`_Kernel*`) — the reach-around paths that mere import rules miss.

Honest scope: Python has no package-private, so this is a lint, not a
proof — the by-construction version of this boundary is a process
boundary (the HTTP API) or a language with visibility (guardrail 8).
What the lint guarantees is that bypassing the kernel cannot happen
QUIETLY: it is a named CI failure, not a code-review maybe. Run it from
the app's check.sh; it exits 1 with file:line findings.
"""

import argparse
import ast
import pathlib
import sys

FORBIDDEN_MODULES = {"sqlite3"}
FORBIDDEN_ATTRS = {"store", "features_mod", "rb_mod"}
ALLOWED_ENGINE = "engine.kernel"


def _findings_for_module(mod, node, path):
    if mod == ALLOWED_ENGINE:
        return []
    root = mod.split(".")[0]
    if root == "engine":
        return [(path, node.lineno,
                 f"imports {mod!r}: app code may import {ALLOWED_ENGINE} only")]
    if root in FORBIDDEN_MODULES:
        return [(path, node.lineno,
                 f"imports {mod!r}: the store's substrate is beneath the boundary")]
    return []


def scan_file(path):
    findings = []
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                findings += _findings_for_module(alias.name, node, path)
        elif isinstance(node, ast.ImportFrom):
            if node.level:      # relative imports stay inside the app
                continue
            mod = node.module or ""
            if mod == "engine":
                for alias in node.names:
                    if alias.name == "kernel":
                        continue
                    findings += _findings_for_module(f"engine.{alias.name}",
                                                     node, path)
            else:
                findings += _findings_for_module(mod, node, path)
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRS or node.attr.startswith("_Kernel"):
                findings.append((path, node.lineno,
                                 f"reaches around the kernel via .{node.attr}"))
        elif isinstance(node, ast.Name):
            if node.id.startswith("_Kernel"):
                findings.append((path, node.lineno,
                                 f"touches mangled kernel internals {node.id!r}"))
    return findings


def scan(dirs):
    findings, n_files = [], 0
    for d in dirs:
        root = pathlib.Path(d)
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for f in files:
            n_files += 1
            findings += scan_file(f)
    return findings, n_files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+", help="app directories (or files) to hold "
                    "to the kernel boundary")
    args = ap.parse_args()
    findings, n_files = scan(args.dirs)
    for path, line, msg in findings:
        print(f"   FAIL {path}:{line}: {msg}")
    if findings:
        print(f"BOUNDARY: FAIL ({len(findings)} finding(s) in {n_files} files)")
        sys.exit(1)
    print(f"BOUNDARY: ok ({n_files} files import nothing beneath engine.kernel)")


if __name__ == "__main__":
    main()
