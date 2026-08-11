#!/usr/bin/env python3
"""Generate the project slide deck (PDF, 16:9 landscape).

Audience: engineers without prior formal-verification background.
Regenerated ground-up from the current repository state (see CLAUDE.md
workflow rule: the deck always describes the repo, never accretes).
This edition leads with the rule-driven experiments (examples/
rule-driven-cms, note 13) and shows the developer experience with real
code from the repo; Act I (proofs beside the code) is one evidence slide.
Usage: python3 make_slides.py  ->  formal-guardrails-slides.pdf
"""
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

W, H = 960, 540
INK = HexColor("#1F2A3A")
MUTED = HexColor("#5C6B7E")
ACCENT = HexColor("#1F6F6B")      # teal
ACCENT_D = HexColor("#155250")
WARN = HexColor("#B4552D")        # rust — counterexamples / failures
OK = HexColor("#3A7D44")
PANEL = HexColor("#F1F4F7")
PANEL_LINE = HexColor("#D8DFE7")
WHITE = HexColor("#FFFFFF")

CODE_BG = HexColor("#F4F6F8")     # light code panel (YAML)
CODE_INK = HexColor("#243247")
CODE_DARK_BG = HexColor("#16222F")  # terminal panel
CODE_TXT = HexColor("#D8E2EA")
CODE_OK = HexColor("#8CCB96")
CODE_FAIL = HexColor("#F09A7E")
CODE_DIM = HexColor("#7E93A5")

OUT = "formal-guardrails-slides.pdf"
c = canvas.Canvas(OUT, pagesize=(W, H))
page = [0]

F, FB, FI = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
M, MB = "Courier", "Courier-Bold"


def wrap(text, font, size, width):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if stringWidth(t, font, size) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def text_block(x, y, text, font=F, size=13, width=400, leading=None,
               color=INK):
    leading = leading or size * 1.32
    c.setFont(font, size)
    c.setFillColor(color)
    for ln in wrap(text, font, size, width):
        c.drawString(x, y, ln)
        y -= leading
    return y


def footer(title_page=False):
    page[0] += 1
    if title_page:
        return
    c.setFont(F, 8.5)
    c.setFillColor(MUTED)
    c.drawString(40, 20, "Formal guardrails for LLM agents · rules as the program · 2026-08-11")
    c.drawRightString(W - 40, 20, str(page[0]))


def header(kicker, title):
    c.setFillColor(ACCENT)
    c.rect(0, H - 8, W, 8, fill=1, stroke=0)
    c.setFont(FB, 10.5)
    c.setFillColor(ACCENT)
    c.drawString(40, H - 46, kicker.upper())
    c.setFont(FB, 25)
    c.setFillColor(INK)
    c.drawString(40, H - 76, title)


def bullets(x, y, items, width, size=13, gap=8, dot_color=ACCENT):
    for it in items:
        c.setFillColor(dot_color)
        c.circle(x + 3, y + size * 0.32, 2.2, fill=1, stroke=0)
        ny = text_block(x + 14, y, it, size=size, width=width - 14)
        y = ny - gap
    return y


def panel(x, y, w_, h_, fill=PANEL, line=PANEL_LINE):
    c.setFillColor(fill)
    c.setStrokeColor(line)
    c.roundRect(x, y, w_, h_, 7, fill=1, stroke=1)


def arrow(x1, y1, x2, y2, color=MUTED, w_=1.4):
    c.setStrokeColor(color)
    c.setLineWidth(w_)
    c.line(x1, y1, x2, y2)
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    for da in (0.45, -0.45):
        c.line(x2, y2, x2 - 8 * math.cos(a + da), y2 - 8 * math.sin(a + da))
    c.setLineWidth(1)


def chip(x, y, txt, color=ACCENT, size=9.5):
    w_ = stringWidth(txt, FB, size) + 14
    c.setFillColor(color)
    c.roundRect(x, y, w_, 16, 8, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont(FB, size)
    c.drawString(x + 7, y + 4.5, txt)
    return x + w_


def code_block(x, top, w_, lines, size=8.6, dark=False):
    """Monospace code panel. `lines` are strings or (text, style) tuples;
    styles: cmd, ok, fail, dim, add, del. Returns the bottom y."""
    lh = size * 1.42
    pad = 12
    h_ = 2 * pad + lh * len(lines)
    panel(x, top - h_, w_, h_, fill=(CODE_DARK_BG if dark else CODE_BG))
    light = {"": CODE_INK, "dim": MUTED, "ok": OK, "fail": WARN,
             "add": OK, "del": WARN, "cmd": ACCENT_D}
    darkc = {"": CODE_TXT, "dim": CODE_DIM, "ok": CODE_OK, "fail": CODE_FAIL,
             "add": CODE_OK, "del": CODE_FAIL, "cmd": WHITE}
    colors = darkc if dark else light
    yy = top - pad - size
    for ln in lines:
        text, style = ln if isinstance(ln, tuple) else (ln, "")
        c.setFont(MB if style in ("cmd", "fail") else M, size)
        c.setFillColor(colors[style])
        c.drawString(x + pad, yy, text)
        yy -= lh
    return top - h_


def box(x, y, w_, h_, title, body, title_color=ACCENT_D, body_size=8.6,
        fill=PANEL):
    panel(x, y, w_, h_, fill=fill)
    c.setFont(FB, 9.5)
    c.setFillColor(title_color)
    c.drawString(x + 10, y + h_ - 16, title)
    text_block(x + 10, y + h_ - 29, body, size=body_size, width=w_ - 20,
               color=INK)


# ----------------------------------------------------------------- slide 1
c.setFillColor(INK)
c.rect(0, 0, W, H, fill=1, stroke=0)
c.setFillColor(ACCENT)
c.rect(0, 118, W, 5, fill=1, stroke=0)
c.setFillColor(WHITE)
c.setFont(FB, 34)
c.drawString(70, 340, "The rule base is the program")
c.setFont(FB, 21)
c.setFillColor(HexColor("#7FB5B2"))
c.drawString(70, 305, "formal guardrails for LLM agents, act II")
c.setFont(F, 15)
c.setFillColor(HexColor("#AFC3CF"))
c.drawString(70, 258, "Three services — a CMS, a ticket desk, a receivables tracker — written as rules,")
c.drawString(70, 236, "served by one domain-free engine, with a solver reviewing every change.")
c.setFont(F, 12)
c.drawString(70, 168, "Research review with code: the developer experience, two sabotage episodes, one domain transfer —")
c.drawString(70, 150, "and act I (proofs beside the code) in a single slide. August 2026.")
c.setFont(F, 11)
c.setFillColor(HexColor("#7E93A3"))
c.drawString(70, 88, "No formal-methods background assumed — the four concepts you need are on slide 3.")
footer(title_page=True)
c.showPage()

# ----------------------------------------------------------------- slide 2
header("Why this project", "Agents now out-write our ability to check")
y = bullets(40, H - 120, [
    "LLM agents produce code faster than humans can meaningfully review it. Human attention is the bottleneck — and it samples, it does not cover.",
    "Tests also sample: they check the runs you thought of. The bugs that matter live in the interactions you did not think of.",
    "If we want agents (and background jobs, and time) to act autonomously, we need a way to say what must never break — and have a machine enforce it.",
], 560, size=14, gap=12)
panel(640, H - 300, 280, 190)
c.setFont(FB, 12.5)
c.setFillColor(ACCENT_D)
c.drawString(654, H - 134, "The proposal")
text_block(654, H - 156,
           "The developer writes down intent as rules and invariants. Agents "
           "write the rest. Reasoning engines sit between them and arbitrate: "
           "every change must provably keep the rules.", size=11.5, width=252)
text_block(654, H - 250,
           "Code becomes cheap to regenerate. The spec becomes the durable asset.",
           font=FI, size=11.5, width=252, color=ACCENT_D)
y = text_block(40, 180,
               "Setting: a regular web SaaS application — CRUD/API handlers, authorization, tenancy, workflows, background "
               "jobs. Not kernels, crypto, or avionics: every technique here is judged against ordinary product teams, CI "
               "budgets, and mainstream languages at the edges.",
               size=12.5, width=880, color=MUTED)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 3
header("Background in four words", "All the formal methods you need today")
data = [
    ("Invariant", "A sentence about the system that must be true at every "
     "moment. Example: “a user never sees another user's data.” You already "
     "write these — in comments, runbooks and post-mortems. Here they "
     "become machine-checkable."),
    ("Model", "A small, faithful board-game version of your system: its "
     "states and legal moves. In act II the “model” is not beside the "
     "system — the rule base IS both the model and the running program."),
    ("Checker", "A tireless adversary (here: the Z3 solver). It considers "
     "every situation the rules allow — thousands you would never test — "
     "hunting for one that breaks an invariant."),
    ("Counterexample", "The checker's proof of failure: the exact situation "
     "that breaks the rule, with the rule that allowed it named. Not "
     "“something is wrong” but “an editor who authored this article can "
     "publish it, via editor_decide.”"),
]
xs, ys_ = [40, 500], [H - 108, H - 300]
for i, (t, b) in enumerate(data):
    x, yy = xs[i % 2], ys_[i // 2]
    panel(x, yy - 172, 420, 172)
    c.setFont(FB, 15)
    c.setFillColor(ACCENT_D if i != 3 else WARN)
    c.drawString(x + 16, yy - 28, t)
    text_block(x + 16, yy - 50, b, size=11.5, width=388)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 4
header("Act I in one slide (2026-07 → 08-06)", "Proofs beside the code: it works — and it has a tax")
acts = [
    ("2 protocols falsified, then proven",
     "P1: the model checker beat a careful engineer twice on an online DB "
     "migration (drain guard, IS-NULL backfill). Version 3 survived — and was "
     "later proven inductively, for any system size, and live (tracks I, J, M)."),
    ("59 anomalies per run",
     "P3: skip the guard against real Postgres under concurrent load and the "
     "model's predicted anomaly appears 59×/run; 0 with the proven choreography. "
     "The invariant is load-bearing, not decorative."),
    ("1 round to the full fix",
     "P4: same bug, same model, same generic prompt — a stronger frozen gate "
     "turned a partial fix into the full fix. Invest in gate strength, not "
     "prompt steering."),
    ("3.94× faster, never wrong",
     "P5: an agent optimized the CMS freely inside the frozen gate; two "
     "correctness-breaking “optimizations” were absorbed mechanically. "
     "Counterexamples, not humans, did the reviewing."),
    ("Proofs at five levels",
     "Inductive invariants, parameterized (machine-inferred by UPDR), liveness "
     "under fairness, noninterference via self-composition, and a Dafny proof "
     "of real session code (tracks I–M)."),
    ("The residual tax",
     "Every result above polices the model↔code boundary: MBT, trace "
     "validation, extraction fidelity. Act II removes that boundary for the "
     "ruled part of the system."),
]
for i, (t, b) in enumerate(acts):
    x = [40, 490][i % 2]
    yy = (H - 100) - (i // 2) * 102
    panel(x, yy - 94, 430, 94, fill=PANEL if i < 5 else HexColor("#F6E8E1"))
    c.setFont(FB, 11.5)
    c.setFillColor(ACCENT_D if i < 5 else WARN)
    c.drawString(x + 14, yy - 19, t)
    text_block(x + 14, yy - 35, b, size=9.6, width=402)
y = text_block(40, 118,
               "Language scouting closed the loop (notes 11–12): F* is not the SaaS rule language; of five ways proofs can "
               "meet code, “verified engine + small analyzable DSL” — Cedar's shape — ranked first. Act II builds exactly that.",
               size=11.5, width=880, color=ACCENT_D)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 5
header("Act II · the reframing", "“Is formal methods even the right framing?”")
y = text_block(40, H - 104,
               "The developer's question, verbatim: all the examples model one facet of a system. If a human builds a "
               "full web service from the ground up — maybe formal methods is not the right framing. How about "
               "rule-based systems?", size=12, width=430, color=INK)
y = bullets(40, y - 14, [
    "Rule engines (OPS5, CLIPS, Drools, DMN) ran real businesses — and died of interaction opacity: at 10³ rules nobody could ask “does any rule ever let X happen?”. That question is exactly an SMT workload.",
    "Formal methods stall on the opposite problem: the spec and the code are two artifacts, and they drift. Executable rules remove the seam — there is only one artifact for the domain.",
], 430, size=10.8, gap=8)
# --- diagram, right column ---
panel(560, 340, 280, 52, fill=HexColor("#E9F1EC"))
c.setFont(FB, 11)
c.setFillColor(ACCENT_D)
c.drawString(576, 368, "rules.yaml — THE PROGRAM")
c.setFont(F, 9)
c.setFillColor(INK)
c.drawString(576, 353, "roles · lifecycle · allow/deny rules · assumptions")
arrow(640, 338, 590, 310)
arrow(760, 338, 810, 310)
box(480, 220, 210, 88, "engine/  (generic, serve)",
    "every request: lifecycle legality -> rule decision -> act. "
    "Refusals are 403s that NAME the rule.")
box(710, 220, 210, 88, "analysis/  (Z3, review)",
    "every change: dead rules, safety (EVERY situation), possibility "
    "(SOME), lifecycle, feature runs.")
c.setFont(FI, 8.5)
c.setFillColor(MUTED)
c.drawCentredString(660, 206, "one condition grammar, two backends — agreement checked exhaustively")
panel(560, 130, 280, 50, fill=HexColor("#F6E8E1"))
c.setFont(FB, 10.5)
c.setFillColor(WARN)
c.drawString(576, 158, "gate: safety + features — FROZEN")
c.setFont(F, 9)
c.setFillColor(INK)
c.drawString(576, 143, "agents edit rules; the gate they answer to is pinned")
arrow(880, 182, 880, 218)
y = text_block(40, 96,
               "The synthesis (note 13): rules are the programming surface · the solver is the reviewer · proof effort "
               "concentrates on the once-proven engine (Cedar's shape, note 12 pattern 1). Time, relations and computation "
               "still escalate up the assurance ladder.", size=11.5, width=880, color=ACCENT_D)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 6
header("Developer experience · writing the app", "A feature is a rule, not a handler")
text_block(40, H - 100,
           "The whole CMS is one reviewable file: lifecycle plus fourteen allow/deny rules, each carrying the stakeholder "
           "sentence it translates. There are no handlers to write — endpoints exist because the lifecycle says so.",
           size=12, width=880)
code_block(40, 398, 430, [
    ("# rulesets/cms/rules.yaml — the CMS (130 lines)", "dim"),
    "lifecycle:",
    "  transitions:",
    "    - {action: submit,  from: draft,     to: in_review}",
    "    - {action: publish, from: in_review, to: published}",
    "    - {action: archive, from: published, to: archived}",
    "",
    "- id: no_self_decision",
    '  description: "Nobody may publish or reject an',
    "    article they authored themselves — separation",
    '    of duties, with no exception for admins."',
    "  effect: deny",
    "  when: 'action in [\"publish\", \"reject\"]",
    "         and actor.is_author'",
])
code_block(490, 398, 430, [
    ("$ curl -sX POST $CMS/articles/7/publish -H 'X-User: ed'", "cmd"),
    ("HTTP/1.1 403 Forbidden", "fail"),
    "{",
    '  "error": "forbidden",',
    ('  "denied_by": "no_self_decision",', "ok"),
    '  "description": "Nobody may publish or reject an',
    '                  article they authored themselves…",',
    '  "situation": {"role": "editor", "action": "publish",',
    '                "is_author": true, "state": "in_review"}',
    "}",
], dark=True)
bullets(40, 150, [
    "One vocabulary end to end: the ticket sentence, the rule id, the solver's finding, and the 403 body all say no_self_decision.",
    "Deny beats allow, silence means deny (Cedar/XACML semantics, stated once) — so admins are denied too: policy, not privilege, decides.",
], 880, size=11, gap=6)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 7
header("Developer experience · the gate", "What must never happen — and what must keep working")
text_block(40, H - 100,
           "The gate is two YAML files, frozen for agents. Safety quantifies over EVERY situation the rules allow; "
           "possibility demands witnesses (a “fix” that makes the system safely do nothing fails); features are frozen "
           "scenarios whose refusals are expected by name.", size=12, width=880)
code_block(40, 386, 430, [
    ("# safety.yaml — FROZEN for agents editing rules", "dim"),
    "safety:",
    "  - id: S2_separation_of_duties",
    "    requires: 'implies(action == \"publish\",",
    "                       not actor.is_author)'",
    ("possibility:            # the anti-“does nothing” half", "dim"),
    "  - id: P2_review_by_non_author",
    "    witness: 'action == \"read\" and not actor.is_author",
    "              and resource.state == \"in_review\"'",
    "lifecycle:",
    "  only_into: {published: [publish]}",
    "",
    ("# features.yaml — refusals expected BY NAME", "dim"),
    "- {actor: ed,   action: publish,",
    "   expect: deny,  denied_by: no_self_decision}",
    "- {actor: erin, action: publish,",
    "   expect: allow, state_after: published}",
])
code_block(490, 386, 430, [
    ("$ python -m analysis.analyze rulesets/cms", "cmd"),
    "rules: 14 (5 deny, 9 allow) | situations: 8640",
    "-- dead rules --",
    ("   ok: all 14 rules are effectual", "ok"),
    "-- assumptions --",
    ("   ok: creating roles are all assumable authors", "ok"),
    "-- safety: must hold in EVERY allowed situation --",
    ("   ok  S1 … S9   (9 properties)", "ok"),
    "-- possibility: must hold in SOME situation --",
    ("   ok  P2_review_by_non_author", "ok"),
    "       witness: {role: editor, action: read, …}",
    "-- lifecycle --",
    ("   ok: 6 transitions live, gated entries respected", "ok"),
    "-- feature runs (frozen scenarios) --",
    ("   ok  5 features (34 steps)", "ok"),
    ("VERDICT: PASS (0 findings)", "ok"),
], dark=True)
bullets(40, 118, [
    "This runs in CI on every rule change, in seconds. Merging a rule diff means: no dead rules, every safety property proven over all situations, every workflow still alive, every scenario still passing.",
], 880, size=11, gap=6)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 8
header("Concepts · the gate", "The gate: frozen acceptance criteria, not the rules")
text_block(40, H - 100,
           "The gate is what any version of the rule base must pass to count as correct. Agents edit rules.yaml freely; "
           "the gate they answer to is pinned somewhere they cannot reach.",
           size=12, width=880)
code_block(40, 398, 880, [
    ("# the same intent, twice — on purpose:", "dim"),
    "rules.yaml    - id: no_self_decision          effect: deny      # enforced: refuses requests, at runtime",
    "safety.yaml   - id: S2_separation_of_duties   requires: 'implies(action == \"publish\", not actor.is_author)'",
    ("                                                                # verified: EVERY situation, at review time", "dim"),
])
gate_cards = [
    ("Deliberate redundancy", ACCENT_D,
     "The rule is enforcement — the server refuses the request. The gate property is verification — the solver proves "
     "no allowed situation violates it. Delete the rule (the sabotage episode does) and the property catches it, with "
     "the concrete situation and the rule that now wrongly grants it."),
    ("Both directions, always", WARN,
     "Safety alone is gameable: a rule base that denies everything passes every “never happens” property vacuously. So "
     "the gate pairs safety with possibility witnesses and frozen feature runs. strict_privacy broke NO safety property "
     "— it failed possibility P2 and two features."),
    ("Frozen mechanically, ratchets upward", ACCENT_D,
     "analyze <edited-rules> --gate <pinned-dir>: the criteria live in a directory the editor cannot touch. Changing "
     "the gate is a human ceremony, and it only grows — each counterexample becomes a permanent item. Otherwise an "
     "optimizing agent weakens the check instead of fixing the rules (guardrail 1)."),
    ("Verdicts, not opinions", ACCENT_D,
     "PASS means mergeable — nothing else to review for the ruled part. FAIL means named findings — a dead rule, a "
     "situation plus the granting rule, the blocking deny, the failing feature step — routed back to whoever edited."),
]
for i, (t, col, b) in enumerate(gate_cards):
    x = [40, 490][i % 2]
    yy = 316 - (i // 2) * 100
    panel(x, yy - 92, 430, 92)
    c.setFont(FB, 10.5)
    c.setFillColor(col)
    c.drawString(x + 14, yy - 18, t)
    text_block(x + 14, yy - 33, b, size=9.2, width=402)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 9
header("Concepts · why rules at all", "“Couldn't the gate hold ordinary code?” It can — at a price")
text_block(40, H - 100,
           "The gate's strength is not free-standing — it depends on what the program is made of. Same gate sentence, two programs:",
           size=12, width=880)
c.setFont(FB, 11.5)
c.setFillColor(OK)
c.drawString(40, H - 126, "The program is rules  (act II)")
c.setFillColor(WARN)
c.drawString(490, H - 126, "The program is free code  (act I — P4/P5)")
versus = [
    ("A ∀-check is a proof.", "S2 holds in all 8,640 situations, decided in ~2 s — the rule "
     "language is deliberately too weak to be undecidable.",
     "∀ becomes sampling.", "“No situation exists where…” is undecidable for code (Rice). You get "
     "property tests — P3: 735 requests, 0 errors — evidence, not proof; or per-change code proofs "
     "(track L, extraction-fidelity gap)."),
    ("No seam.", "The analyzer and the server evaluate the SAME parsed rules — backend agreement "
     "checked exhaustively. The gate examines the program, not a model of it.",
     "The seam returns.", "Checked artifact ≠ executed artifact: MBT, trace validation, conformance "
     "harnesses — half of act I polices that boundary."),
    ("Bounded edit surface.", "Agents edit only the rule base; the engine consults it on every "
     "request; the language cannot express a bypass or a side door. The analyzer interprets 100% of "
     "the editable artifact.",
     "Unbounded artifact.", "Code can be wrong in ways no gate item mentions — a new endpoint, a "
     "leaking cache, a bypassed check. Act I needed boundary lint and Grant<Op> compile-error "
     "tokens just to police this."),
    ("Findings name causes.", "Dead rules, blocking denies, granting rules — the repair loop "
     "consumes rule interactions directly.",
     "Findings name symptoms.", "A failing test points at behavior; the cause is yours to find."),
]
yy = H - 138
for lt, lb, rt, rb_ in versus:
    for x, t, b in ((40, lt, lb), (490, rt, rb_)):
        panel(x, yy - 64, 430, 64)
        c.setFont(FB, 9.8)
        c.setFillColor(OK if x == 40 else WARN)
        c.drawString(x + 12, yy - 16, t)
        text_block(x + 12, yy - 29, b, size=8.4, width=406)
    yy -= 70
text_block(40, yy - 6,
           "The quiet dependency: the gate is WRITTEN in the rule vocabulary — its properties quantify over situations "
           "that exist because the rule base declares them. Define a gate for free code and you end up specifying half "
           "a rule language anyway, just without executing it.",
           size=9.6, width=880, color=ACCENT_D)
text_block(40, yy - 40,
           "The honest flip side: where behavior is computation — migrations, fuzzy matching, performance — rules can't "
           "express it, and the repo does exactly this: free code under a gate, paying the difference in harnesses, "
           "lints and proofs. That is the escalation ladder.",
           size=9.6, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 10
header("Developer experience · a bad edit cannot hide", "Two plausible edits, seven named findings")
text_block(40, H - 100,
           "Sabotage episode 1: two locally-reasonable edits, held to the frozen gate (--gate points at the pinned copy).",
           size=12, width=880)
code_block(40, 412, 880, [
    ("# edit 1: legal adds a privacy rule (LEG-77)          # edit 2: separation of duties removed", "dim"),
    ("+ - id: strict_privacy", "add"),
    ("+   effect: deny", "add"),
    ("+   when: 'action == \"read\" and resource.state != \"published\" and not actor.is_author'", "add"),
    ("- - id: no_self_decision                              # “admins found it annoying”", "del"),
])
code_block(40, 316, 880, [
    ("$ python -m analysis.analyze rulesets/cms-buggy --gate rulesets/cms", "cmd"),
    ("FAIL DEAD allow rule 'editor_read_all': it never grants anything", "fail"),
    "     (overridden where it overlaps: deny_inactive, strict_privacy)",
    ("FAIL S2_separation_of_duties", "fail"),
    "     counterexample: {role: editor, action: publish, is_author: true, state: in_review, …}",
    "     allowed by: editor_decide",
    ("FAIL P2_review_by_non_author: IMPOSSIBLE — blocked by deny rule(s): strict_privacy", "fail"),
    ("FAIL feat_publish_lifecycle: step 4 (ed read): expected allow, got deny (rule: strict_privacy)", "fail"),
    ("VERDICT: FAIL (7 findings)", "fail"),
], dark=True)
bullets(40, 138, [
    "Four different detectors fire at once: the dead-rule check catches the silent masking that rotted 1980s rule bases; ∀-safety catches the removed deny with a concrete situation and the granting rule named; ∃-possibility catches the workflow the new deny killed — the classic safety-only blind spot; and the frozen features catch both, by name.",
], 880, size=11, gap=6)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 11
header("Episode · background processing", "A background job is just another actor")
text_block(40, H - 100,
           "Ticket SYND-9: import published articles from publisher feeds, nightly. The importer gets no back door — it is "
           "an unprivileged HTTP client (role importer), so everything interesting about it is policy:",
           size=12, width=880)
code_block(40, 384, 430, [
    ("# the pipeline cannot skip provenance…", "dim"),
    "- id: import_needs_provenance",
    "  effect: deny",
    "  when: 'actor.role == \"importer\"",
    "         and action == \"create\"",
    "         and not resource.has_source'",
    "",
    ("# …and a stolen importer credential is contained:", "dim"),
    "- id: importer_scope",
    "  effect: deny",
    "  when: 'actor.role == \"importer\"",
    "         and action not in [\"create\", \"read\",",
    "                             \"submit\"]'",
])
code_block(490, 384, 430, [
    ("$ analyze rulesets/cms-import-naive --gate rulesets/cms", "cmd"),
    ("  # the obvious draft: syndicate straight to published", "dim"),
    ("  # (“the publisher already reviewed it”)", "dim"),
    ("FAIL role 'importer' can create items, but the", "fail"),
    "     assumptions say it can never be an author —",
    "     stale assumption: analysis would silently",
    "     skip every importer-authored situation",
    ("FAIL lifecycle: 'syndicate' (draft -> published)", "fail"),
    "     enters 'published'; gate allows only ['publish']",
    ("FAIL S8_imports_have_provenance  (+S9, +feature)", "fail"),
    ("VERDICT: FAIL (5 findings)", "fail"),
], dark=True)
bullets(40, 148, [
    "Falsifier RB1 (tickets land as rule diffs): held — engine/ untouched; the change was 1 role, 1 field, 3 rules, 2 clients.",
    "The episode forced two new generic gate kinds: stale-assumption detection (the silent-unsoundness class) and gated lifecycle entries — review cannot be skirted by inventing a new transition into published.",
], 880, size=11, gap=6)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 12
header("Episode · domain transfer", "Same engine, different world: money you are owed")
text_block(40, H - 100,
           "The transferability test, from the ticket: “the user describes the amount they're owed, the approximate payer "
           "name or exact payment reference, and the due date; the system provides a dashboard and email notifications "
           "about overdue payments; bank transaction emails settle claims.”", size=12, width=880, color=MUTED)
code_block(40, 372, 430, [
    ("projections:            # time enters the vocabulary", "dim"),
    "  - {name: is_past_due, kind: date_passed,",
    "     field: due_date}",
    "",
    ("# the ticket sentence, as a rule:", "dim"),
    "- id: claim_needs_identification",
    "  effect: deny",
    "  when: 'action == \"create\"",
    "         and not (resource.has_payer_name",
    "                  or resource.has_reference)'",
    "",
    ("# even the clock bot obeys the calendar:", "dim"),
    "- id: no_premature_overdue",
    "  effect: deny",
    "  when: 'action == \"mark_overdue\"",
    "         and not resource.is_past_due'",
])
split = [
    ("290 lines of YAML — the domain", OK,
     "Money truth only from the bank feed (admins bounce off only_feed_settles), "
     "absolute tenant isolation, append-only ledger, calendar law: 13 rules, 10 "
     "safety + 7 possibility properties, all solver-checked."),
    ("~100 generic engine lines — the transfer cost", ACCENT_D,
     "One missing concept: TIME. Declared date projections + an engine clock "
     "(--today, /__clock test seam), multi-source transitions (settle from "
     "awaiting AND overdue), a feature-file clock (advance_days)."),
    ("Client-side, correctly — the projection boundary", WARN,
     "Email parsing, the fuzzy matching itself (exact reference, else normalized "
     "payer name + exact amount), reminder dedup, cron. Cross-item and "
     "approximate: beyond any per-situation vocabulary."),
]
yy = 372
for t, col, b in split:
    panel(490, yy - 84, 430, 84)
    c.setFont(FB, 10.5)
    c.setFillColor(col)
    c.drawString(504, yy - 18, t)
    text_block(504, yy - 33, b, size=9.2, width=402)
    yy -= 92
bullets(40, 96, [
    "The transfer worked and its cost is measurable — and conceptual, not volumetric: the engine was missing time, not receivables.",
], 880, size=11, gap=6)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 13
header("Developer experience · two days in production", "The demo transcript, verbatim")
code_block(40, 420, 880, [
    ("$ python receivables_demo.py                              (engine clock: 2026-08-11)", "cmd"),
    "-- users register what they are owed --",
    ("   ok  rita's dashboard shows exactly her 3 claims (uma's is invisible)", "ok"),
    "-- day 1: the bank's transaction emails arrive --",
    ("   ok  matched by approximate name (JOHN SMITH) and exact reference (INV-2026-001)", "ok"),
    ("   ok  the stranger's transfer is held for manual review, settles nothing", "ok"),
    "-- day 1: the overdue sweeper runs (it attempts EVERY awaiting claim) --",
    ("   ok  every attempt refused by name: [(3, 'no_premature_overdue'), (4, …)]", "ok"),
    "-- 30 days pass (clock -> 2026-09-10); the sweeper runs again --",
    ("   ok  claim 3 (due 08-15) is overdue; uma's (due 09-30) is protected", "ok"),
    "        reminder -> rita@example.com: Payment overdue: EUR 500.00 (due 2026-08-15)",
    "-- day 2: the late payment finally lands --",
    ("   ok  ACME S.R.O. matches the overdue claim 3; settle succeeds", "ok"),
    ("   ok  even the admin cannot fake money truth: 403 only_feed_settles", "ok"),
    ("VERDICT: PASS", "ok"),
], dark=True)
bullets(40, 150, [
    "The sweeper is deliberately dumb — it tries everything, and the rules hold the clock accountable, not vice versa. A buggy (or compromised) bot is bounded by policy the solver already checked over every situation.",
    "Late payments land because possibility W2 (“settle from overdue exists”) is part of the frozen gate — liveness guarded the design before the demo existed.",
], 880, size=11, gap=6)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 14
header("Scoreboard", "Three services, one engine, every claim executable")
stats = [
    ("3 : 1", "services per engine — CMS, tickets, receivables on 1,097 lines "
     "of domain-free Python (grep-provable: zero domain words outside docstrings).", ACCENT_D),
    ("313 : 1,097", "lines of YAML that ARE the CMS vs the shared generic "
     "engine+analyzer. Receivables: 290. Tickets: 100.", ACCENT_D),
    ("36,096", "situations checked exhaustively — runtime evaluation and the "
     "Z3 compilation agree on every one (8,640 + 576 + 26,880).", OK),
    ("12", "named findings across two sabotaged rule bases (7 + 5); zero "
     "false passes; every finding carries a rule name or a concrete situation.", WARN),
]
x = 40
for n, b, col in stats:
    panel(x, 280, 205, 120)
    c.setFont(FB, 24)
    c.setFillColor(col)
    c.drawString(x + 14, 358, n)
    text_block(x + 14, 338, b, size=9.0, width=178)
    x += 225
c.setFont(FB, 12)
c.setFillColor(ACCENT_D)
c.drawString(40, 250, "What the analyzer asks of every rule-base change (seconds, in CI):")
bullets(40, 226, [
    "Is any rule dead — does removing it change no decision? (rule rot, reversed: two redundant guards were proven useless and deleted)",
    "Do the safety properties hold in EVERY allowed situation? If not: the situation + the granting rule.",
    "Is every workflow still POSSIBLE? If not: the blocking deny, found by re-checking without each deny.",
], 430, size=10, gap=6)
bullets(490, 226, [
    "Are the assumptions consistent with the rules? (every creating role must be an assumable author)",
    "Is the lifecycle live and are gated states entered only through their gate (only_into)?",
    "Do the frozen feature scenarios still run — with every expected refusal denied by the right rule?",
], 430, size=10, gap=6)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 15
header("Where it stops", "Kept deliberately sharp")
rows = [
    ("The projection boundary", "Rules see finite booleans (is_author, has_source, is_past_due). Fuzzy matching, "
     "cross-item invariants (“no two claims with one reference”, “≤3 published per author”) live in clients today — "
     "properly in store constraints (P9: the invariant→Postgres compiler that doesn't exist yet, anywhere)."),
    ("No time-interleaving", "Single-situation rules can't see races: the demoted author who is still is_author, the "
     "stale session. That is rung 2's job — the Quint temporal twin (falsifier RB4) stays on the ladder."),
    ("The clock is a trust root (RB6)", "is_past_due is only as true as the engine's date. The analyzer proves “overdue "
     "only when past due” relative to the projection; a skewed clock breaks it silently. The temporal twin should model skew."),
    ("One entity per rule base", "Receivables dodged it (transactions live with the bank; only claims are ruled). "
     "Linked ruled entities — invoice↔payment↔dunning — need N rule bases plus client joins, or engine work on relations."),
    ("The engine is unproven Python", "Fine for research; the production form is a verified engine — Cedar's Lean proofs, "
     "or our own track-D Dafny→Go shape — so trust rests on one proof plus per-change analysis."),
]
yy = H - 104
for t, b in rows:
    panel(40, yy - 62, 880, 62)
    c.setFont(FB, 11)
    c.setFillColor(ACCENT_D)
    c.drawString(54, yy - 18, t)
    text_block(54, yy - 33, b, size=9.4, width=845)
    yy -= 68
footer(); c.showPage()

# ---------------------------------------------------------------- slide 16
header("Guardrails · CLAUDE.md", "What we learned the hard way — now enforced")
gr = [
    ("The spec is frozen for agents", "Enforced mechanically — the analyzer takes --gate from a pinned directory; agents edit rules, never the gate. Same contract as act I's frozen invariants."),
    ("Gates need both directions", "Safety-only gates accept fixes that trade away liveness (“the safest system does nothing”). Every gate here = safety + possibility witnesses + frozen feature runs."),
    ("Gate strength beats NL steering", "Same bug, model, prompt: the stronger gate turned a partial fix into the full fix (P4). Cheaper models are fine when the gate is strong."),
    ("Escalate to proofs", "Rules (this deck) < temporal models < inductive < parameterized < liveness < hyperproperties. Climb only when the ticket needs time, relations, or computation."),
    ("Translate / validate split", "LLM translation of NL→rules is unsound — always followed by a sound solver step. Humans review rules sentence-by-sentence, never agent edits."),
    ("Counterexamples are the currency", "Machine-readable and named: unsat blockers, situation witnesses, denied_by 403s. One vocabulary from ticket to runtime error."),
    ("Verify sub-agent claims", "The checker corrected the author repeatedly (two “correct” protocols, two “needed” rules). Dead ends and falsified predictions are recorded in the notes."),
    ("Boundaries by construction", "Bots are ordinary actors with no back door; capability tokens make bypass a compile error (track G). Typestate over discipline."),
]
xs2, yw = [40, 500], 420
yy0 = H - 108
for i, (t, b) in enumerate(gr):
    x = xs2[i % 2]
    yy = yy0 - (i // 2) * 96
    panel(x, yy - 88, yw, 88)
    c.setFont(FB, 11.5)
    c.setFillColor(ACCENT_D)
    c.drawString(x + 14, yy - 20, f"{i + 1} · {t}")
    text_block(x + 14, yy - 36, b, size=9.6, width=yw - 28)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 17
header("Roadmap", "Falsifiers on the table")
c.setFont(FB, 13)
c.setFillColor(OK)
c.drawString(40, H - 110, "Held so far")
bullets(40, H - 134, [
    "RB1 (tickets land as rule diffs, engine untouched): held twice — imports cost zero engine lines; the receivables transfer cost ~100 generic lines for one missing concept (time). Prediction: gate-language growth flattens as new domains reuse projections, only_into, the assumption check.",
    "Act I stands underneath: the migration protocol and CMS model remain proven at five levels (tracks I–M); the P4/P5 loop is the template for RB5.",
], 880, size=10.5, gap=6)
c.setFont(FB, 13)
c.setFillColor(ACCENT_D)
c.drawString(40, H - 250, "Next")
bullets(40, H - 274, [
    "RB3 — the LLM fidelity episode: same tickets, ticket→rule-diff vs ticket→handler-code; measure human corrections needed. The bet: declarative diffs review better.",
    "RB5 — agent repair: hand an agent the sabotaged rule bases under the frozen gate; expect ≤2 rounds (P4's result, cheaper, because diffs are rules).",
    "RB4 — the temporal twin in Quint: the demoted-author race and clock skew that per-situation rules provably cannot see.",
    "RB2 — scale: exhaustive backend agreement is 26,880 situations (~80 s) for receivables; per-condition projected enumeration or symbolic equivalence when it hurts. P8 — the same rules as Cedar policies (verified engine, symbolic analysis). P9 — the invariant→Postgres-constraint compiler nobody has built.",
], 880, size=10.5, gap=6)
c.setFont(FB, 12)
c.setFillColor(MUTED)
c.drawString(40, 108, "Parked (consciously, with reasons recorded)")
text_block(40, 90,
           "Alloy (Z3 covers it) · Quint→Rust codegen (no tooling) · Kani until unbounded domains arrive · Verus (proxy-blocked; Dafny stands in).",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 18
c.setFillColor(INK)
c.rect(0, 0, W, H, fill=1, stroke=0)
c.setFillColor(ACCENT)
c.rect(0, H - 8, W, 8, fill=1, stroke=0)
c.setFont(FB, 26)
c.setFillColor(WHITE)
c.drawString(70, 400, "The one-sentence takeaway")
c.setFont(F, 17)
c.setFillColor(HexColor("#D7E2E9"))
for i, ln in enumerate([
    "The developer writes the rules and the gate; the solver reviews every change;",
    "agents, bots, and time do their worst inside the fence.",
    "For the ruled part of the system there is no code to review — only a rule diff and a verdict.",
]):
    c.drawString(70, 350 - i * 28, ln)
c.setFont(F, 11.5)
c.setFillColor(HexColor("#8FA5B5"))
c.drawString(70, 200, "Try it: examples/rule-driven-cms/check.sh — tests + 5 analyses + 5 live demos, one command")
c.drawString(70, 180, "Read it: research/13-rule-based-cms.md (the framing + both episodes) · research/INDEX.md (all notes)")
c.drawString(70, 160, "Act I evidence: research/09, 10, 12 · prototypes p1–p7 · examples/cms (the spec-beside-code twin)")
footer(title_page=True)
c.showPage()

c.save()
print(f"wrote {OUT} ({page[0]} pages)")
