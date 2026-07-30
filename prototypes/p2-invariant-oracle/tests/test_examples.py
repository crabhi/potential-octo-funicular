"""End-to-end tests: run every CLI subcommand against every example file and
assert the verdict taxonomy the README documents.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
CLAIM = 'implies(phase == "contract", not old_running)'


def run(*args):
    proc = subprocess.run(
        [sys.executable, "-m", "oracle", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc


def run_json(*args):
    proc = run(*args, "--json")
    assert proc.returncode in (0, 1), proc.stderr
    return json.loads(proc.stdout)


# -- check ------------------------------------------------------------------


def test_check_consistent():
    out = run_json("check", str(EXAMPLES / "consistent.yaml"))
    assert out["verdict"] == "CONSISTENT"
    assert set(out["witness"]) == {
        "phase", "column_state", "version_skew", "old_running", "new_running", "reads_absent_column",
    }


def test_check_contradictory_names_the_conflict():
    out = run_json("check", str(EXAMPLES / "contradictory.yaml"))
    assert out["verdict"] == "IMPOSSIBLE"
    core_names = {e["name"] for e in out["unsat_core"]}
    assert core_names == {"inv_skew_bound", "inv_skew_at_least_two"}


def test_check_surprising_is_consistent():
    out = run_json("check", str(EXAMPLES / "surprising.yaml"))
    assert out["verdict"] == "CONSISTENT"


# -- witness ------------------------------------------------------------------


def test_witness_consistent_produces_models():
    out = run_json("witness", str(EXAMPLES / "consistent.yaml"), "-n", "5")
    assert out["verdict"] == "CONSISTENT"
    assert 1 <= out["found"] <= 5
    for w in out["witnesses"]:
        assert w["phase"] in ("expand", "backfill", "contract", "done")


def test_witness_contradictory_is_impossible():
    out = run_json("witness", str(EXAMPLES / "contradictory.yaml"), "-n", "3")
    assert out["verdict"] == "IMPOSSIBLE"


def test_witness_surprising_reveals_forgotten_guard():
    # The missing guard (inv_contract_needs_no_old) should let a witness
    # through where the migration has entered `contract` while an
    # old-version instance is still running -- an unexpected state.
    out = run_json("witness", str(EXAMPLES / "surprising.yaml"), "-n", "40")
    assert out["verdict"] == "CONSISTENT"
    surprising_states = [
        w for w in out["witnesses"] if w["phase"] == "contract" and w["old_running"]
    ]
    assert surprising_states, "expected a witness with phase=contract and old_running=True"


# -- vacuity ------------------------------------------------------------------


def test_vacuity_consistent_all_ok():
    out = run_json("vacuity", str(EXAMPLES / "consistent.yaml"))
    verdicts = {r["name"]: r["verdict"] for r in out["results"]}
    assert set(verdicts) == {
        "inv_skew_bound", "inv_no_read_absent", "inv_expand_state", "inv_backfill_state",
        "inv_contract_state", "inv_contract_needs_no_old", "inv_done_state",
    }
    assert all(v == "OK" for v in verdicts.values()), verdicts


def test_vacuity_contradictory_reports_impossible():
    out = run_json("vacuity", str(EXAMPLES / "contradictory.yaml"))
    assert out["verdict"] == "IMPOSSIBLE"


def test_vacuity_surprising_all_ok():
    out = run_json("vacuity", str(EXAMPLES / "surprising.yaml"))
    verdicts = {r["name"]: r["verdict"] for r in out["results"]}
    assert all(v == "OK" for v in verdicts.values()), verdicts


def test_vacuity_detects_injected_tautology_and_redundancy(tmp_path):
    spec = """
variables:
  x:
    type: int
    min: 0
    max: 10
invariants:
  - name: inv_base
    description: base bound
    formula: "x <= 5"
  - name: inv_tautology
    description: always true given the domain
    formula: "x >= 0"
  - name: inv_redundant
    description: implied by inv_base
    formula: "x <= 8"
"""
    f = tmp_path / "vacuity_demo.yaml"
    f.write_text(spec)
    out = run_json("vacuity", str(f))
    verdicts = {r["name"]: r["verdict"] for r in out["results"]}
    assert verdicts["inv_base"] == "OK"
    assert verdicts["inv_tautology"] == "TAUTOLOGY"
    assert verdicts["inv_redundant"] == "REDUNDANT"


# -- claim ------------------------------------------------------------------


def test_claim_valid_on_consistent():
    out = run_json("claim", str(EXAMPLES / "consistent.yaml"), "--claim", CLAIM)
    assert out["verdict"] == "VALID"


def test_claim_satisfiable_on_surprising():
    out = run_json("claim", str(EXAMPLES / "surprising.yaml"), "--claim", CLAIM)
    assert out["verdict"] == "SATISFIABLE"
    assert out["witness_claim_true"] is not None
    assert out["witness_claim_false"] is not None


def test_claim_impossible_on_contradictory():
    out = run_json("claim", str(EXAMPLES / "contradictory.yaml"), "--claim", CLAIM)
    assert out["verdict"] == "IMPOSSIBLE"


def test_claim_invalid_case():
    # inv_skew_bound entails version_skew <= 1 with no escape valve, so a
    # claim asserting version_skew >= 2 must be INVALID (unsatisfiable
    # together with the invariants).
    out = run_json(
        "claim",
        str(EXAMPLES / "consistent.yaml"),
        "--claim",
        "version_skew >= 2",
    )
    assert out["verdict"] == "INVALID"


# -- expression language safety -----------------------------------------------


def test_unsafe_expression_is_rejected(tmp_path):
    spec = """
variables:
  x:
    type: int
invariants:
  - name: inv_evil
    description: attempts to escape the mini-language
    formula: "__import__('os').system('echo hi')"
"""
    f = tmp_path / "evil.yaml"
    f.write_text(spec)
    proc = run("check", str(f))
    assert proc.returncode not in (0,)
    assert "error" in (proc.stdout + proc.stderr).lower() or proc.returncode == 2
