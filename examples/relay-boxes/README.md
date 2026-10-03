# Relay on boxes — reviewed contracts, generated bodies, Monty sandboxes

Another approach to the same question as the rest of the repository
(*how do humans stay in control of code that LLMs write?*), tried on the
same product: **Relay**, the customer-support helpdesk of
`../helpdesk/` (tickets HD-1…HD-9 in `../helpdesk/TICKETS.md`).

Instead of a rule base that *is* the program, the program is split by
**who reviews it** — and the split is a folder. Within each side, code is
organised by business area, and generated code mirrors reviewed code
module for module:

```
src/relay/                      REVIEWED — a human reads every line of a change
  people.py                     who uses Relay (roles, actors)
  policy.py                     refusals as values, the rule registry
  kernel.py                     the only owner of state; DeskReader, its read-only face
  cases/   model · rules · queues · pages                  HD-1…HD-6
  thread/  model · rules                                   HD-8/9 (comments, evidence)
  mail/    model · intake · gateway                        HD-7 (the mail robot)
  web/     routes · ui · server · seed                     the HTTP front
src/generated/relay/            GENERATED — nobody reads it; the gate holds it
  cases/queues.py  cases/pages.py  mail/intake.py  web/routes.py  web/ui.py
test/relay/...                  reviewed tests, by business area
test/generated/relay/...        generated tests, same mirror
src/boxkit/                     the framework (reviewed once; its own package in real use)
```

`relay.cases.queues` declares the contract `sort_into_queues`; module
`generated.relay.cases.queues` holds its body. A contract module may
declare several boxes (`relay.cases.pages` declares the three case
pages); its generated mirror holds all their bodies and the helpers they
share.

The UI — routing, every view, every HTML template, the stylesheet — is
generated. So is the product logic that is not policy (queue sorting,
interpreting inbound email). None of it can write state, read a file,
reach the network, call a kernel method its contract does not list, or
return a value its reviewed type does not admit.

## Reviewing a change

Review happens in the pull request. `src/generated/` and `test/generated/`
are marked `linguist-generated` in the repository's `.gitattributes`, so
GitHub collapses them in the diff; **what stays expanded is exactly the
code a human reviews.** A PR that touches only generated files changed no
contract, rule or transition — the gate already decided it. A PR that
touches a contract module (e.g. `src/relay/cases/queues.py`) changed a
type or a description: read it; the gate marks the affected bodies STALE
until they are regenerated against it.

## The DSL: plain Python + the mirror convention

```python
# src/relay/kernel.py (REVIEWED)
class DeskReader(Protocol):            # an object capability: the sandbox
    def cases(self) -> list[Case]: ... # can call exactly these methods
    ...

# src/relay/web/ui.py (REVIEWED)
Escape = Callable[[str], str]          # a function capability

# src/relay/cases/queues.py (REVIEWED)
@blackbox
def sort_into_queues(cases: list[Case], today: date) -> list[Queue]:
    """Partition the cases … into the desk's six queues, in this order …
    "SLA breached" is a cross-state view …"""          # the reviewed description
    ...                                                 # no body — ever (linted)
```

```python
# src/generated/relay/cases/queues.py (GENERATED — one header per box pins its contract)
# boxkit: generated implementation of `sort_into_queues` against spec 71cc8e59…
def sort_into_queues(cases: list[Case], today: date) -> list[Queue]:
    ...
```

```python
# src/relay/cases/model.py (REVIEWED) — state transitions are plain data,
# read by plain reviewed code in the kernel; not part of the DSL
CASE_TRANSITIONS: dict[tuple[CaseState, CaseAction], CaseState] = {
    ("new", "triage"): "open",          # HD-3
    ("open", "wait"): "waiting",        # HD-3
    ...
}

# src/relay/cases/rules.py (REVIEWED) — guard rules, the one policy piece boxkit provides

@POLICY.deny("breach_needs_lead", "HD-5: once the SLA is breached …", on=("case",))
def _(s: Situation) -> bool:
    return s.action == "resolve" and s.breached and s.actor.role != "lead"
```

What `boxkit` derives mechanically from a `@blackbox` declaration:

* **the stub** — exactly the reviewed types the box can see (the transitive
  closure of its signature, copied verbatim from the reviewed modules,
  dependencies first) plus a `BoxkitContract_<name>` protocol for its
  signature. The implementer is shown only this (`boxkit brief`); the
  generated module is type-checked against it by
  [ty](https://docs.astral.sh/ty/) *inside Monty*;
* **the spec hash** — over the text of those types, the signature and the
  description; *not* over where they live. Moving a contract to another
  module keeps its body fresh; changing a type the box uses, or its
  description, makes that body (and only that body) **STALE**;
* **the constructors** — the reviewed dataclasses in the closure are the
  only host classes the sandbox can instantiate;
* **the capability surfaces** — `Protocol` parameters become host objects
  whose callable surface is exactly the protocol's methods; `Callable`
  parameters become host functions; every argument the sandbox passes and
  every value that comes back is checked against the reviewed annotation.

## Run it

A uv project (`uv_build`; one wheel ships `relay`, `generated` and `boxkit`).

```bash
./check.sh                                   # everything, both directions (≈1 min)
uv run python -m boxkit check src/relay      # the gate alone
uv run python -m boxkit brief src/relay relay.cases.pages   # what the implementer sees
uv run pytest                                # all tests
uv run relay                                 # serve http://127.0.0.1:8811/
```

`boxkit check` stages: (1) contract modules carry no logic; (2) boundary
lint — nothing reviewed imports `generated`, and every generated module is
the self-contained mirror of a contract module, on an import allowlist;
(3) every box has a body that is present, fresh (spec hash) and
type-correct against its stub. (That every state is reachable and only
tombstones are final is an ordinary reviewed test, `test/relay/test_policy.py`.)

`check.sh` adds the framework's hostile-body tests, a check that the
generated folders are collapsed in PRs, the reviewed tests (policy
exhausted over 285,120 situations — 29 safety properties and 21
witnesses; box behaviour; XSS on every page for every persona; every
rendered link must be a route the router knows; the app over HTTP with
forged requests), the generated tests, **the other direction** — five
preserved bad variants that must each FAIL at the stage named for them
(mistyped body, unescaped page, reviewed code importing generated code,
kernel without the org wall, description change leaving its body STALE)
— and a mutation run: deleting any one of the 29 guard rules must break a
reviewed test.

## Who plays "the LLM"?

Nobody in particular — that is the point of the split. Any coding agent
gets the brief for a contract module, writes its mirror under
`src/generated/`, and is held to the gate. For this prototype the bodies
were written by sub-agents that were **forbidden to read anything but
their brief** — so the descriptions had to carry the whole spec (see
`DEVLOG.md`: two descriptions were ambiguous, both ambiguities were caught
by reviewed tests, both were fixed in the contract, and the STALE
mechanism forced exactly those two regenerations).
