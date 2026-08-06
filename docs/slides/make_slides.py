#!/usr/bin/env python3
"""Generate the project slide deck (PDF, 16:9 landscape).

Audience: engineers without prior formal-verification background.
Regenerated ground-up from the current repository state (see CLAUDE.md
workflow rule: the deck always describes the repo, never accretes).
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

OUT = "formal-guardrails-slides.pdf"
c = canvas.Canvas(OUT, pagesize=(W, H))
page = [0]

F, FB, FI = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


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
    c.drawString(40, 20, "Formal proofs as guardrails for LLM agents · 2026-08-06")
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


# ----------------------------------------------------------------- slide 1
c.setFillColor(INK)
c.rect(0, 0, W, H, fill=1, stroke=0)
c.setFillColor(ACCENT)
c.rect(0, 118, W, 5, fill=1, stroke=0)
c.setFillColor(WHITE)
c.setFont(FB, 34)
c.drawString(70, 330, "Formal proofs as guardrails")
c.drawString(70, 288, "for LLM coding agents")
c.setFont(F, 15.5)
c.setFillColor(HexColor("#AFC3CF"))
c.drawString(70, 244, "Invariants as the durable artifact of a regular web SaaS application —")
c.drawString(70, 222, "agents write the code, reasoning engines hold it to the rules")
c.setFont(F, 12)
c.drawString(70, 160, "Research review — workflow, evidence from 7 prototypes and 13 tracks, proofs at every level")
c.drawString(70, 142, "August 2026")
c.setFont(F, 11)
c.setFillColor(HexColor("#7E93A3"))
c.drawString(70, 88, "No formal-methods background assumed — the four concepts you need are on slide 3.")
footer(title_page=True)
c.showPage()

# ----------------------------------------------------------------- slide 2
header("Why this project", "Agents now out-write our ability to check")
y = bullets(40, H - 120, [
    "LLM agents produce code faster than humans can meaningfully review it. Human attention is the bottleneck — and it samples, it does not cover.",
    "Tests also sample: they check the runs you thought of. Concurrency bugs live precisely in the interleavings you did not think of.",
    "If we want agents to optimize systems autonomously (performance, cost), we need a way to say what must never break — and have a machine enforce it.",
], 560, size=14, gap=12)
panel(640, H - 300, 280, 190)
c.setFont(FB, 12.5)
c.setFillColor(ACCENT_D)
c.drawString(654, H - 134, "The proposal")
text_block(654, H - 156,
           "The developer writes down intent as invariants. Agents write and "
           "rewrite the code. Reasoning engines sit between them and arbitrate: "
           "every change must provably keep the invariants.", size=11.5, width=252)
text_block(654, H - 252,
           "Code becomes cheap to regenerate. The spec becomes the durable asset.",
           font=FI, size=11.5, width=252, color=ACCENT_D)
y = text_block(40, 180,
               "Setting: a regular web SaaS application — CRUD/API handlers, authorization, tenancy, schema migrations "
               "running under live traffic. Not kernels, crypto, or avionics: every tool below is judged against ordinary "
               "product teams, CI budgets, and mainstream languages at the edges.",
               size=12.5, width=880, color=MUTED)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 3
header("Background in four words", "All the formal methods you need today")
data = [
    ("Invariant", "A sentence about the system that must be true at every "
     "moment. Example: “no request ever reads a database column that has "
     "been dropped.” You already write these — in comments, runbooks and "
     "post-mortems. Here they become machine-checkable."),
    ("Model", "A small, faithful board-game version of your system: its "
     "states and legal moves (a request commits, a migration step runs). "
     "Small enough to explore, faithful enough that its bugs are your bugs."),
    ("Checker", "A tireless adversary. It plays every possible ordering of "
     "moves against the model — millions of interleavings you would never "
     "think to test — hunting for one that breaks an invariant."),
    ("Counterexample", "The checker's proof of failure: the exact move list "
     "that breaks the invariant. Not “something is wrong” but "
     "“this sequence of 9 steps ends with a stale read.” Perfect "
     "food for an LLM to repair against."),
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
header("The workflow", "Three roles, one contract — every stage now built and exercised")
lanes = [("DEVELOPER", "owns intent", 40), ("LLM AGENTS", "own implementation", 355),
         ("REASONING ENGINES", "arbitrate", 670)]
for t, s, x in lanes:
    c.setFont(FB, 11)
    c.setFillColor(ACCENT)
    c.drawString(x, H - 108, t)
    c.setFont(FI, 10)
    c.setFillColor(MUTED)
    c.drawString(x, H - 122, s)
steps = [
    (40, H - 210, 250, 70, "1 · Invariants in English",
     "“During a migration, both app versions must read correct data.”"),
    (355, H - 210, 250, 70, "2 · Translated to formal rules",
     "LLM drafts; developer reviews each rule against the original sentence."),
    (670, H - 210, 250, 70, "3 · Sanity-checked",
     "Do the rules contradict? Are any vacuous? What surprising states do they allow? (P2)"),
    (670, H - 305, 250, 70, "4 · Design checked & PROVEN",
     "Bounded checking first, then inductive / parameterized / liveness proofs. (P1, P6, P7)"),
    (355, H - 305, 250, 70, "5 · Bound to the real system",
     "Spec-derived tests, model-based testing, trace validation, code proofs. (P3, tracks B–D, L)"),
    (40, H - 305, 250, 70, "6 · Agents repair & optimize",
     "Any edit that keeps every gate green ships. Counterexamples come back as repair tasks. (P4, P5)"),
]
for x, yy, w_, h_, t, b in steps:
    panel(x, yy - h_, w_, h_)
    c.setFont(FB, 11.5)
    c.setFillColor(INK)
    c.drawString(x + 12, yy - 20, t)
    text_block(x + 12, yy - 36, b, size=9.8, width=w_ - 24, color=MUTED)
arrow(292, H - 245, 353, H - 245)
arrow(607, H - 245, 668, H - 245)
arrow(795, H - 282, 795, H - 303)
arrow(668, H - 340, 607, H - 340)
arrow(353, H - 340, 292, H - 340)
y = text_block(40, 128,
               "The contract: the spec is frozen for the agent — enforced mechanically (the harness diffs the frozen region, "
               "reverts, and fails the round), never by convention or prompt. Objectives (speed, cost) are optimized only "
               "inside the region the spec allows. The agent may make the system faster any way it likes; it may not make it wrong.",
               size=12, width=880, color=ACCENT_D)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 5
header("Case study", "Changing the database schema while serving traffic")
text_block(40, H - 110,
           "Why this problem: it is ubiquitous at scale, genuinely concurrent, and formally treated exactly once in the "
           "literature (Google F1, 2013). The popular open-source migration tools ship no correctness argument at all.",
           size=12.5, width=880)
stages = [("EXPAND", "add new column,\ninvisible to reads"),
          ("DUAL-WRITE", "every write fills\nold + new column"),
          ("BACKFILL", "copy old rows\nin batches"),
          ("SWITCH READS", "reads now served\nfrom new column"),
          ("CONTRACT", "drop the old\ncolumn")]
x = 40
for i, (t, b) in enumerate(stages):
    panel(x, H - 270, 160, 92, fill=HexColor("#E8F0EF") if i != 4 else HexColor("#F6E8E1"))
    c.setFont(FB, 11.5)
    c.setFillColor(ACCENT_D if i != 4 else WARN)
    c.drawString(x + 12, H - 202, t)
    yy = H - 222
    for ln in b.split("\n"):
        c.setFont(F, 10)
        c.setFillColor(INK)
        c.drawString(x + 12, yy, ln)
        yy -= 13
    if i < 4:
        arrow(x + 160, H - 224, x + 176, H - 224)
    x += 176
y = bullets(40, H - 310, [
    "Meanwhile: two versions of the application run side by side (rolling deploy). Version 1 has never heard of the new column.",
    "Meanwhile: user requests read and write the same rows the migration is copying — under snapshot isolation, so everyone sees a consistent-looking snapshot and conflicts surface only at commit.",
    "One protocol mistake in the choreography and some user reads return stale data — silently.",
], 880, size=12.5, gap=8)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 6
header("Evidence · design level (P1)", "The checker beat us — twice")
text_block(40, H - 108,
           "We wrote the migration protocol as a small model (Quint) with three one-line invariants, believing each version "
           "correct. Random simulation found counterexamples in under a second; symbolic checking confirmed them.",
           size=12.5, width=880)
panel(40, 224, 430, 166, fill=HexColor("#F6E8E1"))
c.setFont(FB, 12.5); c.setFillColor(WARN); c.drawString(54, 366, "Bug #1 — the drain guard was in the wrong place")
text_block(54, 344,
           "Rule as written: “backfill may not start until every app instance runs v2.” "
           "Counterexample: dual-writes alone fill the new column, so the read switch fires "
           "with no backfill at all — while a v1 instance still lives. It writes the old column "
           "afterwards; a v2 user reads stale data.", size=10.8, width=402)
text_block(54, 252, "Fix: the drain must gate the read switch too, not just the backfill.",
           font=FB, size=10.8, width=402, color=INK)
panel(490, 224, 430, 166, fill=HexColor("#F6E8E1"))
c.setFont(FB, 12.5); c.setFillColor(WARN); c.drawString(504, 366, "Bug #2 — the textbook backfill query is wrong")
text_block(504, 344,
           "Every guide says: backfill WHERE new_column IS NULL. Counterexample: during the "
           "rolling window a v2 instance dual-writes a row (new column now non-NULL), then a "
           "surviving v1 instance overwrites the old column only. The row is non-NULL but stale — "
           "and IS NULL never revisits it. The staleness survives to the switch.", size=10.8, width=402)
text_block(504, 244, "Fix: backfill WHERE new IS DISTINCT FROM old; switch when all rows agree.",
           font=FB, size=10.8, width=402, color=INK)
text_block(40, 196,
           "Both are real production failure modes of app-level dual-write migrations — and neither is in the literature or the "
           "OSS tools' docs. After the fixes: 30,000 random traces clean, Apalache verifies to 12 steps — and the protocol "
           "is now PROVEN at every depth and every system size (slide 12).",
           size=12, width=880, color=ACCENT_D)
text_block(40, 148,
           "This is the workflow working as designed: the human states three one-line invariants; the machine finds the "
           "non-obvious consequences of the protocol.", size=12, width=880, font=FI, color=MUTED)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 7
header("Evidence · rule level (P2)", "Asking the logic engine: do my rules even make sense?")
text_block(40, H - 108,
           "Before any model or code exists, the invariant set itself can be interrogated (P2: a small CLI over the "
           "Z3 solver; rules are typed and plain enough to review sentence-by-sentence).",
           size=12.5, width=880)
rows = [
    ("“Do any rules contradict?”", "IMPOSSIBLE", WARN,
     "Two developers add “at most one app version at a time” and “at least two during rolling "
     "deploys.” The solver returns the minimal conflicting pair — by name — out of the whole rule set."),
    ("“What states do the rules allow?”", "SATISFIABLE", MUTED,
     "Enumerated example states reveal a forgotten guard: “dropping the column while an old binary "
     "still runs” was allowed. Nobody wrote a wrong rule — one rule was missing. The witness shows it."),
    ("“Does my claim follow from the rules?”", "VALID / INVALID", OK,
     "“Contract never starts while v1 runs” → VALID: the rules entail it, no test suite needed. "
     "The same query gates agent edits in P4/P5 today."),
]
yy = H - 160
for q, verdict, col, b in rows:
    panel(40, yy - 82, 880, 82)
    c.setFont(FB, 12)
    c.setFillColor(INK)
    c.drawString(54, yy - 22, q)
    chip(700, yy - 26, verdict, color=col)
    text_block(54, yy - 42, b, size=10.8, width=800)
    yy -= 94
text_block(40, 92, "Each verdict is also emitted as JSON — the machine-readable half of the agent loop, now closed (slide 10).",
           size=11.5, width=880, color=MUTED, font=FI)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 8
header("Evidence · real system (P3)", "The same invariant, enforced against real Postgres")
text_block(40, H - 108,
           "P3: a real Rust API (two versions running side by side), a real Postgres database, the real five-step "
           "migration — exercised by generated concurrent traffic while the migration runs (Hypothesis test harness).",
           size=12.5, width=880)
stats = [("735", "concurrent requests across all migration phases", OK),
         ("0", "errors with the proven choreography", OK),
         ("59", "“column does not exist” errors per run when the drain step is deliberately skipped", WARN),
         ("1", "genuine race found in the ‘modern’ instance itself (and fixed)", WARN)]
x = 40
for n, b, col in stats:
    panel(x, 260, 205, 120)
    c.setFont(FB, 30)
    c.setFillColor(col)
    c.drawString(x + 16, 336, n)
    text_block(x + 16, 314, b, size=10.2, width=175, color=INK)
    x += 225
y = bullets(40, 230, [
    "The deliberately-broken run reproduces exactly the anomaly the model predicted — the formal invariant is load-bearing, not decorative.",
    "Bonus find: a check-then-act race — the app reads migration flags, then executes SQL a moment later; a contract commit in that gap 500s a fully-migrated instance. The class of bug that survives code review and unit tests.",
    "Design-level proof (P1) and real-system evidence (P3) tell the same story about the same invariants.",
], 880, size=12, gap=8)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 9
header("Worked example · a CMS", "Ten security rules, one knob, every artifact runnable")
text_block(40, H - 108,
           "The same workflow on a familiar domain (examples/cms): roles, draft articles, a review/publish lifecycle, "
           "public access. Stakeholder sentences become named, typed rules; the names travel from tickets to solver "
           "verdicts to model invariants to the app's 403 bodies.",
           size=12.5, width=880)
panel(40, 230, 430, 150, fill=HexColor("#E9F1EC"))
c.setFont(FB, 12.5); c.setFillColor(OK); c.drawString(54, 356, "cms_live — re-check auth on every action")
text_block(54, 334,
           "20,000 simulated traces clean; Apalache verifies to depth 10; the safety invariant is INDUCTIVE with almost "
           "no strengthening — check-at-use is structurally the right design, and now that's a theorem (Track I). "
           "Policy suite over real HTTP: 5/5.", size=10.8, width=402)
panel(490, 230, 430, 150, fill=HexColor("#F6E8E1"))
c.setFont(FB, 12.5); c.setFillColor(WARN); c.drawString(504, 356, "cms_cached — trust the session snapshot")
text_block(504, 334,
           "Counterexample in under a second: author logs in, admin deactivates the account, the still-open session "
           "publishes anyway (stale JWT / cached claims). The same invariant provably has NO inductive proof here "
           "(concrete CTI). Replayed on the real app: 2/2 stale-token violations reproduced over HTTP.",
           size=10.8, width=402)
y = bullets(40, 200, [
    "The rule oracle caught cross-ticket conflicts before any code: SEC-482 vs CMS-1201 (session length) flagged IMPOSSIBLE with the two rule names in the unsat core; LEG-77 silently killing review-before-publish flagged INVALID.",
    "Gates need BOTH directions: the happy-path feature test passes in both configurations — features don't catch the race, safety doesn't catch a feature dying. Every gate = safety + feature runs/witnesses.",
], 880, size=11.5, gap=7)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 10
header("The agent loop closed (P4)", "Same bug, same model, same prompt — the gate decides")
text_block(40, H - 108,
           "P4 seeds the historical IS-NULL bug into the migration protocol and lets a headless LLM repair it against the "
           "frozen spec (diffed mechanically, reverted on tamper). Run twice, changing ONLY the gate:",
           size=12.5, width=880)
panel(40, 236, 430, 154, fill=HexColor("#F6E8E1"))
c.setFont(FB, 12.5); c.setFillColor(WARN); c.drawString(54, 366, "Episode 1 — safety-only gate")
text_block(54, 344,
           "Repair in 1 round, invariants untouched, 30k traces + Apalache green — and WRONG in a way the gate "
           "couldn't see: the fix preserves safety by sacrificing completion (a stale row now blocks the switch "
           "forever). The safest system does nothing: a safety-only gate happily accepts it.",
           size=10.8, width=402)
panel(490, 236, 430, 154, fill=HexColor("#E9F1EC"))
c.setFont(FB, 12.5); c.setFillColor(OK); c.drawString(504, 366, "Episode 2 — gate + frozen feature runs & witness")
text_block(504, 344,
           "Only change: adversarial stale-row-recovery run + completion-reachability witness added to the gate. "
           "Same generic prompt, same model: FULL fix in one round (IS-DISTINCT backfill + switch guard), "
           "30k traces + Apalache clean, completion witnessed in 84% of traces.",
           size=10.8, width=402)
y = bullets(40, 206, [
    "The lesson we now enforce as a guardrail: invest in gate strength, not natural-language steering. Weaker/cheaper models are fine when the gate is strong.",
    "Each counterexample becomes a frozen gate item — the gate ratchets, it never regresses.",
], 880, size=12, gap=8)
text_block(40, 120,
           "Boundary by construction (Track G): protected app operations require a Grant<Op> capability token only the "
           "verified kernel can mint — bypassing authorization is now a pinned COMPILE ERROR (E0639/E0308), not a lint or a convention.",
           size=12, width=880, color=ACCENT_D)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 11
header("Autonomous optimization (P5)", "The agent makes it 3.9x faster — and cannot make it wrong")
text_block(40, H - 108,
           "The end-goal demo: an agent maximizes benchmark throughput on the CMS app (seeded with a global Mutex and "
           "fingerprinting-under-lock). The frozen gate: boundary lint + policy suite + race suites + spec-frozen paths "
           "enforced by git. The agent optimizes freely inside the fence.",
           size=12.5, width=880)
stats = [("3.94x", "accepted speedup on the benchmark, all gates green", OK),
         ("2", "correctness-breaking “optimizations” attempted and mechanically absorbed by the gate", WARN),
         ("1", "marginal edit rejected by the improvement threshold", MUTED)]
x = 40
for n, b, col in stats:
    panel(x, 250, 285, 130)
    c.setFont(FB, 28)
    c.setFillColor(col)
    c.drawString(x + 16, 334, n)
    text_block(x + 16, 310, b, size=10.6, width=255, color=INK)
    x += 305
y = bullets(40, 216, [
    "One rejected attempt was identity caching — exactly the stale-auth bug class the model, the code proof, and the race suite all encode. Three independent layers said no.",
    "Counterexamples, not humans, did the reviewing. The developer's only artifact is the spec.",
], 880, size=12, gap=8)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 12
header("Escalation: from tests to theorems", "“Never happens” now means proven — at five levels")
text_block(40, H - 104,
           "Bounded checking says “safe up to k steps at this size.” Phase 3 removed the qualifiers (all PROVEN, tracks I–M):",
           size=12.5, width=880)
rungs = [
    ("Inductive invariants — safe at EVERY depth", "Track I · Quint/Apalache",
     "7-conjunct strengthening for the migration protocol, ~10s to verify; CMS live-mode invariant inductive nearly "
     "for free, cached-mode provably has no such proof (concrete CTI). Strengthening effort is itself a design signal."),
    ("Parameterized — ANY number of keys & instances", "Track J · mypyvy/EPR",
     "Hand invariant verifies in 0.38s; UPDR independently INFERRED a 9-clause proof in 5.7s (machine-found, zero human "
     "strengthening). Negative control: the buggy variant provably has NO universal inductive invariant."),
    ("Liveness under fairness — it always completes", "Track M · TLC + WF",
     "<>(phase=DONE) proven over the complete 623-state graph, even under unbounded write interference — stronger than "
     "predicted. Dropping rollout fairness yields the stalled-deploy lasso: the assumption is necessary, and named."),
    ("Hyperproperties — no information leak", "Track K · self-composition",
     "“Draft contents never influence anonymous observations” relates PAIRS of traces — per-request checks cannot even "
     "state it. Proven inductively on the self-composed CMS; the leaky variant yields a machine-found two-world distinguisher."),
    ("Real code — the app's session/identity state machine", "Track L · Dafny",
     "Freshness, revocation & demotion immediacy proven (14/14 VCs) on logic extracted from main.rs; the cached-stale "
     "behavior is a machine-checked witness; a buggy resolver is rejected. Open gap: extraction fidelity (documented)."),
]
yy = H - 138
for t, tag, b in rungs:
    panel(40, yy - 62, 880, 62)
    c.setFont(FB, 11)
    c.setFillColor(ACCENT_D)
    c.drawString(54, yy - 18, t)
    c.setFont(FB, 9)
    c.setFillColor(MUTED)
    c.drawRightString(905, yy - 18, tag)
    text_block(54, yy - 33, b, size=9.4, width=845)
    yy -= 68
footer(); c.showPage()

# ---------------------------------------------------------------- slide 13
header("The honest question", "What binds the model to the code? A ladder, now fully exercised")
text_block(40, H - 104,
           "Model↔code drift is the classic failure mode of industrial formal methods. Every rung below is implemented "
           "and measured in this repo (tracks B–E, G, L):",
           size=12.5, width=880)
rungs = [
    ("5 · Proofs in / code from the spec", "proof", INK,
     "Dafny authorization kernel proven against all 10 rules, compiled to Go, embedded and demoed (Track D); the app's "
     "session logic proven (Track L); Grant<Op> makes bypass a compile error (Track G). Kani vs exhaustive measured "
     "(Track E): exhaustive wins at 64 points; Kani proves a 2^131-point domain in ~0.1s — adopt when ids/strings enter."),
    ("4 · Trace validation", "strong evidence", ACCENT_D,
     "Real app action logs compile into a generated Quint run: “was this a legal behavior of the model?” The cached-mode "
     "stale-token publish is accepted by the app but refused by the model — conformance violation caught from client-side "
     "logs alone (Track B)."),
    ("3 · Model-based testing", "strong evidence", ACCENT_D,
     "Model-generated traces drive the real API: 240/240 steps at parity across 3 runs; all 6 replayed race "
     "counterexamples rejected by the live app at exactly the predicted step (Track C)."),
    ("2 · Spec-derived tests against the real system", "evidence", ACCENT_D,
     "Migration harness 735 requests / 0 errors; CMS policy suite 5/5; deliberately-broken runs reproduce the model's "
     "predicted anomalies (P3)."),
    ("1 · Shared vocabulary", "traceability", MUTED,
     "One set of invariant names from tickets to rules to model to the app's 403 bodies. Proves nothing alone — makes "
     "every failure traceable to a requirement."),
]
yy = H - 140
for t, tag, col, b in rungs:
    panel(40, yy - 60, 880, 60)
    c.setFont(FB, 10.5)
    c.setFillColor(col)
    c.drawString(54, yy - 17, t)
    chip(780, yy - 21, tag, color=col)
    text_block(54, yy - 31, b, size=9.2, width=710)
    yy -= 66
footer(); c.showPage()

# ---------------------------------------------------------------- slide 14
header("Language scouting", "Is F* the endgame rule language? Verdict: no — but steal two ideas")
text_block(40, H - 104,
           "F* is the purist endpoint of “rules as abstraction”: the type IS the rule (dependent/refinement types, "
           "SMT-checked, Pulse separation logic for concurrency; production-proven in Windows/Linux/Firefox crypto). "
           "Research note 11 evaluates it for our SaaS setting:",
           size=12.5, width=880)
panel(40, 226, 430, 160, fill=HexColor("#F6E8E1"))
c.setFont(FB, 12.5); c.setFillColor(WARN); c.drawString(54, 362, "Why not primary")
bullets(54, 336, [
    "LLM proof automation: ~1/3–1/2 of proofs (Microsoft's own FStarDataSet) vs Dafny's 86%; absent from the 2026 vericoding benchmark entirely.",
    "Extracts to OCaml/C/Rust — no web/SQL/framework story; could only ever be the kernel language, where Dafny already wins.",
    "Failed obligations are Z3 timeouts, not counterexamples — poison for a frozen gate where red must mean “your edit is wrong”.",
], 402, size=9.6, gap=6, dot_color=WARN)
panel(490, 226, 430, 160, fill=HexColor("#E9F1EC"))
c.setFont(FB, 12.5); c.setFillColor(OK); c.drawString(504, 362, "Worth stealing")
bullets(504, 336, [
    "The 3DGen pattern (Microsoft): agents write in a small constrained DSL; a pre-verified toolchain compiles it to provably correct code — ZERO prover calls per feature. Our translate/validate split, shipped.",
    "Effects & indexed types as by-construction boundaries — strictly stronger than our Grant<Op> tokens, if we ever need a richer kernel.",
], 402, size=9.6, gap=6, dot_color=OK)
text_block(40, 196,
           "Falsifiable predictions logged (F1–F3), incl.: a DSL-with-verified-checker loop for tenant isolation beats the "
           "P4 gate on round count with zero per-feature proofs — testable today in our existing stack (P2's Z3 core).",
           size=12, width=880, color=ACCENT_D)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 15
header("Guardrails · CLAUDE.md", "What we learned the hard way — now enforced")
gr = [
    ("The spec is frozen for agents", "Enforced mechanically — diff the frozen region, revert, fail the round. Never by convention or prompt."),
    ("Gates need both directions", "Safety-only gates accept fixes that trade away liveness (“the safest system does nothing”). Every gate = safety + feature runs + proof obligations."),
    ("Gate strength beats NL steering", "Same bug, model, prompt: the stronger gate turned a partial fix into the full fix. Cheaper models are fine when the gate is strong."),
    ("Escalate to proofs", "Bounded < inductive (any depth) < parameterized (any size) < liveness under fairness < hyperproperties via self-composition."),
    ("Translate / validate split", "LLM translation of NL→formal is unsound — always followed by a sound solver step. Humans review specs, never agent edits."),
    ("Counterexamples are the currency", "Machine-readable (ITF JSON, unsat cores, named 403s); one invariant vocabulary from ticket to runtime error."),
    ("Verify sub-agent claims", "The checker corrected the author several times — that is the method working. Dead ends and falsified predictions are recorded."),
    ("Boundaries by construction", "Capability tokens only the verified kernel can mint — a compile error, not a lint. Typestate over discipline."),
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

# ---------------------------------------------------------------- slide 16
header("Roadmap", "What's proven, what's parked, what's next")
c.setFont(FB, 13)
c.setFillColor(OK)
c.drawString(40, H - 110, "Done — 13 tracks, every falsifier tested")
bullets(40, H - 134, [
    "Repair loop (A/F), trace validation (B), model-based testing (C), Dafny→Go kernel (D), Kani spike (E), compile-error boundary (G), gated optimization 3.94x (H).",
    "Proofs: inductive (I), parameterized w/ machine-inferred invariant (J), noninterference (K), real-code session proof (L), liveness under fairness (M). F* scouting (note 11).",
], 880, size=11.5, gap=7)
c.setFont(FB, 13)
c.setFillColor(ACCENT_D)
c.drawString(40, H - 250, "Next")
bullets(40, H - 274, [
    "Track N — refinement mappings: prove serializable refines snapshot isolation, and an app-shaped model refines the abstract one (shrinks the tested residue to “code matches low-level model”).",
    "Track O — verified runtime enforcement: a monitor synthesized from the spec shields effects even over unverified code (the Grant token's dynamic cousin).",
    "F* falsifiers F1–F3 — incl. the 3DGen-shaped experiment: constrained DSL + pre-verified checker, zero per-feature prover calls (doable in the existing stack).",
    "TCB accounting as a first-class artifact — every “proven” names what it trusts (compilers, extraction fidelity, the HTTP layer) and directs the next escalation.",
], 880, size=11.5, gap=7)
c.setFont(FB, 13)
c.setFillColor(MUTED)
c.drawString(40, 128, "Parked (consciously, with reasons recorded)")
text_block(40, 106,
           "Alloy (P2/Z3 covers it) · Quint→Rust codegen (no tooling exists) · Kani for finite kernels (exhaustive is simpler; "
           "adopt when unbounded ids/strings arrive) · Verus (release downloads proxy-blocked; Dafny stands in).",
           size=11, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 17
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
    "Write intent once, formally, with machine help —",
    "then let agents rewrite the code forever,",
    "with a tireless adversary guaranteeing they never make it wrong.",
]):
    c.drawString(70, 350 - i * 28, ln)
c.setFont(F, 11.5)
c.setFillColor(HexColor("#8FA5B5"))
c.drawString(70, 188, "Repo: research/INDEX.md (all notes) · research/09 & 10 (scoreboards with falsifiers) · CLAUDE.md (guardrails)")
c.drawString(70, 168, "Prototypes: p1 check.sh · p2 demo.sh · p3 run_demo.sh · p4 agent loop · p5 optimization loop · p6 mypyvy · p7 TLC")
c.drawString(70, 148, "Worked example: examples/cms — model, app, oracle, MBT, trace validation, noninterference, Dafny kernel; all runnable")
footer(title_page=True)
c.showPage()

c.save()
print(f"wrote {OUT} ({page[0]} pages)")
