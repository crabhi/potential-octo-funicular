"""Rule-deletion mutation run: delete each guard rule (src/relay/policy.py,
src/relay/*/rules.py) in turn, in a scratch copy, and require the reviewed
policy grid to notice. A surviving mutant is a rule the reviewed tests
would let an agent delete — a one-directional gate. Exit 1 if any survives.

    uv run python mutants.py
"""

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
RULE_FILES = [ROOT / "src/relay/policy.py", *sorted((ROOT / "src/relay").glob("*/rules.py"))]
RULE = r'@POLICY\.(?:deny|allow)\("%s",.*?\n(?=\n|\Z)'


def main() -> int:
    targets = [(f, rid) for f in RULE_FILES
               for rid in re.findall(r'@POLICY\.(?:deny|allow)\("(\w+)"', f.read_text())]
    alive = []
    for path, rid in targets:
        d = pathlib.Path(tempfile.mkdtemp())
        for part in ("src", "test", "pyproject.toml"):
            src = ROOT / part
            (shutil.copytree if src.is_dir() else shutil.copy)(src, d / part)
        target = d / path.relative_to(ROOT)
        text = target.read_text()
        mutant = re.sub(RULE % rid, "", text, count=1, flags=re.S)
        assert mutant != text, rid
        target.write_text(mutant)
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                            "test/relay/test_policy.py"],
                           cwd=d, capture_output=True, text=True,
                           env={"PYTHONPATH": str(d / "src"), "PATH": "/usr/bin:/bin"})
        shutil.rmtree(d)
        failed = next((ln.split("::")[-1].split(" ")[0] for ln in r.stdout.splitlines()
                       if ln.startswith("FAILED")), r.stdout.strip().splitlines()[-1:])
        print(f"  {'killed' if r.returncode else 'ALIVE '}  {rid:<26} {failed}")
        if not r.returncode:
            alive.append(rid)
    print(f"{len(targets)} rule-deletion mutants, {len(targets) - len(alive)} killed"
          + (f"; SURVIVORS: {alive}" if alive else ""))
    return 1 if alive else 0


if __name__ == "__main__":
    sys.exit(main())
