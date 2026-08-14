#!/usr/bin/env python3
"""Generate the project slide deck (PDF, 16:9 landscape).

Audience: engineers without prior formal-verification background.
Regenerated ground-up from the current repository state (see CLAUDE.md
workflow rule: the deck always describes the repo, never accretes).
This edition leads with the developer-experience study (examples/
taskboard — Flowdeck, note 14): an end-to-end SaaS app built as rules,
with screenshots of the running product and the honest DEVLOG findings;
acts I and II are compressed to evidence slides.
Usage: python3 make_slides.py  ->  formal-guardrails-slides.pdf
(needs reportlab + pillow; screenshots come from img/, regenerate them
with examples/taskboard/screenshots.py)
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
    c.drawString(40, 20, "Formal guardrails for LLM agents · the developer experience · 2026-08-14")
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


def box(x, y, w_, h_, title, body, title_color=ACCENT_D, body_size=8.6,
        fill=PANEL):
    panel(x, y, w_, h_, fill=fill)
    c.setFont(FB, 9.5)
    c.setFillColor(title_color)
    c.drawString(x + 10, y + h_ - 16, title)
    text_block(x + 10, y + h_ - 29, body, size=body_size, width=w_ - 20,
               color=INK)


def shot(path, x, y, w_):
    """Draw a screenshot (all are 16:9) at width w_, top-left anchored at
    (x, y_top) — returns bottom y. Adds a hairline frame."""
    h_ = w_ * 9 / 16
    c.drawImage(ImageReader(str(IMG / path)), x, y - h_, w_, h_)
    c.setStrokeColor(PANEL_LINE)
    c.setLineWidth(1)
    c.rect(x, y - h_, w_, h_, fill=0, stroke=1)
    return y - h_


def image_slide(kicker, title, img, caption, note=None):
    header(kicker, title)
    bottom = shot(img, 145, H - 90, 670)
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
c.setFillColor(ACCENT)
c.rect(0, 118, W, 5, fill=1, stroke=0)
c.setFillColor(WHITE)
c.setFont(FB, 33)
c.drawString(70, 350, "A SaaS app with zero app code")
c.setFont(FB, 20)
c.setFillColor(HexColor("#7FB5B2"))
c.drawString(70, 315, "formal guardrails for LLM agents, act III: the developer experience")
c.setFont(F, 15)
c.setFillColor(HexColor("#AFC3CF"))
c.drawString(70, 264, "Flowdeck — a multi-tenant team kanban — built end to end as one rule base:")
c.drawString(70, 242, "7 tickets, 377 lines of YAML, a clickable web UI, and a solver reviewing every change.")
c.setFont(F, 12)
c.drawString(70, 172, "With screenshots of the running product, the unedited development journal (two real")
c.drawString(70, 154, "authorization holes caught), and what this way of working actually feels like. August 2026.")
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
     "moment. Example: “a user never sees another team's data.” You already "
     "write these — in comments, runbooks and post-mortems. Here they "
     "become machine-checkable."),
    ("Model", "A small, faithful board-game version of your system: its "
     "states and legal moves. Here the “model” is not beside the system — "
     "the rule base IS both the model and the running program."),
    ("Checker", "A tireless adversary (here: the Z3 solver). It considers "
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
               "DSL” — Cedar's shape — ranked first. Acts II and III build exactly that.",
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
    "Domain transfer (receivables): the engine was missing time, not receivables — ~100 generic lines.",
    "Two redundant rules proven dead and deleted: the solver shrinks rule bases, reversing 1980s rule rot.",
], 300, size=9.3, gap=5)
text_block(40, 96,
           "Act III asks the question that decides adoption: what does building a real product this way FEEL like — "
           "with a UI you can click, and an honest journal of every finding?", size=11.5, width=880, color=ACCENT_D)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 6
header("Act III · the experiment", "Flowdeck: 7 tickets, 377 lines of YAML, zero app code")
text_block(40, H - 100,
           "A multi-tenant team kanban SaaS, developed exactly as the method prescribes: tickets → rules → frozen gate, "
           "with every analyzer round journaled (DEVLOG.md) and predictions recorded before the runs that test them.",
           size=12, width=880)
code_block(40, 388, 430, [
    ("# TICKETS.md — the product spec (excerpts)", "dim"),
    "TB-1  A team's board is completely invisible to",
    "      every other team. Staff sees everything",
    "      but never decides reviews.",
    "TB-3  Only the assignee starts/submits a task;",
    "      no work starts without an estimate.",
    "TB-4  Nobody approves a task they did themselves.",
    "TB-6  A janitor bot archives stale done tasks —",
    "      and must be able to do nothing else.",
])
code_block(490, 388, 430, [
    ("# rules.yaml — the ticket, translated (excerpt)", "dim"),
    "- id: team_walls",
    '  description: "TB-1: members and leads only',
    '    ever act inside their own team — reading',
    '    included, creating included."',
    "  effect: deny",
    "  when: 'actor.role in [\"member\", \"lead\"]",
    "         and not resource.same_team'",
])
bullets(40, 152, [
    "The whole application: rules.yaml (160 lines, 18 rules) + safety.yaml (13 ∀-properties, 8 ∃-witnesses) + features.yaml (5 scenarios, refusals by name) + a seed list. UI, API, storage, analysis: inherited, generic.",
    "New vocabulary this domain forced into the generic engine (~60 lines): actor attributes and actor↔resource relations — same_team, assigned_to_me — as projected booleans. Third domain in a row to cost exactly one missing concept (receivables: time).",
], 880, size=10.5, gap=6)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 7
header("Act III · the loop, measured", "Four analyzer rounds, 0.18 s each — all findings real")
rounds = [
    ("1", "unknown variable 'actor.is_assignee' — typo = load error, named. Prediction “the containment deny is dead” FALSIFIED: an unguarded allow made it load-bearing.", MUTED),
    ("2", "TWO REAL AUTHORIZATION HOLES (below) + two probes expecting the wrong deny name (overlapping denies are declaration-order-named).", WARN),
    ("3", "DEAD deny rule 'janitor_scope' — after the fix, default-deny + tight allows contain the bot; gate S11 proves it universally. Deleted: the solver shrinks the rule base.", ACCENT_D),
    ("4", "PASS (0 findings). Tickets → green gate: ~1 hour of author time, almost all of it writing YAML, none of it debugging.", OK),
]
yy = H - 96
for n, b, col in rounds:
    panel(40, yy - 60, 430, 60)
    c.setFont(FB, 15)
    c.setFillColor(col)
    c.drawString(52, yy - 36, n)
    text_block(74, yy - 16, b, size=8.8, width=384)
    yy -= 66
x = 40
for t in ["34,560 situations", "0.18 s / round", "2 real holes", "~1 h to green"]:
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
text_block(490, 268, "Hole 1: anyone who can write the assignee field could hand "
           "work to the anonymous public. Hole 2: “staff can support everything” "
           "quietly granted staff the team's work (TB-3 violation). Both are "
           "interaction bugs — each rule read fine alone. Nobody writes the test "
           "where the task is assigned to the anonymous user; the ∀-check "
           "considers all 34,560 situations, then names the granting rule.",
           size=9.6, width=430, color=INK)
text_block(40, 116,
           "The round-2 draft is preserved (rulesets/taskboard-round2) and held to the frozen gate by check.sh forever — "
           "development history as a permanent regression test.", size=10.5, width=880, color=ACCENT_D)
footer(); c.showPage()

# ----------------------------------------------------------------- slides 8-12: screenshots
image_slide("Act III · the result", "The app, derived — nobody wrote this UI",
            "board-tom.png",
            "Board columns = the lifecycle table; cards = the read rule; buttons = the decision function "
            "(tom gets “start” only where he is the assignee). Persona switcher: authn is out of scope, authz is the study.",
            "python app.py → http://127.0.0.1:8800/ui — the same generic module renders any rule base. "
            "The demo data was seeded through the rules over HTTP: a seed that violates policy cannot exist.")

image_slide("Act III · tenant walls, visibly", "Same URL, other team: nadia sees only boreal",
            "board-nadia.png",
            "team_walls (TB-1) is one deny rule — and S1_team_isolation proves that no allowed situation lets a member "
            "or lead act cross-team. The board IS the read rule, so the proof is what you are looking at.",
            "The visibility probe compares the live list endpoint against the decision function's prediction per persona "
            "(check.sh stage 4).")

image_slide("Act III · a refusal, end to end", "mira clicks “approve” on her own task",
            "banner-denied.png",
            "403 — refused by rule no_self_approval, with the TB-4 ticket sentence. One vocabulary carries from the "
            "ticket to the rule id to the solver's counterexample to the button tooltip to this banner.",
            "The UI never enforces — denied buttons stay clickable on purpose, and the decision function refuses by "
            "name. Locked buttons: delete (nothing_is_deleted), approve (no_self_approval); send back is live.")

image_slide("Act III · reflection, not enforcement", "Every control names the rule that governs it",
            "detail-mira.png",
            "Three rules visible at once: delete locked by nothing_is_deleted, approve locked by no_self_approval, and "
            "the edit form warning “editing is refused right now by review_is_sealed” (TB-4: content sealed under review).",
            "A support question answers itself: “why can't I?” → the rule id and the stakeholder sentence it translates.")

# ---------------------------------------------------------------- slide 12
header("Act III · the program, rendered — twice", "The rules page; and the same UI serving the CMS")
bottom = shot("rules-page.png", 40, H - 96, 430)
bottom2 = shot("board-cms.png", 490, H - 96, 430)
text_block(40, bottom - 14,
           "/ui/rules renders rules.yaml — lifecycle, every rule with its ticket "
           "sentence, projections, assumptions. The program is its own "
           "documentation, in the app.", size=9.5, width=430, color=ACCENT_D, font=FI)
text_block(490, bottom2 - 14,
           "Generality, executable: the identical UI module serving the CMS "
           "(editor persona, publish/reject chips, drafts hidden). The CMS "
           "gained a browser UI without changing a line.", size=9.5, width=430,
           color=ACCENT_D, font=FI)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 13
header("Act III · how it feels", "The phenomenology, kept honest (note 14)")
feels = [
    ("Review latency is gone", "0.18 s from edit to verdict, and the verdict is terminal: PASS = mergeable; FAIL = the situation + the rule, by name. Like a type checker for authorization — that also demands liveness, so “deny everything” cannot pass."),
    ("The gate is where the thinking happens", "Writing safety.yaml forced the questions the rules let me fudge (“may staff work a task?”). ∀-properties are the design review; the rules are just the design."),
    ("The unit of work is a sentence", "Every edit was a ticket-shaped stanza. There was never a “now write the handler” moment — after the gate went green, building the app meant writing a seed list."),
    ("Predictions get falsified fast", "“The containment deny is dead” — falsified in round 1, true in round 3, one fix later. The dead-rule check is a live diagnostic of the containment regime."),
    ("Bugs tests would miss", "Both real holes were rule interactions. The solver considers the situation nobody writes a test for — task assigned to “anonymous” — and hands you the granting rule."),
    ("The app is a byproduct", "UI, API, storage, named errors: derived. Zero lines of Flowdeck-specific code exist in the repository."),
]
for i, (t, b) in enumerate(feels):
    x = [40, 490][i % 2]
    yy = (H - 100) - (i // 2) * 118
    panel(x, yy - 110, 430, 110)
    c.setFont(FB, 11.5)
    c.setFillColor(ACCENT_D)
    c.drawString(x + 14, yy - 19, t)
    text_block(x + 14, yy - 36, b, size=9.6, width=402)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 14
header("Act III · frictions found", "The sharp edges are the research — all enumerable, none a wall")
fr = [
    ("Namespace surprise", "Relational projections read like actor facts but live under resource.* (resource.assigned_to_me). Load error caught it; naming needed a convention. Cost: one round."),
    ("Deny-order naming", "When several denies match, denied_by is declaration-order. Named-denial probes must sit in the minimal state that triggers them. A future analyzer check could flag ambiguous probes."),
    ("Edit is blind to proposed values", "Rules see an edit's current fields, not the incoming ones — “a title can never be emptied later” is not expressible; S3 guards creation only. Vocabulary gaps fail loud; semantic gaps fail silent. Sharpest edge found."),
    ("Assumptions are trusted, not proven", "Nothing stops assignee: “ada” at runtime; an assignees-are-team-members assumption would be unchecked (only authorship is cross-verified mechanically today)."),
    ("The vocabulary is a budget", "Every boolean doubles the situation space: 276,480 → 34,560 after has_-opt-out. Exhaustive backend agreement is ~85 s of check.sh — RB2's known scaling edge."),
    ("The engine wants to be a package", "Flowdeck path-shims ../rule-driven-cms. Fine for research, grating for product work."),
]
for i, (t, b) in enumerate(fr):
    x = [40, 490][i % 2]
    yy = (H - 96) - (i // 2) * 122
    panel(x, yy - 114, 430, 114, fill=HexColor("#F9F1EC") if i == 2 else PANEL)
    c.setFont(FB, 11)
    c.setFillColor(WARN)
    c.drawString(x + 14, yy - 19, t)
    text_block(x + 14, yy - 36, b, size=9.6, width=402)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 15
header("Scoreboard", "Four services, one engine, every claim executable")
stats = [
    ("4 : 1", "services per engine — CMS, tickets, receivables, Flowdeck on "
     "1,615 lines of domain-free Python (455 of them the web UI every rule "
     "base gains at once).", ACCENT_D),
    ("377 : 0", "lines of YAML that ARE Flowdeck vs lines of app-specific "
     "code. CMS: 313. Receivables: 290. Tickets: 100.", ACCENT_D),
    ("70,656", "situations checked exhaustively across the four services — "
     "runtime evaluation and the Z3 compilation agree on every one.", OK),
    ("16 + 4", "named findings across two sabotaged rule bases and the "
     "preserved round-2 draft; zero false passes; every finding names a rule "
     "or prints a situation.", WARN),
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
c.drawString(40, 250, "Transfer cost per new domain (falsifier RB1) — one missing generic concept each, then flat:")
bullets(40, 226, [
    "CMS → tickets: 0 engine lines. → receivables: ~100 (the concept: TIME — clock, date projections, feature clocks).",
    "→ Flowdeck: ~60 (the concept: actor↔resource RELATIONS — tenancy, assignment) + the generic UI (~455, every service at once).",
    "Prediction on the table: a fifth domain (approvals/expenses) costs zero engine lines — time + relations + validation cover it.",
], 880, size=10.5, gap=6)
text_block(40, 120,
           "What the analyzer asks of every change, in seconds: dead rules · stale assumptions · ∀-safety · ∃-possibility "
           "· lifecycle liveness + gated entries · frozen features with refusals by name.", size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 16
header("Where it stops", "Kept deliberately sharp")
rows = [
    ("The projection boundary", "Rules see finite booleans (same_team, assigned_to_me, is_past_due). Fuzzy matching, "
     "cross-item invariants (“no two claims share a reference”, quotas) live in clients — properly in store constraints "
     "(P9: the invariant→Postgres compiler that still doesn't exist, anywhere)."),
    ("Edit can't see proposed values", "New from the DX study: rules evaluate an edit against current fields, so "
     "“title can never be emptied” is unstatable. Known engine fix; until then this is the silent-gap class to watch (DX3)."),
    ("No time-interleaving", "Single-situation rules can't see races — the demoted author who is still is_author. Rung 2's "
     "job: the Quint temporal twin (RB4) stays on the ladder."),
    ("One entity per rule base", "A kanban app fit in one. Comments/checklists would force relations between ruled "
     "entities — N rule bases + client joins, or engine work."),
    ("The engine is unproven Python", "1,615 lines taken on faith. The production form is a verified engine (Cedar's "
     "Lean proofs, or our track-D Dafny→Go shape): one proof, then per-change analysis only."),
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

# ---------------------------------------------------------------- slide 17
header("Guardrails · CLAUDE.md", "What we learned the hard way — now enforced")
gr = [
    ("The spec is frozen for agents", "Enforced mechanically — the analyzer takes --gate from a pinned directory; agents edit rules, never the gate. The taskboard's round-2 draft is gated forever."),
    ("Gates need both directions", "Safety-only gates accept fixes that trade away liveness (“the safest system does nothing”). Every gate here = safety + possibility witnesses + frozen feature runs."),
    ("Gate strength beats NL steering", "Same bug, model, prompt: the stronger gate turned a partial fix into the full fix (P4). Cheaper models are fine when the gate is strong."),
    ("Escalate to proofs", "Rules (this deck) < temporal models < inductive < parameterized < liveness < hyperproperties. Climb only when the ticket needs time, relations, or computation."),
    ("Translate / validate split", "LLM translation of NL→rules is unsound — always followed by a sound solver step. Humans review rules sentence-by-sentence, never agent edits."),
    ("Counterexamples are the currency", "Named and machine-readable: situation witnesses, blocking denies, denied_by 403s — now also greyed buttons and banners in the UI."),
    ("Verify claims; record falsified predictions", "The DEVLOG keeps the author's wrong prediction (round 1) next to the run that killed it. The checker corrected the author — again. That is the method working."),
    ("Boundaries by construction", "Bots are ordinary actors with no back door; the janitor is contained by default-deny, proven by S11 — after the solver showed the scope rule was dead."),
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

# ---------------------------------------------------------------- slide 18
header("Roadmap", "Falsifiers on the table")
c.setFont(FB, 13)
c.setFillColor(OK)
c.drawString(40, H - 110, "Held so far")
bullets(40, H - 134, [
    "RB1 (tickets land as rule diffs): held three times — imports 0 engine lines, receivables ~100 (time), Flowdeck ~60 (relations). Gate-language growth is flattening as predicted.",
    "DX verdict (note 14): for the policy-shaped core of a SaaS app, the loop beats conventional development on its own terms — faster iteration, terminal verdicts, interaction bugs caught, UI/API for free.",
], 880, size=10.5, gap=6)
c.setFont(FB, 13)
c.setFillColor(ACCENT_D)
c.drawString(40, H - 236, "Next")
bullets(40, H - 260, [
    "DX1 — an outside web developer ships a ruled app from tickets in under a day without reading the engine. DX2 — the same 7 tickets, implemented conventionally by a strong LLM: does it contain either interaction hole the gate caught here?",
    "DX3 / engine — close the edit-proposed-values gap (evaluate edits against incoming fields); add the ambiguous-probe warning.",
    "RB3 — ticket→rule-diff vs ticket→handler-code fidelity, measured. RB5 — agent repair on the sabotaged rule bases under the frozen gate.",
    "RB4 — the Quint temporal twin (stale-role races, clock skew). RB2 — symbolic backend-agreement when exhaustive hurts. P8 — the same rules as Cedar policies. P9 — the invariant→Postgres-constraint compiler nobody has built.",
], 880, size=10.5, gap=6)
c.setFont(FB, 12)
c.setFillColor(MUTED)
c.drawString(40, 108, "Parked (consciously, with reasons recorded)")
text_block(40, 90,
           "Alloy (Z3 covers it) · Quint→Rust codegen (no tooling) · Kani until unbounded domains arrive · Verus (proxy-blocked; Dafny stands in).",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 19
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
    "We built a working multi-tenant SaaS product out of seven tickets and 377 lines of rules —",
    "no handlers, no app UI code — and the solver reviewed every change in a fifth of a second,",
    "catching two authorization holes no test suite would have looked for.",
]):
    c.drawString(70, 350 - i * 28, ln)
c.setFont(F, 11.5)
c.setFillColor(HexColor("#8FA5B5"))
c.drawString(70, 210, "Run it: examples/taskboard/check.sh · python examples/taskboard/app.py → /ui")
c.drawString(70, 190, "Read it: examples/taskboard/DEVLOG.md (the raw journal) · research/14-developer-experience.md")
c.drawString(70, 170, "The stack beneath: research/13 (rules as the program) · 09–12 (proof escalation) · prototypes p1–p7")
footer(title_page=True)
c.showPage()

c.save()
print(f"wrote {OUT} ({page[0]} pages)")
