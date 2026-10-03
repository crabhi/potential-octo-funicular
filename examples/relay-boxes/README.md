# Relay on boxes — reviewed contracts, generated bodies, Monty sandboxes

Another approach to the same question as the rest of the repository
(*how do humans stay in control of code that LLMs write?*), tried on the
same product: **Relay**, the customer-support helpdesk of
`../helpdesk/` (tickets HD-1…HD-9 in `../helpdesk/TICKETS.md`).

Instead of a rule base that *is* the program, the program is split by
**who reviews it**:

| Humans review (hash-locked)            | An LLM generates (never reviewed line by line) |
|----------------------------------------|-----------------------------------------------|
| the **data model** — `relay/model.py` | every black-box **body** — `relay/impl/<box>.py`, run only inside a [Monty](https://github.com/pydantic/monty) micro-sandbox |
| the **state transitions + guard rules + kernel** — `relay/machine.py` | **generated tests** — `relay/tests/generated/` |
| the **types of the black boxes**, their capabilities, and each box's **description** (LLM-drafted, human-approved) — `relay/boxes.py` | |
| the **outer code** that turns box outputs into effects — `relay/shell.py` | |
| **reviewed tests** — `relay/tests/reviewed/` | |

The UI — routing, every view, every HTML template, the stylesheet — is
generated. So is the product logic that is not policy (queue sorting,
interpreting inbound email). None of it can write state, read a file,
reach the network, call a kernel method its contract does not list, or
return a value its reviewed type does not admit.

```
  ┌──────────── REVIEWED ────────────┐        ┌──────── GENERATED (Monty) ───────┐
  │ shell.py   HTTP · cookies · mail │──args─▶│ impl/route.py      req → command  │
  │            applies commands ─────┼─┐      │ impl/case_page.py  → HTML         │
  │ boxes.py   types · Protocols ·   │ │      │ impl/intake_email.py → intent     │
  │            signatures + descr.   │ │◀─ret─│ …8 boxes, each ONLY sees its stub │
  │ machine.py lifecycles · rules ·  │ │      └──────────────┬───────────────────┘
  │            Desk (the kernel)  ◀──┼─┘   DeskReader (read-only, per actor,     │
  │ model.py   frozen dataclasses    │◀──── exactly the Protocol's methods) ─────┘
  └──────────────────────────────────┘
```

## The DSL: plain Python + one file convention

```python
# relay/boxes.py (REVIEWED)
class DeskReader(Protocol):            # an object capability: the sandbox
    def cases(self) -> list[Case]: ... # can call exactly these methods
    ...

Escape = Callable[[str], str]          # a function capability

@blackbox
def sort_into_queues(cases: list[Case], today: date) -> list[Queue]:
    """Partition the cases … into the desk's six queues, in this order …
    "SLA breached" is a cross-state view …"""          # the reviewed description
    ...                                                 # no body — ever (linted)
```

```python
# relay/impl/sort_into_queues.py (GENERATED — first line pins the contract)
# boxkit: generated implementation of `sort_into_queues` against spec 1dfd4e1e…
def sort_into_queues(cases: list[Case], today: date) -> list[Queue]:
    ...
```

```python
# relay/machine.py (REVIEWED)
CASE = Lifecycle("case", CaseState, initial="new", terminal=("closed",), transitions=[
    T("triage", "new", "open"), T("wait", "open", "waiting"), ...])

@POLICY.deny("breach_needs_lead", "HD-5: once the SLA is breached …", on=("case",))
def _(s: Situation) -> bool:
    return s.action == "resolve" and s.breached and s.actor.role != "lead"
```

What `boxkit` derives mechanically from a `@blackbox` declaration:

* **the stub** — exactly the reviewed types the box can see (the transitive
  closure of its signature, copied verbatim from `model.py`/`boxes.py`) plus
  a `BoxkitContract` protocol for its signature. The implementer is shown
  only this (`python -m boxkit brief relay <box>`); the body is
  type-checked against it by [ty](https://docs.astral.sh/ty/) *inside Monty*;
* **the spec hash** — over stub + description. A generated file records the
  hash it was written against; change a reviewed type the box uses, or its
  description, and the body is **STALE** until regenerated (and only that
  box — unrelated contracts keep their hash);
* **the constructors** — the reviewed dataclasses in the closure are the
  only host classes the sandbox can instantiate (a box cannot mint a type
  its contract does not name);
* **the capability surfaces** — `Protocol` parameters become host objects
  whose callable surface is exactly the protocol's methods; `Callable`
  parameters become host functions; every argument the sandbox passes and
  every value that comes back is checked against the reviewed annotation.

## The gate

```bash
./check.sh       # everything, both directions (≈1 min; creates .venv)
python -m boxkit check relay          # the gate alone
python -m boxkit brief relay case_page  # what the implementer sees
python -m boxkit status relay         # what changed since the last review
python -m boxkit approve relay --by "<human>"   # re-stamp REVIEW.lock (humans only)
python -m relay.shell                 # serve http://127.0.0.1:8811/
```

`boxkit check` stages: (1) every reviewed file and every contract matches
`REVIEW.lock` — an agent edit to `machine.py` fails the gate until a human
re-approves; (2) contracts carry no logic; (3) lifecycles are well-formed
(reachability, determinism, declared terminals) and every rule names a
declared entity; (4) boundary lint — nothing reviewed imports `impl/`,
`impl/` files are self-contained sandbox modules on an import allowlist;
(5) every box has an implementation that is present, fresh (spec hash) and
type-correct against its stub.

`check.sh` adds the framework's hostile-body tests, the reviewed tests
(policy exhausted over 285,120 situations — the 29 safety properties and
16 witnesses of the rule-engine Relay; box behaviour; XSS on every page for
every persona; every rendered link must be a route the router knows; the
app over HTTP with forged requests), the generated tests, and **the other
direction** — five preserved bad variants that must each FAIL at the stage
named for them (mistyped body, unescaped page, unapproved kernel edit,
kernel without the org wall, description change leaving the body STALE).

## Who plays "the LLM"?

Nobody in particular — that is the point of the split. Any coding agent
(Claude Code, a headless `claude -p`, a cheaper model) gets the brief,
writes `impl/<box>.py`, and is held to the gate. For this prototype the
bodies were written by sub-agents that were **forbidden to read anything
but their brief** — so the descriptions had to carry the whole spec (see
`DEVLOG.md` for how that went: two descriptions were ambiguous, both
ambiguities were caught by reviewed tests, both were fixed in the
contract, and the STALE mechanism forced exactly those two regenerations).

## Mechanical enforcement outside the repo

`REVIEW.lock` proves reviewed code did not change *without* a lock update;
a lock update is one file in the PR diff. In a real setup, protect
`REVIEW.lock` and the reviewed paths with CODEOWNERS / branch protection
(humans approve), and deny agent edits to them in the agent harness
(e.g. Claude Code `permissions.deny` for `Edit(relay/model.py)` etc.).
The current lock is a **bootstrap stamp** (`approved_by: claude-bootstrap
(NOT yet human-reviewed)`) — the human review of `REVIEW.md` is pending.
