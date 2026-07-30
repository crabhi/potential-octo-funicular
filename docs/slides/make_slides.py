#!/usr/bin/env python3
"""Generate the project slide deck (PDF, 16:9 landscape).

Audience: engineers without prior formal-verification background.
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
    c.drawString(40, 20, "Formal proofs as guardrails for LLM agents · 2026-07-30")
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


def panel_titled(x, y, w_, h_, title, body, tcolor=ACCENT_D, size=11.5,
                 tsize=12.5):
    panel(x, y, w_, h_)
    c.setFont(FB, tsize)
    c.setFillColor(tcolor)
    c.drawString(x + 14, y + h_ - 24, title)
    text_block(x + 14, y + h_ - 42, body, size=size, width=w_ - 28)


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
c.drawString(70, 244, "A workflow for developing large-scale systems when agents write the code")
c.setFont(F, 12)
c.drawString(70, 160, "Research review — approaches, evidence from three prototypes, and a roadmap")
c.drawString(70, 142, "July 2026")
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
               "Economics: formal specs used to be written in addition to code, by the same scarce experts. "
               "With LLMs, translation into formal language is assisted, counterexamples are consumed by a tireless agent, "
               "and one spec is amortized over unbounded regenerations of the code.",
               size=12.5, width=560, color=MUTED)
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
header("The workflow", "Three roles, one contract")
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
    (670, H - 305, 250, 70, "4 · Design model-checked",
     "Concurrent requests + migration explored exhaustively at small size. (P1)"),
    (355, H - 305, 250, 70, "5 · Bound to the real system",
     "Spec-derived tests drive the real API + database. (P3)"),
    (40, H - 305, 250, 70, "6 · Agents optimize freely",
     "Any edit that keeps every gate green ships. Counterexamples come back as repair tasks. (P4)"),
]
for x, yy, w_, h_, t, b in steps:
    panel(x, yy - h_, w_, h_)
    c.setFont(FB, 11.5)
    c.setFillColor(INK)
    c.drawString(x + 12, yy - 20, t)
    text_block(x + 12, yy - 36, b, size = 9.8, width=w_ - 24, color=MUTED)
arrow(292, H - 245, 353, H - 245)
arrow(607, H - 245, 668, H - 245)
arrow(795, H - 282, 795, H - 303)
arrow(668, H - 340, 607, H - 340)
arrow(353, H - 340, 292, H - 340)
y = text_block(40, 128,
               "The contract: the spec is frozen for the agent — code edits can never weaken the gate; changing the spec is a human "
               "ceremony. Objectives (speed, cost) are optimized only inside the region the spec allows. The agent may make the system "
               "faster any way it likes; it may not make it wrong.", size=12, width=880, color=ACCENT_D)
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
header("Approaches surveyed", "Three ways to put a formal fence around an agent")
cols = [
    ("A · Design-first", OK,
     "Model the design (requests, migration steps) in a spec language; "
     "model-check it. Bind spec to code with generated tests.",
     ["Covers whole-system concurrency — where the hard bugs live",
      "Cheapest; counterexamples are readable stories",
      "Weak spot: model and code can drift apart"]),
    ("B · Proof-carrying code", MUTED,
     "Write the implementation in a verification-aware language (Dafny, "
     "Rust+Verus); proofs live inside the code and re-verify on every edit.",
     ["Strongest per-function guarantees; best-studied LLM+verifier combo (68–86% benchmark success)",
      "Weak spot: the database sits outside the verified boundary",
      "Locks the implementation language; slow verify cycles"]),
    ("C · Hybrid, layered  ← chosen", ACCENT_D,
     "A's design model + a typed, plain-English-reviewable invariant layer "
     "on top + selective code proofs only where optimization is riskiest.",
     ["Each layer covers the gaps of the one below",
      "Team learns gradually: English rules first, models later, proofs last",
      "Every stage pays for itself before the next is needed"]),
]
x = 40
for t, col, lead, bl in cols:
    panel(x, 90, 285, 350)
    c.setFont(FB, 13.5)
    c.setFillColor(col)
    c.drawString(x + 14, 414, t)
    yy = text_block(x + 14, 392, lead, size=11, width=257)
    bullets(x + 14, yy - 10, bl, 257, size=10.5, gap=7, dot_color=col)
    x += 305
footer(); c.showPage()

# ----------------------------------------------------------------- slide 7
header("Evidence 1 · design level", "The checker beat us — twice")
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
           "OSS tools' docs. After the fixes: 30,000 random traces clean, and Apalache verifies all executions up to 12 steps.",
           size=12, width=880, color=ACCENT_D)
text_block(40, 148,
           "This is the workflow working as designed: the human states three one-line invariants; the machine finds the "
           "non-obvious consequences of the protocol.", size=12, width=880, font=FI, color=MUTED)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 8
header("Evidence 2 · rule level", "Asking the logic engine: do my rules even make sense?")
text_block(40, H - 108,
           "Before any model or code exists, the invariant set itself can be interrogated (prototype P2: a small CLI over the "
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
     "The same query later gates agent edits."),
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
text_block(40, 92, "Each verdict is also emitted as JSON — the machine-readable half of the future agent loop.",
           size=11.5, width=880, color=MUTED, font=FI)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 9
header("Evidence 3 · real system", "The same invariant, enforced against real Postgres")
text_block(40, H - 108,
           "Prototype P3: a real Rust API (two versions running side by side), a real Postgres database, the real five-step "
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
    "Design-level proof (P1) and real-system evidence (P3) now tell the same story about the same invariants.",
], 880, size=12, gap=8)
footer(); c.showPage()

# ------------------------------------------------------- CMS example 1 of 3
header("Worked example · a CMS", "Ten security rules everyone recognizes")
text_block(40, H - 108,
           "The same workflow on a familiar domain: a content management system with user roles, draft articles, "
           "a review/publish lifecycle, and public access. Requirements start as stakeholder sentences in tickets:",
           size=12.5, width=880)
rules_ex = [
    ("inv_draft_visibility", "“A draft is visible only to its author, editors, and admins.”"),
    ("inv_publish_staff_only", "“Only editors and admins may publish.”"),
    ("inv_anonymous_published_only", "“Anonymous visitors can read published articles and nothing else.”"),
    ("inv_deactivated_does_nothing", "“A deactivated account can neither edit nor publish anything.”"),
    ("inv_archived_not_public", "“Archived articles are not publicly accessible.”"),
]
yy = H - 168
for nm, sent in rules_ex:
    panel(40, yy - 40, 620, 40)
    c.setFont("Courier-Bold", 10)
    c.setFillColor(ACCENT_D)
    c.drawString(52, yy - 18, nm)
    c.setFont(FI, 10.5)
    c.setFillColor(INK)
    c.drawString(52, yy - 33, sent)
    yy -= 48
panel(690, yy + 8, 230, 232)
c.setFont(FB, 12); c.setFillColor(ACCENT_D); c.drawString(704, yy + 216, "Lifecycle")
tx = yy + 192
for st in ["draft", "in review", "published", "archived"]:
    c.setFont(FB, 11); c.setFillColor(INK)
    c.drawString(724, tx, st)
    if st != "archived":
        arrow(714, tx - 6, 714, tx - 22)
    c.setFillColor(ACCENT)
    c.circle(714, tx + 3, 3, fill=1, stroke=0)
    tx -= 34
text_block(704, tx + 6, "Roles: anonymous, author, editor, admin — plus admin actions (demote, deactivate) that can fire at any moment.",
           size=9.5, width=202, color=MUTED)
text_block(40, yy - 16,
           "Each sentence becomes one typed rule (LLM-drafted, reviewed next to the original). The rule NAMES travel "
           "through every later stage — oracle verdicts, model invariants, and the app's 403 responses all cite them.",
           size=12, width=620, color=ACCENT_D)
footer(); c.showPage()

# ------------------------------------------------------- CMS example 2 of 3
header("Worked example · a CMS", "The oracle at code-review time")
panel(40, 250, 430, 160)
c.setFont(FB, 12.5); c.setFillColor(WARN); c.drawString(54, 386, "Two tickets collide")
chip(360, 382, "IMPOSSIBLE", color=WARN)
text_block(54, 364,
           "Security files SEC-482: “sessions expire within 15 minutes” (SOC2). Editorial UX files "
           "CMS-1201: “sessions last at least an hour.” Both get translated and merged. The solver "
           "flags the set as unsatisfiable and the unsat core names exactly those two rules — out of "
           "twelve — before any session code exists.", size=10.8, width=402)
panel(490, 250, 430, 160)
c.setFont(FB, 12.5); c.setFillColor(WARN); c.drawString(504, 386, "A rule silently kills a feature")
chip(818, 382, "INVALID", color=WARN)
text_block(504, 364,
           "Legal adds LEG-77: “unpublished material is accessible only to the person who wrote it.” "
           "Nothing contradicts — the set stays CONSISTENT. But query the claim “an editor can view "
           "someone else's draft” → INVALID: under the combined rules, review-before-publish is dead. "
           "Every individual rule looks reasonable; the solver sees the consequence.", size=10.8, width=402)
text_block(40, 214,
           "Both answers arrive at review time, from a query — not from a production incident or a bug report three sprints later.",
           size=12.5, width=880, color=ACCENT_D)
text_block(40, 168,
           "This is the project's “query the invariants for contradictions and unexpected outcomes” step, running on real files "
           "in the repo: examples/cms/invariants/.", size=11.5, width=880, color=MUTED, font=FI)
footer(); c.showPage()

# ------------------------------------------------------- CMS example 3 of 3
header("Worked example · a CMS", "The checker finds the stale-session race")
text_block(40, H - 108,
           "Single-state rules can't see time. The model adds it: sessions cache the user's role at login; admin "
           "actions (demote, deactivate) run concurrently. One constant selects the design — and only one survives:",
           size=12.5, width=880)
panel(40, 280, 430, 130, fill=HexColor("#E9F1EC"))
c.setFont(FB, 12.5); c.setFillColor(OK); c.drawString(54, 386, "cms_live — re-check on every action")
text_block(54, 364, "20,000 simulated traces clean; Apalache verifies all executions to depth 10. "
           "Authorization at time of use is safe by construction.", size=10.8, width=402)
panel(490, 280, 430, 130, fill=HexColor("#F6E8E1"))
c.setFont(FB, 12.5); c.setFillColor(WARN); c.drawString(504, 386, "cms_cached — trust the session snapshot")
text_block(504, 364,
           "Counterexample in under a second: an author logs in, the admin deactivates the account, "
           "the still-open session submits content anyway. Other seeds: a demoted editor still publishes.",
           size=10.8, width=402)
y = bullets(40, 250, [
    "The same check-then-act bug class the migration prototype caught in real Postgres — here it is authorization (stale JWT / cached claims), found by the checker before any code.",
    "The demo app (examples/cms/app, Rust) makes the knob real: AUTH_MODE=live passes the full policy suite; AUTH_MODE=cached reproduces the model's counterexample over actual HTTP.",
    "Every 403 names the violated rule (inv_publish_staff_only, ...) — counterexamples stay machine-readable from solver to model to running server.",
], 880, size=12, gap=8)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 10
header("Novelty", "What's new here")
y = bullets(40, H - 120, [
    "No mainstream agent tooling gates edits on a formal checker today — “spec-driven development” products use prose specs. The gap between research verifier-loops and agent products is exactly where this sits.",
    "Two-layer specs: plain-English-reviewable typed rules on top (reliable LLM translation, human review), a temporal model underneath (real concurrency reasoning). Combines the only two approaches with strong evidence.",
    "First formal treatment (that we found) of app-level dual-write migration choreography — both P1 counterexamples are absent from the literature and from the OSS tools' documentation.",
    "Spec-as-fence, not spec-as-target: most verified-codegen work generates correct code once. Here the spec fences an autonomously evolving system — the agent optimizes an objective inside a frozen feasible region.",
], 880, size=13.5, gap=14)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 11
header("Adoption & roadmap", "A learnable ramp — each stage pays for itself")
steps2 = [
    ("Stage 1", "Typed invariants on one subsystem. No new language for the team — rules review as English sentences with concrete example states.", OK),
    ("Stage 2", "A design model only where concurrency bites (migrations, caches, queues). Agents write the model; humans read counterexamples.", ACCENT_D),
    ("Stage 3", "Bind spec to reality: generated tests first, operation-history checking second, code-level proofs last and only where hot.", ACCENT_D),
    ("Stage 4", "Agents optimize autonomously behind the gates. Counterexamples, not humans, do the reviewing.", INK),
]
x = 40
for t, b, col in steps2:
    panel(x, 280, 205, 140)
    c.setFont(FB, 12.5)
    c.setFillColor(col)
    c.drawString(x + 14, 396, t)
    text_block(x + 14, 374, b, size=10.4, width=177)
    if x > 40:
        arrow(x - 20, 350, x - 4, 350)
    x += 225
c.setFont(FB, 13)
c.setFillColor(INK)
c.drawString(40, 240, "Next on this project")
bullets(40, 214, [
    "P4 — the closed loop: checker counterexample → LLM repair → recheck, reused at every layer (the one missing piece for milestone 4).",
    "History checking (Jepsen/Elle-style) on P3's recorded operations; multi-statement transactions in P1 to exercise snapshot-isolation write skew against migrations.",
    "Open questions: NL→spec fidelity at scale · trace-first specs (generate instrumentation, don't retrofit) · review UX for temporal counterexamples · module system for many small specs.",
], 880, size=12, gap=8)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 12
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
c.drawString(70, 168, "Repo: research/INDEX.md (all notes) · research/08-workflow-vision.md (this argument, long form)")
c.drawString(70, 148, "Prototypes: p1-migration-model (./check.sh) · p2-invariant-oracle (./demo.sh) · p3-conformance-harness (./run_demo.sh)")
c.drawString(70, 128, "Worked example: examples/cms — the CMS from slides 10-12, every artifact runnable")
footer(title_page=True)
c.showPage()

c.save()
print(f"wrote {OUT} ({page[0]} pages)")
