// Protocol under repair (P4 agent-loop testbed).
//
// Online schema migration: rename column O -> N (expand/contract) while two
// app instances serve reads/writes under snapshot isolation. Drain
// choreography (all instances upgraded to dual-writing v2 before backfill
// and before the read switch) is already in place.
//
// The protocol below contains at least one flaw. The repair agent may edit
// the ACTIONS in this file. The invariant section at the bottom is FROZEN:
// any change to it is reverted by the harness and the round counts as
// failed.

module migration {
  pure val KEYS = Set(1, 2)
  pure val VALUES = Set(1, 2)
  pure val INSTANCES = Set(1, 2)

  pure val NULL = -1

  pure val COL_ABSENT = 0
  pure val COL_WRITEONLY = 1
  pure val COL_PRESENT = 2
  pure val COL_DELETEONLY = 3

  pure val P_INITIAL = 0
  pure val P_EXPANDED = 1
  pure val P_SWITCHED = 2
  pure val P_CONTRACTING = 3
  pure val P_DONE = 4

  var phase: int
  var oState: int
  var nState: int
  var dbO: int -> int
  var dbN: int -> int
  var logical: int -> int
  var ver: int -> int
  var instVer: int -> int
  var bf: (bool, int, int, int)
  var lastReadOk: bool

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

  // v1 instance: writes the old column only.
  action appWriteV1U(i: int, k: int, v: int): bool = all {
    instVer.get(i) == 1,
    oState == COL_PRESENT,
    dbO' = dbO.set(k, v),
    dbN' = dbN,
    logical' = logical.set(k, v),
    ver' = ver.set(k, ver.get(k) + 1),
    keepMig, keepBf, keepInst, keepRead,
  }

  action appWriteV1 = {
    nondet i = INSTANCES.oneOf()
    nondet k = KEYS.oneOf()
    nondet v = VALUES.oneOf()
    appWriteV1U(i, k, v)
  }

  // v2 instance: dual-writes O (while present) and N (once it exists).
  action appWriteV2U(i: int, k: int, v: int): bool = all {
    instVer.get(i) == 2,
    or { oState == COL_PRESENT, nState != COL_ABSENT },
    dbO' = if (oState == COL_PRESENT) dbO.set(k, v) else dbO,
    dbN' = if (nState != COL_ABSENT) dbN.set(k, v) else dbN,
    logical' = logical.set(k, v),
    ver' = ver.set(k, ver.get(k) + 1),
    keepMig, keepBf, keepInst, keepRead,
  }

  action appWriteV2 = {
    nondet i = INSTANCES.oneOf()
    nondet k = KEYS.oneOf()
    nondet v = VALUES.oneOf()
    appWriteV2U(i, k, v)
  }

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

  action upgradeU(i: int): bool = all {
    instVer.get(i) == 1,
    nState != COL_ABSENT,
    instVer' = instVer.set(i, 2),
    keepDb, keepMig, keepBf, keepRead,
  }

  action upgrade = {
    nondet i = INSTANCES.oneOf()
    upgradeU(i)
  }

  action expand = all {
    phase == P_INITIAL,
    phase' = P_EXPANDED,
    nState' = COL_WRITEONLY,
    oState' = oState,
    keepDb, keepBf, keepInst, keepRead,
  }

  // Backfill under snapshot isolation: begin takes a snapshot of one
  // not-yet-backfilled row (value + row version); commit succeeds only if
  // no write committed in between (first committer wins).
  action backfillBeginU(k: int): bool = all {
    phase == P_EXPANDED,
    not(bf._1),
    dbN.get(k) == NULL,
    INSTANCES.forall(i => instVer.get(i) == 2),
    bf' = (true, k, dbO.get(k), ver.get(k)),
    keepDb, keepMig, keepInst, keepRead,
  }

  action backfillBegin = {
    nondet k = KEYS.oneOf()
    backfillBeginU(k)
  }

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

  action backfillAbort = all {
    bf._1,
    ver.get(bf._2) != bf._4,
    bf' = (false, 0, 0, 0),
    keepDb, keepMig, keepInst, keepRead,
  }

  // Read switch: N becomes readable once every row has a value.
  action switchRead = all {
    phase == P_EXPANDED,
    not(bf._1),
    KEYS.forall(k => dbN.get(k) != NULL),
    INSTANCES.forall(i => instVer.get(i) == 2),
    phase' = P_SWITCHED,
    nState' = COL_PRESENT,
    oState' = oState,
    keepDb, keepBf, keepInst, keepRead,
  }

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

  // ==== INVARIANTS — FROZEN: the harness reverts ANY edit below this line ====

  val invReadsCorrect = lastReadOk

  val invColumnsAgree =
    (phase == P_SWITCHED and oState == COL_PRESENT)
      implies KEYS.forall(k => dbN.get(k) == dbO.get(k))

  val invBackfillDoneAtSwitch =
    (phase >= P_SWITCHED) implies KEYS.forall(k => dbN.get(k) != NULL)

  val invAll = and { invReadsCorrect, invColumnsAgree, invBackfillDoneAtSwitch }

  // ---- Feature/liveness gate (also FROZEN) --------------------------------
  //
  // Safety alone is gameable: a protocol that can never switch reads
  // satisfies every invariant above. The properties below pin the
  // must-still-work side and are part of the repair gate.

  // F1: completion must stay reachable — random exploration has to be able
  // to drive the migration to P_DONE at all (checked as a witness count).
  val featDone = phase == P_DONE

  // F2 (adversarial recovery): during the rolling window, a v2 instance
  // dual-writes key 1, then a still-v1 instance overwrites key 1's old
  // column (its N copy is now stale). After the drain completes, the
  // migration machinery ALONE must still be able to repair that row and
  // reach the read switch. A protocol that strands stale rows fails here.
  run staleRowRecoveryTest = init
    .then(expand)
    .then(upgradeU(1))
    .then(appWriteV2U(1, 1, 1))   // v2 dual-write: O[1]=1, N[1]=1
    .then(appWriteV1U(2, 1, 2))   // v1 write:      O[1]=2, N[1] stale
    .then(upgradeU(2))            // drain complete
    .then(backfillBeginU(1))      // must be enabled for the stale row
    .then(backfillCommit)
    .then(backfillBeginU(2))
    .then(backfillCommit)
    .then(switchRead)
    .expect(phase == P_SWITCHED and lastReadOk)

  // F3 (happy path): the plain migration must still complete end to end.
  run happyPathTest = init
    .then(expand)
    .then(upgradeU(1))
    .then(upgradeU(2))
    .then(backfillBeginU(1))
    .then(backfillCommit)
    .then(backfillBeginU(2))
    .then(backfillCommit)
    .then(switchRead)
    .then(contractStart)
    .then(contractFinish)
    .expect(phase == P_DONE and lastReadOk)
}
