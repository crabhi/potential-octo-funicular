---- MODULE Migration_TTrace_1785480746 ----
EXTENDS Sequences, TLCExt, Migration_TEConstants, Migration, Toolbox, Naturals, TLC

_expression ==
    LET Migration_TEExpression == INSTANCE Migration_TEExpression
    IN Migration_TEExpression!expression
----

_trace ==
    LET Migration_TETrace == INSTANCE Migration_TETrace
    IN Migration_TETrace!trace
----

_prop ==
    ~(([]<>(
            dirty = (<<TRUE, TRUE>>)
            /\
            dbO = (<<1, 2>>)
            /\
            phase = (1)
            /\
            instVer = (<<2, 1>>)
            /\
            dbN = (<<1, 2>>)
            /\
            bfV = (0)
            /\
            oState = (2)
            /\
            bfK = (0)
            /\
            writesLeft = (0)
            /\
            bfA = (FALSE)
            /\
            logical = (<<1, 2>>)
            /\
            nState = (1)
    ))/\([]<>(
            dirty = (<<TRUE, TRUE>>)
            /\
            dbO = (<<1, 1>>)
            /\
            phase = (1)
            /\
            instVer = (<<2, 1>>)
            /\
            dbN = (<<1, 1>>)
            /\
            bfV = (0)
            /\
            oState = (2)
            /\
            bfK = (0)
            /\
            writesLeft = (0)
            /\
            bfA = (FALSE)
            /\
            logical = (<<1, 1>>)
            /\
            nState = (1)
    )))
----

_init ==
    /\ bfK = _TETrace[1].bfK
    /\ logical = _TETrace[1].logical
    /\ bfV = _TETrace[1].bfV
    /\ dirty = _TETrace[1].dirty
    /\ dbN = _TETrace[1].dbN
    /\ dbO = _TETrace[1].dbO
    /\ writesLeft = _TETrace[1].writesLeft
    /\ phase = _TETrace[1].phase
    /\ oState = _TETrace[1].oState
    /\ nState = _TETrace[1].nState
    /\ instVer = _TETrace[1].instVer
    /\ bfA = _TETrace[1].bfA
----

_next ==
    /\ \E i,j \in DOMAIN _TETrace:
        /\ \/ /\ j = i + 1
              /\ i = TLCGet("level")
           \/ /\ i = _TTraceLassoEnd
              /\ j = _TTraceLassoStart
        /\ bfK  = _TETrace[i].bfK
        /\ bfK' = _TETrace[j].bfK
        /\ logical  = _TETrace[i].logical
        /\ logical' = _TETrace[j].logical
        /\ bfV  = _TETrace[i].bfV
        /\ bfV' = _TETrace[j].bfV
        /\ dirty  = _TETrace[i].dirty
        /\ dirty' = _TETrace[j].dirty
        /\ dbN  = _TETrace[i].dbN
        /\ dbN' = _TETrace[j].dbN
        /\ dbO  = _TETrace[i].dbO
        /\ dbO' = _TETrace[j].dbO
        /\ writesLeft  = _TETrace[i].writesLeft
        /\ writesLeft' = _TETrace[j].writesLeft
        /\ phase  = _TETrace[i].phase
        /\ phase' = _TETrace[j].phase
        /\ oState  = _TETrace[i].oState
        /\ oState' = _TETrace[j].oState
        /\ nState  = _TETrace[i].nState
        /\ nState' = _TETrace[j].nState
        /\ instVer  = _TETrace[i].instVer
        /\ instVer' = _TETrace[j].instVer
        /\ bfA  = _TETrace[i].bfA
        /\ bfA' = _TETrace[j].bfA

\* Uncomment the ASSUME below to write the states of the error trace
\* to the given file in Json format. Note that you can pass any tuple
\* to `JsonSerialize`. For example, a sub-sequence of _TETrace.
    \* ASSUME
    \*     LET J == INSTANCE Json
    \*         IN J!JsonSerialize("Migration_TTrace_1785480746.json", _TETrace)


_view ==
    <<bfK, logical, bfV, dirty, dbN, dbO, writesLeft, phase, oState, nState, instVer, bfA, IF TLCGet("level") = _TTraceLassoEnd + 1 THEN _TTraceLassoStart ELSE TLCGet("level")>>
=============================================================================

 Note that you can extract this module `Migration_TEExpression`
  to a dedicated file to reuse `expression` (the module in the 
  dedicated `Migration_TEExpression.tla` file takes precedence 
  over the module `Migration_TEExpression` below).

---- MODULE Migration_TEExpression ----
EXTENDS Sequences, TLCExt, Migration_TEConstants, Migration, Toolbox, Naturals, TLC

expression == 
    [
        \* To hide variables of the `Migration` spec from the error trace,
        \* remove the variables below.  The trace will be written in the order
        \* of the fields of this record.
        bfK |-> bfK
        ,logical |-> logical
        ,bfV |-> bfV
        ,dirty |-> dirty
        ,dbN |-> dbN
        ,dbO |-> dbO
        ,writesLeft |-> writesLeft
        ,phase |-> phase
        ,oState |-> oState
        ,nState |-> nState
        ,instVer |-> instVer
        ,bfA |-> bfA
        
        \* Put additional constant-, state-, and action-level expressions here:
        \* ,_stateNumber |-> _TEPosition
        \* ,_bfKUnchanged |-> bfK = bfK'
        
        \* Format the `bfK` variable as Json value.
        \* ,_bfKJson |->
        \*     LET J == INSTANCE Json
        \*     IN J!ToJson(bfK)
        
        \* Lastly, you may build expressions over arbitrary sets of states by
        \* leveraging the _TETrace operator.  For example, this is how to
        \* count the number of times a spec variable changed up to the current
        \* state in the trace.
        \* ,_bfKModCount |->
        \*     LET F[s \in DOMAIN _TETrace] ==
        \*         IF s = 1 THEN 0
        \*         ELSE IF _TETrace[s].bfK # _TETrace[s-1].bfK
        \*             THEN 1 + F[s-1] ELSE F[s-1]
        \*     IN F[_TEPosition - 1]
    ]

=============================================================================



Parsing and semantic processing can take forever if the trace below is long.
 In this case, it is advised to uncomment the module below to deserialize the
 trace from a generated binary file.

\*
\*---- MODULE Migration_TETrace ----
\*EXTENDS IOUtils, Migration_TEConstants, Migration, TLC
\*
\*trace == IODeserialize("Migration_TTrace_1785480746.bin", TRUE)
\*
\*=============================================================================
\*

---- MODULE Migration_TETrace ----
EXTENDS Migration_TEConstants, Migration, TLC

trace == 
    <<
    ([dirty |-> <<FALSE, FALSE>>,dbO |-> <<0, 0>>,phase |-> 0,instVer |-> <<1, 1>>,dbN |-> <<-1, -1>>,bfV |-> 0,oState |-> 2,bfK |-> 0,writesLeft |-> 0,bfA |-> FALSE,logical |-> <<0, 0>>,nState |-> 0]),
    ([dirty |-> <<FALSE, FALSE>>,dbO |-> <<0, 0>>,phase |-> 1,instVer |-> <<1, 1>>,dbN |-> <<-1, -1>>,bfV |-> 0,oState |-> 2,bfK |-> 0,writesLeft |-> 0,bfA |-> FALSE,logical |-> <<0, 0>>,nState |-> 1]),
    ([dirty |-> <<FALSE, FALSE>>,dbO |-> <<0, 0>>,phase |-> 1,instVer |-> <<2, 1>>,dbN |-> <<-1, -1>>,bfV |-> 0,oState |-> 2,bfK |-> 0,writesLeft |-> 0,bfA |-> FALSE,logical |-> <<0, 0>>,nState |-> 1]),
    ([dirty |-> <<FALSE, TRUE>>,dbO |-> <<0, 1>>,phase |-> 1,instVer |-> <<2, 1>>,dbN |-> <<-1, 1>>,bfV |-> 0,oState |-> 2,bfK |-> 0,writesLeft |-> 0,bfA |-> FALSE,logical |-> <<0, 1>>,nState |-> 1]),
    ([dirty |-> <<TRUE, TRUE>>,dbO |-> <<1, 1>>,phase |-> 1,instVer |-> <<2, 1>>,dbN |-> <<1, 1>>,bfV |-> 0,oState |-> 2,bfK |-> 0,writesLeft |-> 0,bfA |-> FALSE,logical |-> <<1, 1>>,nState |-> 1]),
    ([dirty |-> <<TRUE, TRUE>>,dbO |-> <<1, 2>>,phase |-> 1,instVer |-> <<2, 1>>,dbN |-> <<1, 2>>,bfV |-> 0,oState |-> 2,bfK |-> 0,writesLeft |-> 0,bfA |-> FALSE,logical |-> <<1, 2>>,nState |-> 1])
    >>
----


=============================================================================

---- MODULE Migration_TEConstants ----
EXTENDS Migration

CONSTANTS _TTraceLassoStart, _TTraceLassoEnd

=============================================================================

---- CONFIG Migration_TTrace_1785480746 ----
CONSTANTS
    BOUNDED = FALSE
    BUDGET = 0
_TTraceLassoStart = 5
_TTraceLassoEnd = 6

PROPERTY
    _prop

CHECK_DEADLOCK
    \* CHECK_DEADLOCK off because of PROPERTY or INVARIANT above.
    FALSE

INIT
    _init

NEXT
    _next

VIEW
    _view

CONSTANT
    _TETrace <- _trace

ALIAS
    _expression
=============================================================================
\* Generated on Fri Jul 31 06:52:26 UTC 2026