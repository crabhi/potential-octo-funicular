"""Hypothesis stateful conformance test.

RuleBasedStateMachine drives the REAL running API (sequentially -- no
concurrency here, that's test_concurrent.py's job) through creates, updates,
reads, and migration-advance steps, interleaved in whatever order Hypothesis
picks. Model: an in-memory dict of expected id -> current name.

Invariant checked after every read (see `read_user`): the value returned by
either app instance must equal the model's expected current name --
regardless of which migration phase we're in and regardless of which app
version served the request. This directly instruments research/05's
invariant "no request observes a column that is gone" (surfaced as a 5xx
here, asserted away) and the F1 "no orphan/integrity anomaly" invariant
(surfaced as a stale/wrong read, asserted away).

One deliberate simplification tied to a *documented* invariant from note 05
("Contract only after drain: migrationPhase=Contract implies all app
instances are >= N+1"): once read-switch has been flipped we stop routing
new traffic to the v1 instance before invoking `contract`, mirroring the
real operational precondition. See test_concurrent.py for what happens if
you violate it on purpose.
"""
import string

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, invariant, rule

import common

NAME_ALPHABET = string.ascii_letters + string.digits + " -_"
names = st.text(alphabet=NAME_ALPHABET, min_size=1, max_size=24)


class MigrationConformance(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        common.reset_db()
        common.wait_for_health(common.BASE_V1)
        common.wait_for_health(common.BASE_V2)
        self.expected = {}
        self.step_idx = 0  # index into common.MIGRATION_STEPS[:-1] (contract handled separately)
        self.v1_drained = False
        self.done = False

    ids = Bundle("ids")

    @rule(target=ids, name=names)
    def create_user(self, name):
        base = common.BASE_V2 if self.v1_drained else common.BASE_V1
        status, body = common.create_user(base, name)
        assert status < 500, f"5xx on create via {base}: {status} {body}"
        assert not common.is_schema_error(status, body), f"schema error on create: {body}"
        assert status == 201, f"unexpected status on create: {status} {body}"
        uid = body["id"]
        self.expected[uid] = name
        return uid

    @rule(uid=ids, name=names)
    def update_user(self, uid, name):
        base = common.BASE_V2 if self.v1_drained else common.BASE_V1
        status, body = common.update_user(base, uid, name)
        assert status < 500, f"5xx on update via {base}: {status} {body}"
        assert not common.is_schema_error(status, body), f"schema error on update: {body}"
        if status == 200:
            self.expected[uid] = name

    @rule(uid=ids)
    def read_user(self, uid):
        targets = [common.BASE_V2] if self.v1_drained else [common.BASE_V1, common.BASE_V2]
        for base in targets:
            status, body = common.get_user(base, uid)
            assert status < 500, f"5xx on read via {base}: {status} {body}"
            assert not common.is_schema_error(status, body), f"schema error on read via {base}: {body}"
            if status == 200:
                assert body["name"] == self.expected[uid], (
                    f"stale/wrong read via {base} (v1_drained={self.v1_drained}): "
                    f"expected {self.expected[uid]!r}, got {body['name']!r}"
                )

    @rule()
    def advance_migration(self):
        pre_contract = common.MIGRATION_STEPS[:-1]  # expand, install-trigger, backfill, read-switch
        if self.done:
            return
        if self.step_idx < len(pre_contract):
            step = pre_contract[self.step_idx]
            common.run_migrate_step(step)
            self.step_idx += 1
            if step == "read-switch":
                # Operational precondition (note 05): drain v1 before contract.
                self.v1_drained = True
        elif self.v1_drained:
            common.run_migrate_step("contract")
            self.done = True

    @invariant()
    def health_always_ok(self):
        # Only probe v1 while it is still a legitimate traffic target -- once
        # drained (see advance_migration), contract may drop the column v1
        # depends on, and hitting it deliberately is test_concurrent.py's job.
        targets = [common.BASE_V2] if self.v1_drained else [common.BASE_V1, common.BASE_V2]
        for base in targets:
            status, _ = common.get_user(base, 0)  # id 0 never exists; just check liveness
            assert status in (404, 200), f"{base} unhealthy: status={status}"


TestMigrationConformance = MigrationConformance.TestCase
TestMigrationConformance.settings = settings(
    max_examples=8,
    stateful_step_count=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


if __name__ == "__main__":
    import unittest

    unittest.main()
