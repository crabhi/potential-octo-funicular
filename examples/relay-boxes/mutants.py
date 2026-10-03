"""Rule-deletion mutation run: delete each guard rule of relay/machine.py in
turn (in a scratch copy) and require the reviewed policy grid to notice.
A surviving mutant is a rule the reviewed tests would let an agent delete —
a one-directional gate (guardrail 2). Exit 1 if any mutant survives.

    python mutants.py
"""

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
SRC = (ROOT / "relay" / "machine.py").read_text()


def main() -> int:
    ids = re.findall(r'@POLICY\.(?:deny|allow)\("(\w+)"', SRC)
    alive = []
    for rid in ids:
        d = pathlib.Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "boxkit", d / "boxkit")
        shutil.copytree(ROOT / "relay", d / "relay")
        mutant = re.sub(r'@POLICY\.(deny|allow)\("%s",.*?\n\n' % rid, "", SRC,
                        count=1, flags=re.S)
        assert mutant != SRC, rid
        (d / "relay" / "machine.py").write_text(mutant)
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x",
                            "relay/tests/test_policy.py"],
                           cwd=d, capture_output=True, text=True)
        shutil.rmtree(d)
        failed = next((ln.split("::")[-1].split(" ")[0] for ln in r.stdout.splitlines()
                       if ln.startswith("FAILED")), "")
        print(f"  {'killed' if r.returncode else 'ALIVE '}  {rid:<26} {failed}")
        if not r.returncode:
            alive.append(rid)
    print(f"{len(ids)} rule-deletion mutants, {len(ids) - len(alive)} killed"
          + (f"; SURVIVORS: {alive}" if alive else ""))
    return 1 if alive else 0


if __name__ == "__main__":
    sys.exit(main())
