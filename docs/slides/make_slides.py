#!/usr/bin/env python3
"""Generate the project slide deck (PDF, 16:9 landscape).

Audience: engineers without prior formal-verification background.
Regenerated ground-up from the current repository state (see CLAUDE.md
workflow rule: the deck always describes the repo, never accretes).
This edition leads with act VI (the field manual): the developer asked
for the best approaches by DX, velocity and safety written up as
teaching manuals — then redirected: they are layers of ONE method, so
one compound manual with the composition first-class. docs/manual.md
is the deliverable; Clearance (examples/approvals/) is its executable
worked example. Acts I–V are compressed to evidence.
Usage: python3 make_slides.py  ->  formal-guardrails-slides.pdf
(needs reportlab + pillow; screenshots come from img/, regenerate with
examples/helpdesk/screenshots.py and examples/taskboard/screenshots.py)
"""
import pathlib

from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

W, H = 960, 540
INK = HexColor("#1F2A3A")
MUTED = HexColor("#5C6B7E")
ACCENT = HexColor("#1F6F6B")      # teal
ACCENT_D = HexColor("#155250")
FREE = HexColor("#6C5CE7")        # violet — the free UI layer / act highlights
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

HERE = pathlib.Path(__file__).resolve().parent
IMG = HERE / "img"
OUT = str(HERE / "formal-guardrails-slides.pdf")
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
    c.drawString(40, 20, "Formal guardrails for LLM agents · the field manual · 2026-08-15")
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


def shot(path, x, y, w_):
    """Draw a screenshot (all are 16:9) at width w_, top anchored at y —
    returns bottom y. Adds a hairline frame."""
    h_ = w_ * 9 / 16
    c.drawImage(ImageReader(str(IMG / path)), x, y - h_, w_, h_)
    c.setStrokeColor(PANEL_LINE)
    c.setLineWidth(1)
    c.rect(x, y - h_, w_, h_, fill=0, stroke=1)
    return y - h_


def image_slide(kicker, title, img, caption, note=None):
    header(kicker, title)
    bottom = shot(img, 160, H - 90, 640)
    y = text_block(40, bottom - 15, caption, size=9.8, width=880,
                   color=ACCENT_D, font=FI, leading=12.4)
    if note:
        text_block(40, y - 1, note, size=8.8, width=880, color=MUTED,
                   leading=11.2)
    footer()
    c.showPage()


# ----------------------------------------------------------------- slide 1
c.setFillColor(INK)
c.rect(0, 0, W, H, fill=1, stroke=0)
c.setFillColor(FREE)
c.rect(0, 118, W, 5, fill=1, stroke=0)
c.setFillColor(WHITE)
c.setFont(FB, 33)
c.drawString(70, 350, "The method, written down")
c.setFont(FB, 20)
c.setFillColor(HexColor("#B3A8FF"))
c.drawString(70, 315, "formal guardrails for LLM agents, act VI: the field manual")
c.setFont(F, 15)
c.setFillColor(HexColor("#AFC3CF"))
c.drawString(70, 264, "docs/manual.md — one compound manual teaching the three layers as one method: rules as the")
c.drawString(70, 242, "program, models before code, the frozen gate + agent loop — with the composition first-class.")
c.setFont(F, 12)
c.drawString(70, 172, "Every transcript is real output; the worked example is a sixth committed service (Clearance) whose")
c.drawString(70, 154, "check.sh must PASS its gate and FAIL its preserved round-1 draft. August 2026.")
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
     "moment. Example: “a customer never sees another organization's "
     "cases.” You already write these — in comments, runbooks and "
     "post-mortems. Here they become machine-checkable."),
    ("Model", "A small, faithful board-game version of your system: its "
     "states and legal moves. In the rule-driven layer the “model” is not "
     "beside the system — the rule base IS both the model and the running "
     "program."),
    ("Checker", "A tireless adversary (Z3, Apalache, TLC). It considers "
     "every situation the rules allow — tens of thousands you would never "
     "test — hunting for one that breaks an invariant."),
    ("Counterexample", "The checker's proof of failure: the exact situation "
     "that breaks the rule, with the rule that allowed it named. Not "
     "“something is wrong” but “an anonymous visitor assigned to a task "
     "can start it, via assignee_moves.”"),
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
header("Act I in one slide (2026-07)", "Proofs beside the code: it works — and it has a tax")
acts = [
    ("2 protocols falsified, then proven",
     "P1: the model checker beat a careful engineer twice on an online DB "
     "migration. Version 3 survived — and was later proven inductively, for "
     "any system size, and live (tracks I, J, M)."),
    ("59 anomalies per run",
     "P3: skip the guard against real Postgres under concurrent load and the "
     "model's predicted anomaly appears 59×/run; 0 with the proven choreography."),
    ("1 round to the full fix",
     "P4: same bug, same model, same generic prompt — a stronger frozen gate "
     "turned a partial fix into the full fix. Gate strength beats prompt "
     "steering."),
    ("3.94× faster, never wrong",
     "P5: an agent optimized the CMS freely inside the frozen gate; two "
     "correctness-breaking “optimizations” were absorbed mechanically."),
    ("Proofs at five levels",
     "Inductive invariants, parameterized (UPDR), liveness under fairness, "
     "noninterference via self-composition, a Dafny proof of real session "
     "code (tracks I–M)."),
    ("The residual tax",
     "Every result above polices the model↔code boundary: MBT, trace "
     "validation, extraction fidelity. Act II removed that boundary for the "
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
               "Language scouting (notes 11–12): of five ways proofs can meet code, “verified engine + small analyzable "
               "DSL” — Cedar's shape — ranked first. Everything after act I builds exactly that.",
               size=11.5, width=880, color=ACCENT_D)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 5
header("Act II in one slide (2026-08-11)", "The rule base is the program; the solver is the reviewer")
y = bullets(40, H - 104, [
    "One artifact: rules.yaml — roles, lifecycle, allow/deny rules with their ticket sentences. The engine serving it is domain-free; refusals are 403s that NAME the rule.",
    "One condition grammar, two backends: the analyzer's Z3 view and the server's runtime view are the same parsed rules — agreement checked exhaustively, so spec↔code drift is closed by construction.",
    "The gate is frozen for agents: safety (EVERY situation) + possibility (SOME — “the safest system does nothing” fails) + feature runs with refusals expected by name + gated lifecycle entries.",
], 520, size=11, gap=8)
code_block(40, y - 4, 520, [
    ("$ analyze rulesets/cms-buggy --gate rulesets/cms   # sabotage", "cmd"),
    ("FAIL DEAD allow rule 'editor_read_all' — silently masked", "fail"),
    ("FAIL S2_separation_of_duties  counterexample + granting rule", "fail"),
    ("FAIL P2_review_by_non_author: IMPOSSIBLE — strict_privacy", "fail"),
    ("VERDICT: FAIL (7 findings)   # 4 detector kinds fire at once", "fail"),
], dark=True)
panel(590, 210, 330, 250)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(604, 436, "Evidence so far (notes 13–14)")
bullets(604, 412, [
    "Sabotaged CMS: 7 named findings; naive import extension: 5.",
    "Background jobs are just actors — a compromised importer is contained by policy, provably.",
    "Domain transfer: receivables cost the engine ~100 generic lines (time); Flowdeck ~60 (relations).",
    "Redundant rules proven dead and deleted: the solver shrinks rule bases, reversing 1980s rule rot.",
], 300, size=9.3, gap=5)
text_block(40, 96,
           "Act III built a full product to measure DX. Act IV freed the UI over a kernel boundary. Act V grew relations "
           "between ruled entities. Act VI — this deck's lead — wrote the whole method down as one manual.",
           size=11.5, width=880, color=ACCENT_D)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 6
header("Act III in one slide (note 14)", "Flowdeck: the loop is fast and honest — the UI was the tension")
rounds = [
    ("1", "typo = named load error; the author's dead-rule prediction FALSIFIED by the solver.", MUTED),
    ("2", "TWO REAL AUTHORIZATION HOLES (right) + two probes naming the wrong deny.", WARN),
    ("3", "containment deny proven DEAD after the fix — deleted; S11 proves it universally.", ACCENT_D),
    ("4", "PASS (0 findings). Tickets → green gate ≈ 1 hour, none of it debugging.", OK),
]
yy = H - 96
for n, b, col in rounds:
    panel(40, yy - 58, 430, 58)
    c.setFont(FB, 16)
    c.setFillColor(col)
    c.drawString(52, yy - 36, n)
    text_block(74, yy - 20, b, size=9.6, width=384)
    yy -= 66
x = 40
for t in ["34,560 situations", "0.18 s / round", "2 real holes", "round-2 draft gated forever"]:
    x = chip(x, yy - 16, t) + 8
code_block(490, H - 96, 430, [
    ("$ analyze rulesets/taskboard      # round 2, 0.18 s", "cmd"),
    ("FAIL S2_no_anonymous_access", "fail"),
    "  counterexample: {role: anonymous, action: start,",
    "   assigned_to_me: true, ...}",
    ("  allowed by: assignee_moves", "ok"),
    ("FAIL S5_assignee_works", "fail"),
    "  counterexample: {role: admin, action: submit,",
    "   assigned_to_me: false, ...}",
    ("  allowed by: admin_oversees", "ok"),
], size=8.2, dark=True)
text_block(490, 266,
           "Interaction bugs, not typos: each rule read fine alone. Nobody "
           "writes the test where a task is assigned to “anonymous”; the "
           "∀-check considers all 34,560 situations and names the granting "
           "rule. Full journal: examples/taskboard/DEVLOG.md.",
           size=9.6, width=430)
text_block(40, 112,
           "Flowdeck's UI was DERIVED from the rule base — zero app code, boards and buttons for free. Great demo, wrong "
           "product surface: a real product's UX is not a reflection of its policy vocabulary. The developer redirected.",
           size=10.5, width=880, color=WARN)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 7
header("Act IV in one slide (note 15)", "The boundary moved into a kernel API; the UI went free")
layers = [
    ("FREE — app.py (hand-written htmx, ~760 lines)", FREE,
     "Queues, badges, toasts, forms, the thread. Agent-authored, restyled at will. Zero policy lives here — so no "
     "review of it can ever be about policy. Its product UX (a cross-state “SLA breached” queue, assign-to-me, "
     "locked-action disclosures) is nothing a reflected UI could invent."),
    ("BOUNDARY — engine/kernel.py (+ the lint that holds it)", ACCENT_D,
     "visible / get / create / act / edit / delete — every call decided by the rule base BEFORE the store is touched; "
     "refusals are typed Denied values naming the rule; decide()/affordances() are pure queries for rendering. Edits "
     "are decided twice (current row AND the row it would become — the tenant-escape edit died here). App code imports "
     "engine.kernel and NOTHING beneath it: analysis.boundary fails CI otherwise, and the preserved bypass_variant/ "
     "must keep FAILING it."),
    ("ANALYZED — rulesets/<app>/ (rules + frozen gate)", OK,
     "The program: allow/deny rules from tickets. Z3 reviews every change: dead rules, ∀-safety, ∃-possibility, "
     "lifecycle, frozen features with refusals by name. Relay round 1: PASS with pre-registered predictions held; "
     "engine domain growth for the 4th domain: 0 lines."),
]
yy = H - 96
for t, col, b in layers:
    ph = 100 if t.startswith("BOUNDARY") else 88
    panel(40, yy - ph, 880, ph)
    c.setFillColor(col)
    c.rect(40, yy - ph, 6, ph, fill=1, stroke=0)
    c.setFont(FB, 11.5)
    c.setFillColor(col)
    c.drawString(58, yy - 20, t)
    text_block(58, yy - 36, b, size=9.6, width=840)
    yy -= ph + 8
text_block(40, 82,
           "The tests forge every request the UI hides — the robot triaging, a non-assignee resolving, a customer "
           "re-tenanting her case — and all bounce off the kernel, 403 by rule name, nothing written. Hiding a button "
           "changes nothing; that is the whole point of the boundary.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 8
image_slide("Act IV · a refusal, end to end", "Press the locked button anyway: the ticket sentence answers",
            "relay-denied-toast.png",
            "quinn (staff, not the assignee) presses the locked Resolve: 403 — Refused: rule only_assignee_resolves, "
            "“HD-4: a case is resolved by the agent it is assigned to; only a lead may resolve someone else's case.” "
            "Ticket → rule id → solver vocabulary → typed Denied → toast: one unbroken chain of names.",
            "Affordances, not permissions: one kernel call powers the allowed buttons AND the locked disclosures; the "
            "presentation philosophy is the UI author's choice, the decision never is.")

# ----------------------------------------------------------------- slide 9
header("Act V in one slide (note 16)", "One rule base, three entity types — the kernel joins the parent")
code_block(40, H - 96, 470, [
    ("children:", ""),
    ("  - entity: comment", ""),
    ("    context: [state, same_org]   # opt-in, per atom", "cmd"),
    "",
    ("- id: sealed_thread", ""),
    ("  entity: [comment, attachment]", ""),
    ("  effect: deny", ""),
    ("  when: 'parent.state == \"closed\"", ""),
    ("         and action != \"read\"'", ""),
    "",
    ("# the kernel joins the live parent into the decision:", "dim"),
    (">>> desk.create(dana, {\"body\": \"one more thing\"},", ""),
    ("...             entity=\"comment\", parent_id=closed_case)", ""),
    ("kernel.Denied: denied by sealed_thread", "fail"),
], size=8.8)
panel(540, 208, 380, 248)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(554, 434, "What the episode proved")
bullets(554, 410, [
    "A comment's legality depends on its case's LIVE state and org — decided in the kernel, which joins the parent row. The client never computes context (it would be an enforcement point).",
    "Per-entity analyzer, round-1 PASS with pre-registered predictions held; internal notes do not exist for customers — THREAD (3) vs THREAD (2), even by forged id.",
    "The un-predicted lesson: untagged global denies fail OPEN for children (deny_inactive) — tagged, pinned by S28/S29, negative direction verified. Guardrail 11(a).",
    "Sharp edges recorded as falsifiers ME-1–6: no aggregates (a frame problem), cascades skip child delete rules, field-level visibility stays UI-trust.",
], 350, size=9.0, gap=6)
yy = 172
x = 40
for t in ["33 rules · 3 entities", "37,200 situations", "0 engine domain lines", "forged requests: 403 by name"]:
    x = chip(x, yy, t) + 8
text_block(40, 140,
           "“A closed case seals its thread” is one atom, checked in all 37,200 situations — not a flag the UI remembers "
           "to sync. Full story: research/16-multi-entity-rules.md, examples/helpdesk/.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 10
image_slide("Act V · the read rule, visible", "Same case: staff see THREAD (3); the customer sees THREAD (2)",
            "relay-dana-thread.png",
            "dana's view of case #1: one comment fewer, no internal toggle. Not CSS hiding — visible() never returned "
            "the internal note, get() by forged id raises Denied(internal_is_staff_only), and the forged POST with "
            "internal=yes comes back 403. S15 proves no allowed action ever touches an internal note outside staff.",
            "The count in the heading is the architecture in two characters: the list IS the read rule, applied by the "
            "kernel — the UI invented the layout, the rules decided the content.")

# ---------------------------------------------------------------- slide 11
header("Act VI · the redirect", "“Three best approaches” → they are layers of ONE method")
text_block(40, H - 100,
           "The developer asked for the best approaches by developer experience, velocity and safety, each written up as "
           "a manual — then redirected: if they are layers of one method, compound them into ONE manual and care about "
           "how they compose. The three layers, by what they guard:",
           size=11.5, width=880)
layers6 = [
    ("LAYER 1 — rules are the program", OK,
     "Every single-request decision: authz, tenancy, lifecycle, visibility, document discipline. The rule base is the "
     "program; Z3 checks it exhaustively — both directions — and a generic kernel enforces it under a free UI. Where "
     "you live day to day."),
    ("LAYER 2 — models before code", ACCENT_D,
     "Everything that only goes wrong across time and interleavings: migrations under traffic, jobs, retries. Model "
     "the design (Quint), let the checker attack it, escalate the proof ladder as needed, then hold the real system "
     "to the same invariants with a conformance harness. Episodic."),
    ("LAYER 3 — the frozen gate + agent loop", FREE,
     "How ALL code gets written: agents edit freely inside a mechanically frozen spec; counterexamples are the repair "
     "signal; objectives (speed, cost) live outside the gate. Nobody reviews agent diffs — humans review specs and "
     "counterexamples. The meta-layer."),
]
yy = H - 170
for t, col, b in layers6:
    panel(40, yy - 84, 880, 84)
    c.setFillColor(col)
    c.rect(40, yy - 84, 6, 84, fill=1, stroke=0)
    c.setFont(FB, 11.5)
    c.setFillColor(col)
    c.drawString(58, yy - 20, t)
    text_block(58, yy - 36, b, size=9.6, width=840)
    yy -= 92
text_block(40, 84,
           "Different failure modes need different engines — a wrong deny, a race, and a lazy agent “fix” are three "
           "different animals. The composition rules (which layer owns which concern, one vocabulary end to end, every "
           "seam mechanically held) are what make this a method rather than three tools.",
           size=10.5, width=880, color=ACCENT_D)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 12
header("Act VI · the manual", "docs/manual.md — 1,568 lines, self-contained, every claim runs")
panel(40, 216, 430, 240)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(54, 434, "The shape")
bullets(54, 410, [
    "Part 0 — orientation: the inversion (spec durable, code cheap), why three layers, the numbers up front.",
    "Part 1 — the rules layer, taught by building Clearance line by line: vocabulary as a budget, the two disciplines, the gate in three directions, the kernel, relations.",
    "Part 2 — models before code: the migration model, the two falsified designs, the escalation ladder, conformance.",
    "Part 3 — the frozen gate + loop: freeze mechanics, the controlled experiment, Grant<Op> tokens.",
    "Part 4 — composition: the routing table, one vocabulary, the ratchet, what stays human, adoption path.",
    "Part 5 — honest costs: friction ledger, falsifier index, when NOT to use this, recorded dead ends.",
], 402, size=8.8, gap=5)
panel(510, 216, 410, 240)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(524, 434, "What makes it a manual, not a pitch")
bullets(524, 410, [
    "Written for an experienced developer with NO formal-methods background: the workflow, the syntax by example, day-2 operations, the failure modes.",
    "Self-contained by design (developer directive): it assumes the reader reads NOTHING else — no research notes, no journals — and presents the system in its own right, not as an experiment report.",
    "Every transcript is real tool output, and the worked example is a real committed service with its own one-command check (next slide).",
    "The costs part is a priced register: the bill itemized, the sharp edges with statuses, when NOT to use it, alternatives considered.",
    "DX, velocity and safety get an explicit ledger per layer, and for the whole.",
], 382, size=8.8, gap=5)
text_block(40, 178,
           "The manual is now the repository's front door: the root README points at it first, and every example "
           "directory points back at the part that teaches it. Adoption is staged (Part 4.7): gate one risky surface, "
           "move enforcement into the kernel, put the Layer-3 gate on one repo, reach for models at the first migration.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 13
header("Act VI · Clearance", "The worked example is executable — including its own round-1 bug")
code_block(40, H - 96, 500, [
    ("$ analyze rulesets/approvals-round1 \\", "cmd"),
    ("      --gate rulesets/approvals      # the frozen gate", "cmd"),
    ("FAIL DEAD deny rule 'no_self_decision': it never", "fail"),
    ("     refuses anything another rule would have allowed", "fail"),
    ("ok   S5_no_self_decision      # passes — VACUOUSLY", "ok"),
    ("FAIL P3_managers_expense_too: IMPOSSIBLE —", "fail"),
    ("     no allow rule ever grants it", "fail"),
    ("FAIL feat_four_eyes: step 1 (mia create):", "fail"),
    ("     expected allow, got deny (rule: default_deny)", "fail"),
    ("VERDICT: FAIL (3 finding(s))", "fail"),
    "",
    ("$ analyze rulesets/approvals    # the fixed rule base", "cmd"),
    ("VERDICT: PASS (0 findings)      # 3,456 situations", "ok"),
], size=8.4, dark=True)
panel(570, 190, 350, 266)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(584, 434, "The teaching moment, real")
bullets(584, 410, [
    "Clearance: expense claims — org walls, receipts, four-eyes approval, finance-only payment, sealed records. 10 rules, 3,456 situations, gate 10 ∀ + 4 ∃ + 29 steps.",
    "The real round-1 draft let only employees file — so nobody could ever author-and-decide: “nobody decides their own claim” held VACUOUSLY, the deny was provably dead, the four-eyes feature could not exist.",
    "Safety alone said everything was fine. The possibility direction and the dead-rule check caught it — gates need both directions, demonstrated in one transcript.",
    "The fix was a requirement fix (managers expense too), and the broken draft is gated forever: check.sh stage 2 REQUIRES this FAIL.",
], 320, size=8.9, gap=5)
yy = 168
x = 40
for t in ["examples/approvals/", "check.sh: PASS + required FAIL + HTTP replay", "manual Part 1 builds it line by line"]:
    x = chip(x, yy, t) + 8
text_block(40, 136,
           "The manual quotes this transcript verbatim, and the FAIL is a required CI stage — the teaching example "
           "cannot rot, because rotting would break the build.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 14
header("Act VI · composition", "One vocabulary, one ratchet — a real ticket across all three layers")
panel(40, 208, 440, 248)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(54, 434, "Which layer owns which concern")
bullets(54, 410, [
    "“Only X may…”, “never…”, “X sees only…” (one request decides it) → Layer 1 rule + ∀-property.",
    "“…even while the migration runs”, “two requests at once”, “eventually” → Layer 2 model, then conformance.",
    "“The UI should…”, glue, engine growth → free code, agent-built under the Layer 3 gate.",
    "“Sum/count of…”, fuzzy matching → a projection at the boundary, or deliberately client-side — RECORDED either way.",
    "Incidents: reproduce the bug as a gate item, in gate vocabulary; freeze it; only then repair. The gate only ever tightens.",
], 412, size=9.2, gap=6)
code_block(520, H - 96, 400, [
    ("# the column rename, end to end (all committed):", "dim"),
    ("falsified design #2        (L2 model trace)", ""),
    ("  -> seeded repair task            (L3)", ""),
    ("    -> partial fix exposes the", ""),
    ("       safety-only gate gap", "fail"),
    ("      -> gap becomes frozen feature", ""),
    ("         runs + witness   (the ratchet)", "cmd"),
    ("        -> full fix, 1 round,", ""),
    ("           same generic prompt", "ok"),
    ("          -> inductive -> any-size ->", ""),
    ("             liveness proofs (L2 ladder)", "ok"),
    "",
    ("# every arrow is a committed artifact:", "dim"),
    ("# p1, p4/episodes/, p6, p7", "dim"),
], size=9.0)
text_block(40, 180,
           "Every seam has a mechanical check: rules↔runtime by exhaustive two-backend agreement, kernel↔UI by the "
           "boundary lint (bypass variant must FAIL), model↔code by the conformance harness, spec↔agents by the frozen "
           "region diff. The one unsound seam — NL ticket ↔ formal rule — is held by grounded human review plus the "
           "gate's deliberate redundancy. If a seam is held by discipline, it is already leaking.",
           size=10.5, width=880)
text_block(40, 108,
           "One ghost variable (lastReadOk) carries the correctness story from the first model trace to the conformance "
           "assertion to the frozen repair gate. That continuity — not any single layer — is the method.",
           size=10.5, width=880, color=ACCENT_D)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 15
header("Scoreboard", "Six rule bases, one engine, every claim executable")
stats = [
    ("6 : 1", "services per engine — CMS, tickets, receivables, Flowdeck, "
     "Relay, Clearance on ~2,300 lines of domain-free Python (rule base "
     "456, kernel 291, analyzer 351, lint 105).", ACCENT_D),
    ("111,312", "situations checked exhaustively across the six rule bases — "
     "runtime evaluation and the Z3 compilation agree on every one; "
     "re-verified fresh for the manual.", OK),
    ("1,568", "lines of self-contained manual (docs/manual.md) teaching all "
     "of it — three layers + composition + priced limits, every transcript "
     "real, the worked example committed.", FREE),
    ("2-way CI", "every check.sh holds both directions: gates must PASS, "
     "and the preserved buggy drafts — Clearance round-1, taskboard "
     "round-2, the bypass variant — must FAIL.", WARN),
]
x = 40
for n, b, col in stats:
    panel(x, 280, 205, 130)
    c.setFont(FB, 20)
    c.setFillColor(col)
    c.drawString(x + 14, 380, n)
    text_block(x + 14, 360, b, size=8.6, width=178)
    x += 225
c.setFont(FB, 12)
c.setFillColor(ACCENT_D)
c.drawString(40, 248, "The method by the numbers:")
bullets(40, 224, [
    "Layer 1: Flowdeck tickets → green gate ≈ 1 hour, 4 rounds × 0.18 s, 2 real authorization holes caught pre-code; Relay 33 rules over 3 entities in 721 lines of YAML, solver round ~0.4 s.",
    "Layer 2: two migration designs falsified pre-code in <1 s each; proofs to every depth (inductive), every size (EPR, 0.38 s), and liveness (TLC, 623 states); the harness caught a real TOCTOU race and reproduces 59 anomalies on demand.",
    "Layer 3: full fix in 1 round from a stronger gate (controlled, same prompt); 3.94× speedup with two broken attempts absorbed; capability tokens make kernel bypass a compile error (E0639/E0308, pinned).",
], 880, size=10, gap=6)
text_block(40, 100,
           "What the analyzer asks of every rule change, in seconds, per entity: dead rules · stale assumptions · "
           "∀-safety · ∃-possibility · lifecycle liveness + gated entries · frozen features with refusals by name.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 16
header("Guardrails · CLAUDE.md", "Learned the hard way — the manual is their long form")
gr = [
    ("11 · Relations are engine work, never client joins", "Child entities import parent context (parent.state, parent projections); the kernel joins the live parent into every child decision. Sharp edges kept: untagged global denies fail OPEN (tag + pin them); cascades skip child delete rules.", FREE),
    ("10 · The boundary is a kernel API, not a UI", "Rules guard interaction logic behind a function-level API; the UI above is agent-authored and free; generated UIs are scaffolding. Hold the boundary mechanically (lint), never by convention.", FREE),
    ("1 · The spec is frozen for agents", "The analyzer takes --gate from a pinned directory; agents edit rules, never the gate. Historic buggy drafts are gated forever as regressions — Clearance's round-1 joined them this week.", ACCENT_D),
    ("2 · Gates need both directions", "Safety-only gates accept fixes that trade away liveness (“the safest system does nothing”). Clearance's S5 passing VACUOUSLY over a dead four-eyes rule is the one-transcript demonstration.", ACCENT_D),
    ("3 · Gate strength beats NL steering", "Same bug, model, prompt: a stronger gate turned a partial fix into the full fix (P4). Cheaper models are fine when the gate is strong.", ACCENT_D),
    ("6 · Counterexamples are the currency", "Named and machine-readable: situation witnesses, unsat cores, denied_by 403s — typed Denied values any UI renders its own way.", ACCENT_D),
    ("7 · Record falsified predictions", "The DEVLOGs keep wrong predictions next to the runs that killed them — and the manual's Part 5 cites only that recorded evidence, never retrospect.", ACCENT_D),
    ("8 · Boundaries by construction", "Where the language allows: capability tokens, typestate. Where it doesn't (Python): name-mangling + a lint whose failure is named — and the honesty that this is not a proof.", ACCENT_D),
]
xs2, yw = [40, 500], 420
yy0 = H - 108
for i, (t, b, col) in enumerate(gr):
    x = xs2[i % 2]
    yy = yy0 - (i // 2) * 96
    panel(x, yy - 88, yw, 88, fill=HexColor("#F3F0FF") if i < 2 else PANEL)
    c.setFont(FB, 11)
    c.setFillColor(col)
    c.drawString(x + 14, yy - 20, t)
    text_block(x + 14, yy - 36, b, size=9.2, width=yw - 28)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 17
header("Roadmap", "Falsifiers on the table")
c.setFont(FB, 13)
c.setFillColor(OK)
c.drawString(40, H - 110, "Held so far")
bullets(40, H - 134, [
    "RB1 (tickets land as rule diffs): held six times, and the cost curve stayed closed — imports 0, receivables ~100 (time), Flowdeck ~60 (relations), Relay 0 twice, Clearance 0 (plus one generic probe fix the new domain surfaced).",
    "The one-entity wall came down as engine work; both multi-entity rounds PASS with predictions pre-registered; the method survived being written down — every manual claim re-verified against the repo.",
], 880, size=10.5, gap=6)
c.setFont(FB, 13)
c.setFillColor(ACCENT_D)
c.drawString(40, H - 240, "Next")
bullets(40, H - 264, [
    "DX1 now has its instrument: hand an outside developer TICKETS.md + docs/manual.md — do they ship a ruled app in under a day without touching the engine? DX2 — the same tickets implemented conventionally by a strong LLM: does it contain the interaction holes the gates caught?",
    "ME-1 — aggregates, when a ticket forces them: kernel-computed aggregate projections, conservatism stated. ME-6 — cascade-decides or the load-time check. ME-5 — the fail-open lint.",
    "KB1 — red-team the boundary lint. KB2/ME-4 — a reporting/read seam that still applies the read rule per row. KB3 — concurrent writers between decide and write, on real Postgres (the P3 harness). KB4 — nearest-allow refusal explanations that do not leak across tenants.",
    "RB3 — ticket→rule-diff vs ticket→handler fidelity, measured. P8 — the same rules as Cedar policies. P9 — the invariant→Postgres-constraint compiler nobody has built.",
], 880, size=10, gap=6)
c.setFont(FB, 12)
c.setFillColor(MUTED)
c.drawString(40, 100, "Parked (consciously, with reasons recorded)")
text_block(40, 82,
           "Alloy (Z3 covers it) · Quint→Rust codegen (no tooling) · Kani until unbounded domains arrive · Verus (proxy-blocked; Dafny stands in).",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 18
c.setFillColor(INK)
c.rect(0, 0, W, H, fill=1, stroke=0)
c.setFillColor(FREE)
c.rect(0, H - 8, W, 8, fill=1, stroke=0)
c.setFont(FB, 26)
c.setFillColor(WHITE)
c.drawString(70, 400, "The one-sentence takeaway")
c.setFont(F, 17)
c.setFillColor(HexColor("#D7E2E9"))
for i, ln in enumerate([
    "You state what must never and must always happen; agents make something that does it; reasoning",
    "engines — not humans — hold the code to the statement. Six services, 111,312 exhaustively-checked",
    "situations, two falsified designs and one controlled experiment later, the method is one document.",
]):
    c.drawString(70, 350 - i * 28, ln)
c.setFont(F, 11.5)
c.setFillColor(HexColor("#8FA5B5"))
c.drawString(70, 210, "Read it: docs/manual.md — the field manual (start at Part 0; Part 1 builds examples/approvals/)")
c.drawString(70, 190, "Run it: examples/approvals/check.sh · examples/helpdesk/check.sh + python app.py · prototypes/p1..p7")
c.drawString(70, 170, "The stack beneath: research/INDEX.md · notes 13–16 (rules, DX, boundary, relations) · 09–12 (proofs)")
footer(title_page=True)
c.showPage()

c.save()
