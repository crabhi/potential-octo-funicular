# Flowdeck — an end-to-end SaaS application, developed as rules

The developer-experience experiment (research note 14): build a complete
web application — a multi-tenant team kanban — **the way the rule-driven
method prescribes**, journal every step honestly, and see what development
actually feels like. The previous rule-driven services (CMS, tickets,
receivables) proved the engine generalizes; this one adds the missing
pieces of "a real app": a **web UI you can click**, demo data, and an
unedited log of the loop (DEVLOG.md).

```
./check.sh     # tests + static gate + frozen round-2 regression + HTTP replay + app boot
python app.py  # serve it: http://127.0.0.1:8800/ui  (personas switchable in the header)
```

What the application *is*:

```
 TICKETS.md                        the product spec: 7 stakeholder tickets
 rulesets/taskboard/rules.yaml     the program: 18 rules, lifecycle, projections   150 lines
 rulesets/taskboard/safety.yaml    FROZEN gate: 13 ∀-props, 8 ∃-witnesses, 2 gated entries
 rulesets/taskboard/features.yaml  FROZEN gate: 5 scenarios, 36 steps, refusals by name
 app.py                            boots the generic engine + seeds THROUGH the rules
 ────────────────────────────────────────────────────────────────────────────────────
 UI, API, storage, analysis        inherited: ../rule-driven-cms/engine + analysis
```

**Zero lines of Flowdeck-specific UI or handler code exist.** The board
columns are the lifecycle, the cards are the read rule, the buttons are
the decision function (denied ones are greyed and *name their rule*), the
403 banners carry the ticket sentence, and `/ui/rules` renders the
program. `rulesets/taskboard-round2/` preserves the author's real
second-draft bugs; `check.sh` holds it to the frozen gate forever.

The domain concepts Flowdeck forced into the *generic* engine (paid once,
no domain words, reused by every future rule base): per-actor attributes
(`actor_fields: [team]`), relational projections (`actor_matches_field` —
tenancy and assignment as booleans), and `has_`-opt-out for fields no rule
mentions (the situation space is a budget). The UI itself was also built
generically during this episode — the CMS gained a browser UI without
changing a line.

Read the journal: [DEVLOG.md](DEVLOG.md) — four analyzer rounds at ~0.18 s
each; two real authorization holes caught with concrete counterexamples
(S2: a task assigned to "anonymous" hands work to the public; S5: staff
quietly granted the team's work); one containment deny proven dead and
deleted; two probe-placement lessons. Distilled findings:
`research/14-developer-experience.md`. Screenshots: `docs/slides/img/`
(regenerate with `screenshots.py`; needs `pip install playwright` and a
Chromium).
