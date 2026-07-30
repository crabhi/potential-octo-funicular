// P1: Online schema migration (expand/contract) concurrent with API requests,
// under snapshot isolation. See README.md.
//
// Scenario: rename column `name` (O) to `full_name` (N) while two app
// instances serve reads/writes. Migration follows F1-style column states
// (Absent -> WriteOnly -> Present, Present -> DeleteOnly -> Absent) and the
// expand/contract phases: expand, backfill, read switch, contract.
//
// Encoding choices (prototype simplicity over elegance):
// - NULL is encoded as -1 (values are small non-negative ints).
// - Column states and phases are ints with named constants.
// - App write/read transactions are single-statement, so their snapshot is
//   taken and used atomically (SI == atomic action for them). The backfill
//   is the genuinely multi-step SI transaction: it takes a snapshot (read of
//   O plus the row version) and commits later with first-committer-wins
//   conflict detection on the row version, as Postgres REPEATABLE READ does
//   at row granularity.
// - `logical` is a ghost variable: the value the application believes key k
//   holds (last committed app write). Migration steps must never change it.
//
// The DRAIN_GUARD constant is the interesting knob: when true, backfill may
// only start after every app instance runs version 2 (dual-write). When
// false, a v1 instance (writes O only) may keep writing after its row was
// backfilled, so N goes stale and a post-switch read returns a stale value.

module migration {
  const DRAIN_GUARD: bool

  pure val KEYS = Set(1, 2)
  pure val VALUES = Set(1, 2)
  pure val INSTANCES = Set(1, 2)

  pure val NULL = -1

  // column states (F1)
  pure val COL_ABSENT = 0
  pure val COL_WRITEONLY = 1
  pure val COL_PRESENT = 2
  pure val COL_DELETEONLY = 3

  // migration phases
  pure val P_INITIAL = 0    // only O exists
  pure val P_EXPANDED = 1   // N added write-only; instances upgrade; backfill
  pure val P_SWITCHED = 2   // reads served from N
  pure val P_CONTRACTING = 3 // O delete-only
  pure val P_DONE = 4       // O absent

  var phase: int
  var oState: int
  var nState: int
  var dbO: int -> int              // committed value of column O per key
  var dbN: int -> int              // committed value of column N per key
  var logical: int -> int          // ghost: last app-written value per key
  var ver: int -> int              // committed row version (for SI conflicts)
  var instVer: int -> int          // app instance -> app version (1 or 2)
  // in-flight backfill transaction: (active, key, value read at snapshot,
  // row version at snapshot)
  var bf: (bool, int, int, int)
  var lastReadOk: bool             // ghost: false once any read was stale

  action keepDb = all { dbO' = dbO, dbN' = dbN, logical' = logical, ver' = ver }
  action keepMig = all { phase' = phase, oState' = oState, nState' = nState }
  action keepBf = bf' = bf
  action keepInst = instVer' = instVer
  action keepRead = lastReadOk' = lastReadOk

  action init = all {
    phase' = P_INITIAL,
    oState' = COL_PRESENT,
    nState' = COL_ABSENT,
    dbO' = KEYS.mapBy(k => 0),
    dbN' = KEYS.mapBy(k => NULL),
    logical' = KEYS.mapBy(k => 0),
    ver' = KEYS.mapBy(k => 0),
    instVer' = INSTANCES.mapBy(i => 1),
    bf' = (false, 0, 0, 0),
    lastReadOk' = true,
  }

  // A version-1 instance writes the old column only.
  action appWriteV1 = {
    nondet i = INSTANCES.oneOf()
    nondet k = KEYS.oneOf()
    nondet v = VALUES.oneOf()
    all {
      instVer.get(i) == 1,
      oState == COL_PRESENT,
      dbO' = dbO.set(k, v),
      dbN' = dbN,
      logical' = logical.set(k, v),
      ver' = ver.set(k, ver.get(k) + 1),
      keepMig, keepBf, keepInst, keepRead,
    }
  }

  // A version-2 instance dual-writes: O while it is still present,
  // N as soon as it exists (write-only or present).
  action appWriteV2 = {
    nondet i = INSTANCES.oneOf()
    nondet k = KEYS.oneOf()
    nondet v = VALUES.oneOf()
    all {
      instVer.get(i) == 2,
      or { oState == COL_PRESENT, nState != COL_ABSENT },
      dbO' = if (oState == COL_PRESENT) dbO.set(k, v) else dbO,
      dbN' = if (nState != COL_ABSENT) dbN.set(k, v) else dbN,
      logical' = logical.set(k, v),
      ver' = ver.set(k, ver.get(k) + 1),
      keepMig, keepBf, keepInst, keepRead,
    }
  }

  // Any instance serves a read. v2 instances read N once it is switched to
  // Present; otherwise everyone reads O. The ghost check records whether the
  // returned value matches the application's logical value.
  action appRead = {
    nondet i = INSTANCES.oneOf()
    nondet k = KEYS.oneOf()
    val fromN = and { nState == COL_PRESENT, instVer.get(i) == 2 }
    val seen = if (fromN) dbN.get(k) else dbO.get(k)
    all {
      or { fromN, oState == COL_PRESENT },
      lastReadOk' = and { lastReadOk, seen == logical.get(k) },
      keepDb, keepMig, keepBf, keepInst,
    }
  }

  // Rolling deploy: upgrade one instance from v1 to v2.
  action upgrade = {
    nondet i = INSTANCES.oneOf()
    all {
      instVer.get(i) == 1,
      nState != COL_ABSENT,
      instVer' = instVer.set(i, 2),
      keepDb, keepMig, keepBf, keepRead,
    }
  }

  // Expand: add column N in write-only state.
  action expand = all {
    phase == P_INITIAL,
    phase' = P_EXPANDED,
    nState' = COL_WRITEONLY,
    oState' = oState,
    keepDb, keepBf, keepInst, keepRead,
  }

  // Backfill, step 1: open an SI transaction copying O -> N for one key that
  // is out of sync. Records the row version for conflict detection.
  //
  // NOTE: the first version used the textbook criterion `dbN.get(k) == NULL`
  // (SQL: WHERE full_name IS NULL) and the simulator found a counterexample:
  // during a rolling deploy a v2 instance dual-writes N for key k, then a
  // still-live v1 instance overwrites O only — N is non-NULL but STALE, and
  // an IS-NULL backfill never revisits it. The robust criterion is
  // `N IS DISTINCT FROM O`: re-copy any out-of-sync row.
  action backfillBegin = {
    nondet k = KEYS.oneOf()
    all {
      phase == P_EXPANDED,
      not(bf._1),
      dbN.get(k) != dbO.get(k),
      or { not(DRAIN_GUARD), INSTANCES.forall(i => instVer.get(i) == 2) },
      bf' = (true, k, dbO.get(k), ver.get(k)),
      keepDb, keepMig, keepInst, keepRead,
    }
  }

  // Backfill, step 2a: commit — allowed only if no other transaction
  // committed a write to this row since our snapshot (first committer wins).
  action backfillCommit = all {
    bf._1,
    ver.get(bf._2) == bf._4,
    dbN' = dbN.set(bf._2, bf._3),
    ver' = ver.set(bf._2, ver.get(bf._2) + 1),
    dbO' = dbO,
    logical' = logical,
    bf' = (false, 0, 0, 0),
    keepMig, keepInst, keepRead,
  }

  // Backfill, step 2b: abort on write-write conflict; a later begin retries.
  action backfillAbort = all {
    bf._1,
    ver.get(bf._2) != bf._4,
    bf' = (false, 0, 0, 0),
    keepDb, keepMig, keepInst, keepRead,
  }

  // Read switch: N becomes Present (readable) once fully backfilled and no
  // backfill transaction is in flight.
  //
  // NOTE the drain condition: the first version of this model guarded the
  // drain (all instances at v2) only at backfillBegin, and the simulator
  // found a counterexample within seconds — dbN can be filled entirely by
  // v2 dual-writes, so the switch could happen while a v1 instance was
  // still alive and writing only the old column afterwards. Drain must gate
  // BOTH backfill start and the read switch.
  action switchRead = all {
    phase == P_EXPANDED,
    not(bf._1),
    // "backfill ran to completion": every row is in sync, not merely non-NULL
    KEYS.forall(k => dbN.get(k) == dbO.get(k)),
    or { not(DRAIN_GUARD), INSTANCES.forall(i => instVer.get(i) == 2) },
    phase' = P_SWITCHED,
    nState' = COL_PRESENT,
    oState' = oState,
    keepDb, keepBf, keepInst, keepRead,
  }

  // Contract: O stops accepting reads/writes (delete-only), then disappears.
  action contractStart = all {
    phase == P_SWITCHED,
    phase' = P_CONTRACTING,
    oState' = COL_DELETEONLY,
    nState' = nState,
    keepDb, keepBf, keepInst, keepRead,
  }

  action contractFinish = all {
    phase == P_CONTRACTING,
    phase' = P_DONE,
    oState' = COL_ABSENT,
    nState' = nState,
    keepDb, keepBf, keepInst, keepRead,
  }

  action step = any {
    appWriteV1,
    appWriteV2,
    appRead,
    upgrade,
    expand,
    backfillBegin,
    backfillCommit,
    backfillAbort,
    switchRead,
    contractStart,
    contractFinish,
  }

  // ---- Invariants (the developer-facing formal requirements) ------------

  // I1: no committed read ever returned a value other than the application's
  // current logical value for that key.
  val invReadsCorrect = lastReadOk

  // I2: while both columns are live after the read switch, they agree —
  // the F1 "no integrity anomaly" condition for a rename.
  val invColumnsAgree =
    (phase == P_SWITCHED and oState == COL_PRESENT)
      implies KEYS.forall(k => dbN.get(k) == dbO.get(k))

  // I3: reads are never switched to N before every row is backfilled.
  val invBackfillDoneAtSwitch =
    (phase >= P_SWITCHED) implies KEYS.forall(k => dbN.get(k) != NULL)

  val invAll = and { invReadsCorrect, invColumnsAgree, invBackfillDoneAtSwitch }
}

// Correct configuration: backfill waits until every instance dual-writes.
module correct {
  import migration(DRAIN_GUARD = true).*
}

// Broken configuration: backfill may run while v1 instances still write only
// the old column. Model checking finds the stale-read counterexample.
module broken {
  import migration(DRAIN_GUARD = false).*
}
