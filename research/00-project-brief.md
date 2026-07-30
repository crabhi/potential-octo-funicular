# Project brief: formal proofs guiding LLM agents on code

Status: living document. Update when scope changes.
Created: 2026-07-30

## Goal

Build a workflow where formal methods constrain and guide LLM coding agents
working on a web application, so the agent can autonomously optimize code
(e.g. for performance) while provably staying within developer-defined
invariants.

## System model (simplified, agreed with developer)

- The application exposes a **web API**.
- Future application state depends **only** on:
  1. API requests (possibly concurrent), and
  2. database migrations performed by the developer,
  which may run **while requests are being served**.
- Serializing everything is **not acceptable** in the target system.
  However, it is fine to start with a serializable model and extend to
  concurrency later (refinement path matters when choosing tools).

## Intended workflow

1. Developer states invariants in natural language.
2. LLM translates them into a formal language; developer reviews.
3. A reasoning engine can be **queried for contradictions or unexpected
   outcomes** of the invariant set (before any code exists).
4. The formal requirements are used to **verify actual system behavior**
   (model checking, runtime/trace verification, model-based testing,
   or code-level proofs).
5. The agent then optimizes code autonomously against an objective function
   (performance, cost, ...) with the formal constraints as hard boundaries.

## Constraints & preferences

- Implementation languages: Python, Rust, Java or Go preferred; deviation OK.
- A specialized proof/spec language is acceptable.
- Use sub-agents with weaker models for research/execution where possible.
- Notes live in `research/`; `research/INDEX.md` is the index. Update often —
  the project runs across a long time span.

## Milestones

- [x] M1: survey tools & approaches (research notes)
- [ ] M2: agree on approaches with developer
- [ ] M3: small prototypes for agreed approaches
- [ ] M4: end-to-end loop (invariants -> spec -> check -> agent optimization)
