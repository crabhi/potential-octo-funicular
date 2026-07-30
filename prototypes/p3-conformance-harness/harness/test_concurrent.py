"""Concurrent load test: real traffic against both instances while the real
migration runs in a background thread.

Two scenarios:

- test_concurrent_migration_with_drain: the compliant operational sequence.
  Once read-switch flips we stop sending traffic to v1 before running
  `contract` -- this is research/05's documented precondition ("Contract
  only after drain: migrationPhase=Contract implies all app instances are
  >= N+1"). Required invariants: no request ever gets a
  column-does-not-exist error or any 5xx; the final DB state matches the
  last write recorded for every user.

- test_concurrent_migration_without_drain_demonstrates_anomaly: deliberately
  skips that precondition (v1 keeps getting traffic straight through
  contract). This reproduces F1's "integrity anomaly" on purpose -- v1 tries
  to read/write `name` after it has been dropped -- as empirical evidence
  that the precondition is load-bearing, not decorative. See README.md
  "Findings".
"""
import random
import threading
import time
from collections import defaultdict

import common


class MigrationRunner(threading.Thread):
    """Drives the real migrate.py steps in a background thread while HTTP
    workers hit the real API concurrently."""

    STEPS = ["expand", "install-trigger", "backfill", "read-switch"]

    def __init__(self, drain_before_contract, step_pause_s=0.15, drain_pause_s=0.4, quiesce_pause_s=0.15):
        super().__init__(daemon=True)
        self.drain_before_contract = drain_before_contract
        self.step_pause_s = step_pause_s
        self.drain_pause_s = drain_pause_s
        self.quiesce_pause_s = quiesce_pause_s
        self._lock = threading.Lock()
        self._phase = "v1-only"
        self.timeline = []
        self._t0 = time.time()

    def _set_phase(self, phase):
        with self._lock:
            self._phase = phase
        self.timeline.append((round(time.time() - self._t0, 3), phase))

    @property
    def phase(self):
        with self._lock:
            return self._phase

    def v1_allowed(self):
        if self.drain_before_contract:
            return self.phase not in ("draining-v1", "quiescing", "contracted")
        return True  # chaos mode: keep hammering v1 straight through contract

    def v2_allowed(self):
        # See README "Findings" -- v2 itself has a TOCTOU race (read
        # migration_state flags, decide a query text, then execute it) that
        # a request can straddle across the exact instant `contract` commits.
        # A brief quiesce of *all* traffic right at the cutover (mirroring
        # the atomic-rename pause real online-DDL tools use) closes it; v1's
        # long drain window does not, because it only stops one side.
        if self.drain_before_contract:
            return self.phase != "quiescing"
        return True

    def run(self):
        for step in self.STEPS:
            common.run_migrate_step(step)
            self._set_phase(step)
            time.sleep(self.step_pause_s)
        if self.drain_before_contract:
            self._set_phase("draining-v1")
            time.sleep(self.drain_pause_s)
            self._set_phase("quiescing")
            time.sleep(self.quiesce_pause_s)
        common.run_migrate_step("contract")
        self._set_phase("contracted")


def worker_loop(worker_id, runner, stop_event, results, results_lock, model, model_lock, shared_ids, ids_lock):
    rng = random.Random(1000 + worker_id)
    while not stop_event.is_set():
        v1_ok, v2_ok = runner.v1_allowed(), runner.v2_allowed()
        if not v1_ok and not v2_ok:
            # Brief global quiesce around the exact contract cutover -- see
            # MigrationRunner.v2_allowed(). No request is sent this tick.
            time.sleep(0.005)
            continue
        if v1_ok and v2_ok:
            want_v1 = rng.random() < 0.5
        else:
            want_v1 = v1_ok
        base = common.BASE_V1 if want_v1 else common.BASE_V2
        version_tag = "v1" if want_v1 else "v2"
        phase = runner.phase
        with ids_lock:
            existing = list(shared_ids)
        op = "create" if (not existing or rng.random() < 0.25) else rng.choice(["update", "read"])
        try:
            if op == "create":
                name = f"w{worker_id}-{rng.randrange(10**7)}"
                status, body = common.create_user(base, name)
                if status == 201:
                    uid = body["id"]
                    with ids_lock:
                        shared_ids.append(uid)
                    with model_lock:
                        model[uid] = name
                err = str(body) if status >= 500 else None
            elif op == "update":
                uid = rng.choice(existing)
                name = f"w{worker_id}-{rng.randrange(10**7)}-u"
                status, body = common.update_user(base, uid, name)
                if status == 200:
                    with model_lock:
                        model[uid] = name
                err = str(body) if status >= 500 else None
            else:  # read
                uid = rng.choice(existing)
                status, body = common.get_user(base, uid)
                err = str(body) if status >= 500 else None
            with results_lock:
                results.append((phase, version_tag, op, status, err))
        except Exception as e:
            with results_lock:
                results.append((phase, version_tag, op, -1, str(e)))
        time.sleep(0.005)


def _run_concurrent_migration(drain_before_contract, num_workers=6):
    common.reset_db()
    common.wait_for_health(common.BASE_V1)
    common.wait_for_health(common.BASE_V2)

    status, body = common.create_user(common.BASE_V1, "seed")
    assert status == 201, f"seed create failed: {status} {body}"

    results = []
    results_lock = threading.Lock()
    model = {body["id"]: "seed"}
    model_lock = threading.Lock()
    shared_ids = [body["id"]]
    ids_lock = threading.Lock()

    runner = MigrationRunner(drain_before_contract=drain_before_contract)
    stop_event = threading.Event()
    workers = [
        threading.Thread(
            target=worker_loop,
            args=(i, runner, stop_event, results, results_lock, model, model_lock, shared_ids, ids_lock),
            daemon=True,
        )
        for i in range(num_workers)
    ]

    runner.start()
    for w in workers:
        w.start()

    runner.join(timeout=30)
    time.sleep(0.2)  # let a few more in-flight requests land in the post-migration phase
    stop_event.set()
    for w in workers:
        w.join(timeout=5)

    return results, model, runner.timeline


def _print_summary(label, results, timeline):
    by_phase = defaultdict(lambda: defaultdict(int))
    errors = []
    for phase, version, op, status, err in results:
        bucket = "ok" if status < 400 else ("4xx" if status < 500 else "5xx")
        by_phase[phase][bucket] += 1
        by_phase[phase][f"{version}:{op}"] += 1
        if status >= 500 or status == -1:
            errors.append((phase, version, op, status, err))

    print(f"\n=== {label} ===")
    print("migration timeline (elapsed_s, phase):", timeline)
    print(f"{'phase':<18}{'ok':>6}{'4xx':>6}{'5xx':>6}{'total':>8}")
    for phase, counts in by_phase.items():
        total = counts.get("ok", 0) + counts.get("4xx", 0) + counts.get("5xx", 0)
        print(f"{phase:<18}{counts.get('ok', 0):>6}{counts.get('4xx', 0):>6}{counts.get('5xx', 0):>6}{total:>8}")
    print(f"total requests: {len(results)}   errors (5xx/exception): {len(errors)}")
    for e in errors[:10]:
        print("   error:", e)
    if len(errors) > 10:
        print(f"   ... and {len(errors) - 10} more")
    return errors


def test_concurrent_migration_with_drain():
    results, model, timeline = _run_concurrent_migration(drain_before_contract=True)
    errors = _print_summary("WITH drain-before-contract (compliant)", results, timeline)

    schema_errors = [e for e in errors if "does not exist" in str(e[4])]
    assert not schema_errors, f"unexpected column-does-not-exist errors: {schema_errors}"
    assert not errors, f"unexpected 5xx/exception during compliant run: {errors}"

    time.sleep(0.2)  # quiesce: no more in-flight writes
    final_db = common.db_users_snapshot()
    mismatches = {
        uid: {"last_write": name, "db": final_db.get(uid)}
        for uid, name in model.items()
        if final_db.get(uid) != name
    }
    assert not mismatches, f"final DB state diverges from last recorded write: {mismatches}"
    print(f"final state check: {len(model)} users, all consistent with their last recorded write")


def test_concurrent_migration_without_drain_demonstrates_anomaly():
    results, model, timeline = _run_concurrent_migration(drain_before_contract=False)
    errors = _print_summary("WITHOUT drain-before-contract (chaos / negative test)", results, timeline)

    schema_errors = [e for e in errors if "does not exist" in str(e[4])]
    assert schema_errors, (
        "expected to reproduce the F1 'integrity anomaly' (column-does-not-exist "
        "errors) by skipping the drain-before-contract precondition, but saw none "
        "-- either timing was too generous, or the anomaly did not manifest this run"
    )
    print(f"reproduced {len(schema_errors)} schema-anomaly error(s) as expected -- see README 'Findings'")
