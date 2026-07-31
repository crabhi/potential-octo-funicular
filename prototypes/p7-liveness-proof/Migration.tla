---------------------------- MODULE Migration ----------------------------
(* Track M: migration completion as a liveness theorem. Lean TLA+ port of
   the repaired protocol in prototypes/p4-agent-loop/protocol/migration.qnt
   (ghost read machinery dropped: it does not affect completion).

   RESULT (see README): completion holds under weak fairness of the
   migration actions + rollout even with UNBOUNDED app-write interference
   (BOUNDED = FALSE) — the anticipated backfill-starvation lasso is
   structurally impossible in this choreography, because post-drain every
   app write is a dual-write: any write that aborts a backfill also syncs
   the very row the backfill was copying. The classic starvation scenario
   requires non-dual-writing interference, which the drain gate excludes.
   The negative control (SpecNoRollout: drop fairness on Upgrade only)
   shows the rollout-fairness assumption is necessary: TLC returns a lasso
   where an instance never upgrades and the migration waits forever. *)
EXTENDS Integers, FiniteSets

CONSTANTS BOUNDED, BUDGET

KEYS == {1, 2}
VALUES == {1, 2}
INSTANCES == {1, 2}
NULL == -1

\* column states: 0 absent, 1 write-only, 2 present, 3 delete-only
\* phases: 0 initial, 1 expanded, 2 switched, 3 contracting, 4 done

VARIABLES phase, oState, nState, dbO, dbN, logical, dirty, instVer,
          bfA, bfK, bfV, writesLeft

vars == <<phase, oState, nState, dbO, dbN, logical, dirty, instVer,
          bfA, bfK, bfV, writesLeft>>

Init ==
  /\ phase = 0 /\ oState = 2 /\ nState = 0
  /\ dbO = [k \in KEYS |-> 0]
  /\ dbN = [k \in KEYS |-> NULL]
  /\ logical = [k \in KEYS |-> 0]
  /\ dirty = [k \in KEYS |-> FALSE]
  /\ instVer = [i \in INSTANCES |-> 1]
  /\ bfA = FALSE /\ bfK = 0 /\ bfV = 0
  /\ writesLeft = BUDGET

CanWrite == IF BOUNDED THEN writesLeft > 0 ELSE TRUE
WriteTick == writesLeft' = IF BOUNDED THEN writesLeft - 1 ELSE writesLeft

AppWriteV1(i, k, v) ==
  /\ CanWrite /\ instVer[i] = 1 /\ oState = 2
  /\ dbO' = [dbO EXCEPT ![k] = v]
  /\ logical' = [logical EXCEPT ![k] = v]
  /\ dirty' = [dirty EXCEPT ![k] = TRUE]
  /\ WriteTick
  /\ UNCHANGED <<phase, oState, nState, dbN, instVer, bfA, bfK, bfV>>

AppWriteV2(i, k, v) ==
  /\ CanWrite /\ instVer[i] = 2
  /\ (oState = 2 \/ nState /= 0)
  /\ dbO' = IF oState = 2 THEN [dbO EXCEPT ![k] = v] ELSE dbO
  /\ dbN' = IF nState /= 0 THEN [dbN EXCEPT ![k] = v] ELSE dbN
  /\ logical' = [logical EXCEPT ![k] = v]
  /\ dirty' = [dirty EXCEPT ![k] = TRUE]
  /\ WriteTick
  /\ UNCHANGED <<phase, oState, nState, instVer, bfA, bfK, bfV>>

AppWrite == \E i \in INSTANCES, k \in KEYS, v \in VALUES:
              AppWriteV1(i, k, v) \/ AppWriteV2(i, k, v)

Upgrade == \E i \in INSTANCES:
  /\ instVer[i] = 1 /\ nState /= 0
  /\ instVer' = [instVer EXCEPT ![i] = 2]
  /\ UNCHANGED <<phase, oState, nState, dbO, dbN, logical, dirty,
                 bfA, bfK, bfV, writesLeft>>

Expand ==
  /\ phase = 0
  /\ phase' = 1 /\ nState' = 1
  /\ UNCHANGED <<oState, dbO, dbN, logical, dirty, instVer,
                 bfA, bfK, bfV, writesLeft>>

BackfillBegin == \E k \in KEYS:
  /\ phase = 1 /\ ~bfA
  /\ dbN[k] /= dbO[k]                       \* re-copy out-of-sync rows
  /\ \A i \in INSTANCES: instVer[i] = 2     \* drain
  /\ bfA' = TRUE /\ bfK' = k /\ bfV' = dbO[k]
  /\ dirty' = [dirty EXCEPT ![k] = FALSE]
  /\ UNCHANGED <<phase, oState, nState, dbO, dbN, logical, instVer, writesLeft>>

BackfillCommit ==
  /\ bfA /\ ~dirty[bfK]
  /\ dbN' = [dbN EXCEPT ![bfK] = bfV]
  /\ bfA' = FALSE /\ bfK' = 0 /\ bfV' = 0
  /\ UNCHANGED <<phase, oState, nState, dbO, logical, dirty, instVer, writesLeft>>

BackfillAbort ==
  /\ bfA /\ dirty[bfK]
  /\ bfA' = FALSE /\ bfK' = 0 /\ bfV' = 0
  /\ UNCHANGED <<phase, oState, nState, dbO, dbN, logical, dirty, instVer, writesLeft>>

SwitchRead ==
  /\ phase = 1 /\ ~bfA
  /\ \A k \in KEYS: dbN[k] = dbO[k]
  /\ \A i \in INSTANCES: instVer[i] = 2
  /\ phase' = 2 /\ nState' = 2
  /\ UNCHANGED <<oState, dbO, dbN, logical, dirty, instVer,
                 bfA, bfK, bfV, writesLeft>>

ContractStart ==
  /\ phase = 2
  /\ phase' = 3 /\ oState' = 3
  /\ UNCHANGED <<nState, dbO, dbN, logical, dirty, instVer,
                 bfA, bfK, bfV, writesLeft>>

ContractFinish ==
  /\ phase = 3
  /\ phase' = 4 /\ oState' = 0
  /\ UNCHANGED <<nState, dbO, dbN, logical, dirty, instVer,
                 bfA, bfK, bfV, writesLeft>>

Next == AppWrite \/ Upgrade \/ Expand \/ BackfillBegin \/ BackfillCommit
        \/ BackfillAbort \/ SwitchRead \/ ContractStart \/ ContractFinish

\* Fairness ONLY on migration machinery — app writes owe us nothing.
MigrationFairness ==
  /\ WF_vars(Expand) /\ WF_vars(Upgrade)
  /\ WF_vars(BackfillBegin) /\ WF_vars(BackfillCommit) /\ WF_vars(BackfillAbort)
  /\ WF_vars(SwitchRead) /\ WF_vars(ContractStart) /\ WF_vars(ContractFinish)

Spec == Init /\ [][Next]_vars /\ MigrationFairness

\* Negative control: same fairness EXCEPT the rollout (Upgrade) — models an
\* operator who never finishes the deploy. Completion must NOT hold.
NoRolloutFairness ==
  /\ WF_vars(Expand)
  /\ WF_vars(BackfillBegin) /\ WF_vars(BackfillCommit) /\ WF_vars(BackfillAbort)
  /\ WF_vars(SwitchRead) /\ WF_vars(ContractStart) /\ WF_vars(ContractFinish)

SpecNoRollout == Init /\ [][Next]_vars /\ NoRolloutFairness

Completion == <>(phase = 4)

ColumnsAgree == (phase = 2 /\ oState = 2) => \A k \in KEYS: dbN[k] = dbO[k]

=============================================================================
