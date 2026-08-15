# Clearance — the manual's worked example

A miniature expense-claims service (four roles, six-state lifecycle,
org walls, receipt discipline, four-eyes approval, frozen payment
records) built as one rule base on the generic engine in
`../rule-driven-cms/`.

This example exists to be read alongside **`docs/manual.md`**, which
builds it line by line — the tickets (`TICKETS.md`), the rules
(`rulesets/approvals/rules.yaml`, 10 rules), the frozen gate both
directions (`safety.yaml`: 10 ∀-properties + 4 witnesses + gated
lifecycle entries; `features.yaml`: 29 steps with refusals expected by
name), and the preserved round-1 draft (`rulesets/approvals-round1/`)
whose four-eyes rule is provably DEAD — the gate must keep catching it
(`./check.sh` stage 2 requires the FAIL).

```bash
./check.sh    # gate PASS, round-1 draft FAIL, features over real HTTP
```

3,456 situations; analyzer verdict PASS (0 findings). Numbers and
transcripts quoted in the manual come from this directory.
