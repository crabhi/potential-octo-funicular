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

  // v2 instance: dual-writes O (while present) and N (once it exists).
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

  action upgrade = {
    nondet i = INSTANCES.oneOf()
    all {
      instVer.get(i) == 1,
      nState != COL_ABSENT,
      instVer' = instVer.set(i, 2),
      keepDb, keepMig, keepBf, keepRead,
    }
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
  action backfillBegin = {
    nondet k = KEYS.oneOf()
    all {
      phase == P_EXPANDED,
      not(bf._1),
      dbN.get(k) == NULL,
      INSTANCES.forall(i => instVer.get(i) == 2),
      bf' = (true, k, dbO.get(k), ver.get(k)),
      keepDb, keepMig, keepInst, keepRead,
    }
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

  // Read switch: N becomes readable once every row truly matches O (a
  // non-null N is not enough — a still-v1 instance can write O only,
  // after N was set, leaving N stale for that key).
  action switchRead = all {
    phase == P_EXPANDED,
    not(bf._1),
    KEYS.forall(k => dbN.get(k) == dbO.get(k)),
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
}
