#!/usr/bin/env python3
"""Generate the project slide deck (PDF, 16:9 landscape).

Audience: engineers without prior formal-verification background.
Regenerated ground-up from the current repository state (see CLAUDE.md
workflow rule: the deck always describes the repo, never accretes).
This edition leads with act IV (examples/helpdesk — Relay, note 15): the
developer's redirect that moved the verified boundary from a generated UI
down into a function-level kernel API, freeing the UX layer entirely —
with screenshots of the hand-written htmx product and the tests that prove
the freedom costs no guarantees. Acts I–III are compressed to evidence.
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
FREE = HexColor("#6C5CE7")        # violet — the free UI layer (Relay brand)
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
    c.drawString(40, 20, "Formal guardrails for LLM agents · the kernel boundary · 2026-08-14")
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
c.drawString(70, 350, "The UI is free; the rules are the law")
c.setFont(FB, 20)
c.setFillColor(HexColor("#B3A8FF"))
c.drawString(70, 315, "formal guardrails for LLM agents, act IV: the kernel boundary")
c.setFont(F, 15)
c.setFillColor(HexColor("#AFC3CF"))
c.drawString(70, 264, "Relay — a customer-support SaaS whose UI is hand-written htmx an agent may restyle at will,")
c.drawString(70, 242, "while every interaction is decided inside a verified kernel API. Guarantees lost to the freedom: zero.")
c.setFont(F, 12)
c.drawString(70, 172, "With screenshots of the running product, forged-request tests bouncing off the kernel by rule name,")
c.drawString(70, 154, "and the honest journal — including the prediction registered before the solver ran. August 2026.")
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
           "Act III built a full product (Flowdeck) to measure the developer experience. It worked — and it surfaced "
           "the tension this deck resolves: who writes the UI?", size=11.5, width=880, color=ACCENT_D)
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
image_slide("Act III · what “derived UI” looks like", "Flowdeck's reflected board — now officially scaffolding",
            "board-tom.png",
            "Board columns = the lifecycle; cards = the read rule; buttons = the decision function with denying rules "
            "named. Everything on screen is a reflection of rules.yaml — which is exactly the limitation.",
            "Kept as a diagnostic (engine/ui.py serves any rule base — useful while writing rules). What it can never "
            "give a product team: custom queues, brand, workflows, information design. That requires a UI someone OWNS.")

# ----------------------------------------------------------------- slide 8
header("Act IV · the redirect", "Move the boundary down; set the UI free")
text_block(40, H - 100,
           "The developer's requirement (guardrail 10, 2026-08-14): UX customizability is crucial — the implementing "
           "agent must be free in the UI, while the interaction logic stays guarded by the rules. The verified boundary "
           "moves from “the UI is generated” to a class/function-level kernel API.",
           size=12, width=880)
layers = [
    ("FREE — app.py (hand-written htmx, ~600 lines)", FREE,
     "Queues, badges, toasts, forms, partial swaps. Agent-authored, restyled at will. Zero policy lives here — so no "
     "review of it can ever be about policy."),
    ("BOUNDARY — engine/kernel.py (+ the lint that holds it)", ACCENT_D,
     "visible / get / create / act / edit / delete — every call decided by the rule base BEFORE the store is touched; "
     "refusals are typed Denied values naming the rule; decide()/affordances() are pure queries for rendering. "
     "App code imports engine.kernel and NOTHING beneath it: python -m analysis.boundary <app> fails CI otherwise."),
    ("ANALYZED — rulesets/<app>/ (rules + frozen gate)", OK,
     "The program: allow/deny rules from tickets. Z3 reviews every change: dead rules, ∀-safety, ∃-possibility, "
     "lifecycle, frozen features with refusals by name. Unchanged from act II — the gate did not get weaker, the "
     "surface got freer."),
]
yy = H - 168
for t, col, b in layers:
    panel(40, yy - 88, 880, 88)
    c.setFillColor(col)
    c.rect(40, yy - 88, 6, 88, fill=1, stroke=0)
    c.setFont(FB, 11.5)
    c.setFillColor(col)
    c.drawString(58, yy - 20, t)
    text_block(58, yy - 36, b, size=9.6, width=840)
    yy -= 96
text_block(40, 78,
           "Why not keep the generated UI? It couples the product surface to the policy vocabulary, and it smuggles "
           "reflection into the trust story. The UI was never the thing that needed to be correct — enforcement was.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ----------------------------------------------------------------- slide 9
header("Act IV · the kernel API", "One doorway to state; refusals are values, not prose")
code_block(40, H - 96, 470, [
    ("from engine import kernel   # the app's ONLY engine import", "dim"),
    "",
    ('desk = kernel.boot("rulesets/helpdesk", "app.db",', ""),
    ('                   today="2026-08-14", seed=...)', ""),
    "",
    ("rows = desk.visible(actor)        # the read rule, applied", "ok"),
    ('row  = desk.create(actor, {"subject": "Login broken"})', ""),
    ('row  = desk.act(actor, "resolve", case_id)', ""),
    ('row  = desk.edit(actor, case_id, {"assignee": "sam"})', ""),
    ('d    = desk.decide(actor, "close", row)   # pure query', ""),
    "",
    ("try:", ""),
    ("    desk.delete(actor, case_id)", ""),
    ("except kernel.Denied as e:", ""),
    ('    e.rule.id           # "default_deny"', "fail"),
    ("    e.rule.description  # the stakeholder sentence", "fail"),
])
panel(540, 168, 380, 286)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(554, 434, "What the boundary guarantees")
bullets(554, 410, [
    "Decide, then store — never the other way. A refused mutation writes nothing.",
    "visible() IS the read rule: there is no unfiltered list to forget to filter.",
    "affordances(actor, row) returns every action with its decision — buttons, locked-lists, tooltips are one loop; presentation stays the client's business.",
    "One kernel, three adapters: the JSON API and the old generic UI were refactored onto the same instance. One enforcement path.",
    "The same 403 vocabulary end to end: ticket → rule id → solver counterexample → Denied.rule → toast.",
], 350, size=9.3, gap=6)
text_block(40, 96,
           "The kernel is ~200 domain-free lines, written once for every app on the engine. It is small enough to be the "
           "thing you verify — the production form is this API over a proven engine (Cedar's shape, note 12).",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 10
header("Act IV · edits decided twice", "Note 14's sharpest silent gap — closed at the boundary")
text_block(40, H - 100,
           "Act III's honest friction list had one silent failure mode: rules saw an edit's CURRENT fields, never the "
           "proposed values — so “move this case to another org by editing the org field” slipped past the tenancy rule. "
           "The kernel now decides every edit twice: may this actor edit this row — and may the row BECOME this?",
           size=12, width=880)
code_block(40, 356, 430, [
    ("# features.yaml — frozen gate, feat_org_walls", "dim"),
    "- {actor: dana, action: edit, expect: deny,",
    "   denied_by: org_walls,",
    "   set: {org: zephyr}}   # the tenant escape",
    "",
    ("# rules.yaml — the SAME rule that guards reads", "dim"),
    "- id: org_walls",
    "  effect: deny",
    "  when: 'actor.role == \"customer\"",
    "         and not resource.same_org'",
])
code_block(490, 356, 430, [
    ("$ pytest tests/ -q   # at the kernel, then over HTTP", "cmd"),
    (">>> desk.edit(dana, case_id, {'org': 'zephyr'})", ""),
    ("kernel.Denied: denied by org_walls", "fail"),
    (">>> desk.get(dana, case_id)['org']", ""),
    ("'acme'                    # nothing was written", "ok"),
    "",
    ("$ curl -X POST /case/7/edit -d org=zephyr  # forged", "cmd"),
    ("403 · Refused — rule org_walls               ", "fail"),
])
bullets(40, 148, [
    "The fix is 6 lines in the kernel + 9 in the pure feature executor (model and implementation must change together — exhaustive backend agreement still holds).",
    "It applies to every service on the engine at once: Flowdeck's documented “member could re-team a task” hole is retro-closed. All five frozen gates replayed green after the change.",
    "The ticket sentence became enforceable: “a case can never be moved into or out of an organization by its customers” is now a frozen gate step, expected denied_by org_walls.",
], 880, size=10.5, gap=6)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 11
header("Act IV · the boundary, held mechanically", "Bypassing the kernel is a named CI failure, not a review maybe")
text_block(40, H - 100,
           "Python has no package-private, so the boundary is held the way the frozen gate is held: mechanically, in "
           "check.sh. The lint walks the app's AST; the app must pass — and a PRESERVED bypass variant must FAIL, so the "
           "lint itself is regression-tested in both directions on every run.",
           size=12, width=880)
code_block(40, 350, 430, [
    ("# bypass_variant/sneaky_shortcut.py — never run", "dim"),
    ("# a plausible 'quick win': close stale cases in SQL", "dim"),
    "import sqlite3",
    "from engine import store",
    "",
    "def close_stale_cases(db_path):",
    "    conn = sqlite3.connect(db_path)",
    "    for row in store.list_items(conn):",
    "        conn.execute(\"UPDATE items SET",
    "          state = 'closed' WHERE id = ?\", ...)",
])
code_block(490, 350, 430, [
    ("$ python -m analysis.boundary app.py", "cmd"),
    ("BOUNDARY: ok (imports nothing beneath engine.kernel)", "ok"),
    "",
    ("$ python -m analysis.boundary bypass_variant/", "cmd"),
    ("FAIL sneaky_shortcut.py:13: imports 'sqlite3':", "fail"),
    ("     the store's substrate is beneath the boundary", "fail"),
    ("FAIL sneaky_shortcut.py:15: imports 'engine.store':", "fail"),
    ("     app code may import engine.kernel only", "fail"),
    ("BOUNDARY: FAIL (2 findings)   # check.sh REQUIRES this", "fail"),
])
bullets(40, 150, [
    "What it refuses: engine internals, sqlite3, reach-around module aliases, mangled kernel attributes. What it skips would not be quiet: three lines of ordinary Python was the whole failure mode.",
    "Honest scope (note 15): a lint plus name-mangling is not a proof. The by-construction version is a process boundary or a language with visibility (guardrail 8). Falsifier KB1: red-team it.",
], 880, size=10.5, gap=6)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 12
header("Act IV · the experiment", "Relay: a support desk, 7 tickets, round-1 green")
code_block(40, H - 96, 430, [
    ("# TICKETS.md — the product spec (excerpts)", "dim"),
    "HD-1  Customers see and touch only their own",
    "      organization's cases — reading included.",
    "HD-4  The requester's side decides whether it is",
    "      fixed: only customers reopen. Staff never.",
    "HD-5  Once the SLA due date has passed, an",
    "      ordinary agent may no longer resolve —",
    "      a breached case is resolved by a lead.",
    "HD-7  The mail robot opens cases and files",
    "      replies — and can do nothing else.",
])
code_block(490, H - 96, 430, [
    ("$ analyze rulesets/helpdesk        # round 1, 0.2 s", "cmd"),
    ("ok: all 14 rules are effectual", "ok"),
    ("ok   S1_org_isolation ... S13_mailbot_contained", "ok"),
    ("ok   P1_customers_open ... P9_staff_cross_org", "ok"),
    ("ok: 7 transitions live, gated entries respected", "ok"),
    ("ok   feat_lifecycle ... feat_mailbot  (42 steps)", "ok"),
    ("VERDICT: PASS (0 findings)", "ok"),
])
bullets(40, 268, [
    "Pre-registered predictions, both held: (a) round-1 PASS; (b) ZERO dead rules — because the five containments (nothing deleted, staff never reopen, only leads close, customers never touch staff states, robot scope) were written with NO deny rules at all. Tight allows + default-deny do the work; S-properties prove each containment universally. Act III's janitor lesson, transferred as method knowledge.",
    "Honest caveat (DEVLOG): third domain by the same author — round-1-green says the discipline transfers, not that the gate is superfluous. The same author produced two real holes one domain ago; the gate stays frozen for the author who hasn't read the DEVLOGs.",
    "Engine domain vocabulary added for Relay: 0 lines — org tenancy, assignment and SLA reused act III's projections (same_org, mine, sla_breached). The note-14 transfer-cost prediction confirmed.",
], 880, size=10, gap=7)
footer(); c.showPage()

# --------------------------------------------------------- slides 13–17: Relay
image_slide("Act IV · the product", "Nobody generated this — and nobody reviewed it for policy",
            "relay-sam-working.png",
            "The agent-written surface: dark sidebar, queue navigation with live counts, severity dots, org chips, SLA "
            "due dates. htmx partial swaps against the kernel. ~600 lines of UI in which no policy can live.",
            "python examples/helpdesk/app.py → http://127.0.0.1:8810/ — personas switchable in the sidebar; the demo "
            "desk is seeded THROUGH the kernel as the real personas, so a seed that violates policy cannot exist.")

image_slide("Act IV · UX the rules don't know about", "“SLA breached” — a queue no reflected UI could invent",
            "relay-sam-breached.png",
            "A cross-state product view (new+open+waiting, past due), with red day-counters — pure presentation over "
            "kernel.visible(), invented by the UI author because support teams triage by breach, not by lifecycle state.",
            "This is what “customizability is crucial” buys: the rule base knows states and dates; the PRODUCT decides "
            "what a queue is. The count differs per persona because visible() is the read rule.")

image_slide("Act IV · tenant walls, visibly", "Same desk, signed in as the customer: one org exists",
            "relay-dana-working.png",
            "dana (customer, acme) sees acme's single working case; zephyr's cases and counts are simply absent. "
            "org_walls is one deny rule; S1_org_isolation proves no allowed situation crosses it — the sidebar is the proof.",
            "The forged-request tests POST reads and edits on the invisible cases anyway: 403, named org_walls, "
            "nothing written (tests/test_relay.py).")

image_slide("Act IV · affordances, not permissions", "Allowed actions are buttons; refused ones tell you why",
            "relay-quinn-detail.png",
            "quinn (staff, not the assignee) gets Put-on-hold and Assign-to-me live, and one locked action: “Resolve — "
            "refused by only_assignee_resolves.” One kernel call (affordances) powers both lists; the presentation "
            "philosophy — disclosure vs. greying — is the UI author's choice.",
            "The locked entries stay pressable on purpose: the UI reflects decisions, it never makes them.")

image_slide("Act IV · a refusal, end to end", "Press the locked button anyway: the ticket sentence answers",
            "relay-denied-toast.png",
            "403 — Refused: rule only_assignee_resolves, “HD-4: a case is resolved by the agent it is assigned to; only "
            "a lead may resolve someone else's case.” Ticket → rule id → solver vocabulary → typed Denied → toast: one "
            "unbroken chain of names.",
            "htmx quirk found here: 4xx responses are not swapped by default — the honest 403 needed a one-listener "
            "opt-in. A free-layer bug, caught by a screenshot, with nothing at stake but pixels (DEVLOG).")

# ---------------------------------------------------------------- slide 18
header("Act IV · what the freedom cost", "Nothing — and the tests prove it, by forging what the UI hides")
code_block(40, H - 96, 500, [
    ("# tests/test_relay.py — the UI renders postbot no", "dim"),
    ("# buttons at all; forge the POST anyway:", "dim"),
    ('fetch(port, "POST", f"/case/{id}/act", "postbot",', ""),
    ('      body="action=triage")', ""),
    ("assert status == 403 and 'default_deny' in text", "ok"),
    "",
    ("# quinn is staff, but not the assignee:", "dim"),
    ('fetch(..., "quinn", body="action=resolve")', ""),
    ("assert 'only_assignee_resolves' in text", "ok"),
    ("assert state_unchanged                      ", "ok"),
    "",
    ("# dana forges the tenant escape over HTTP:", "dim"),
    ('fetch(..., "dana", body="org=zephyr")', ""),
    ("assert 'org_walls' in text and org == 'acme'", "ok"),
])
panel(570, 168, 350, 286)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(584, 434, "The asymmetry, measured")
bullets(584, 410, [
    "Hiding a button changes nothing: every press and every forged request is decided inside the kernel.",
    "The seed had to obey the rules too: seed case 6 breaches its SLA, so the seed script COULD NOT resolve it as the agent — it routes through the lead.",
    "The free layer's own bugs (hx-vals quoting, the 4xx swap) burned plumbing time and zero policy risk. That asymmetry is the architecture working.",
    "12 tests at three layers: model agreement (19,200 situations), kernel refusals by name, app over HTTP.",
], 320, size=9.3, gap=6)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 19
header("Act IV · sharp edges", "Kept honest — each one is a falsifier on the table")
fr = [
    ("default_deny flattens refusal UX", "Omitting provably-dead containment denies is right by the analyzer — but the robot's refusal now reads “no rule allows this” instead of a stakeholder sentence. Open idea (KB4): explain refusals by the nearest allow — “mailbot_files grants open, reply — not triage.” An explanation is a disclosure channel; org walls must apply to error messages too."),
    ("The lint is conservative, not complete", "It blocklists imports and reach-around attribute names. KB1: red-team it — if a plausible (not adversarial) bypass passes, the boundary needs AST call analysis or a process split."),
    ("Two decisions per edit ≠ transactions", "A concurrent writer between decide and write is unhandled (single SQLite connection hides it). KB3: the P3 harness pattern — real Postgres, concurrent load — applied to the kernel."),
    ("Reads may outgrow the kernel", "Aggregations, search, pagination will pressure “just open the DB read-only.” KB2: a reporting seam that still applies the read rule per row is the test of reads-as-decisions at scale."),
    ("One entity per rule base", "Relay's cases fit one rule base; case comments/attachments would force relations between ruled entities — N rule bases + client joins, or engine work."),
    ("The engine is unproven Python", "~1,900 domain-free lines taken on faith. The production form: this kernel API over a verified engine (Cedar's Lean proofs, or the track-D Dafny→Go shape) — one proof, then per-change analysis only."),
]
for i, (t, b) in enumerate(fr):
    x = [40, 490][i % 2]
    yy = (H - 96) - (i // 2) * 122
    panel(x, yy - 114, 430, 114, fill=HexColor("#F9F1EC") if i == 0 else PANEL)
    c.setFont(FB, 11)
    c.setFillColor(WARN)
    c.drawString(x + 14, yy - 19, t)
    text_block(x + 14, yy - 36, b, size=9.4, width=402)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 20
header("Scoreboard", "Five rule bases, one engine, every claim executable")
stats = [
    ("5 : 1", "services per engine — CMS, tickets, receivables, Flowdeck, "
     "Relay on ~1,900 lines of domain-free Python (kernel: 209; boundary "
     "lint: 105).", ACCENT_D),
    ("0 lines", "of domain vocabulary the engine needed for Relay — the "
     "transfer trend closed: time (~100) → relations (~60) → zero, as "
     "predicted in note 14.", OK),
    ("89,856", "situations checked exhaustively across the five services — "
     "runtime evaluation and the Z3 compilation agree on every one.", OK),
    ("2-way CI", "check.sh holds both directions: Relay's gate must PASS, "
     "the preserved bypass variant must FAIL the lint, the taskboard's "
     "round-2 draft must FAIL the frozen gate.", WARN),
]
x = 40
for n, b, col in stats:
    panel(x, 280, 205, 130)
    c.setFont(FB, 22)
    c.setFillColor(col)
    c.drawString(x + 14, 378, n)
    text_block(x + 14, 358, b, size=8.8, width=178)
    x += 225
c.setFont(FB, 12)
c.setFillColor(ACCENT_D)
c.drawString(40, 248, "Relay by the numbers — the whole product:")
bullets(40, 224, [
    "361 lines of YAML (14 rules + 13 ∀-properties + 9 ∃-witnesses + 2 gated lifecycle entries + 42 frozen feature steps) — reviewed by the solver in ~0.2 s per change.",
    "~600 lines of free htmx UI (app.py) — reviewed by nobody, for policy, ever: the boundary lint proves it cannot touch state around the kernel.",
    "12 tests across three layers; 5-stage check.sh; screenshots reproducible (screenshots.py); journal in DEVLOG.md.",
], 880, size=10.5, gap=6)
text_block(40, 110,
           "What the analyzer asks of every rule change, in seconds: dead rules · stale assumptions · ∀-safety · "
           "∃-possibility · lifecycle liveness + gated entries · frozen features with refusals by name.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 21
header("Guardrails · CLAUDE.md", "Learned the hard way — the newest one is this deck's thesis")
gr = [
    ("10 · The boundary is a kernel API, not a UI", "NEW. Rules guard interaction logic behind a function-level API; the UI above is agent-authored and free; generated UIs are scaffolding. Hold the boundary mechanically (lint), never by convention.", FREE),
    ("1 · The spec is frozen for agents", "The analyzer takes --gate from a pinned directory; agents edit rules, never the gate. Historic buggy drafts are gated forever as regressions.", ACCENT_D),
    ("2 · Gates need both directions", "Safety-only gates accept fixes that trade away liveness (“the safest system does nothing”). Every gate = safety + possibility witnesses + frozen feature runs.", ACCENT_D),
    ("3 · Gate strength beats NL steering", "Same bug, model, prompt: a stronger gate turned a partial fix into the full fix (P4). Cheaper models are fine when the gate is strong.", ACCENT_D),
    ("6 · Counterexamples are the currency", "Named and machine-readable: situation witnesses, unsat cores, denied_by 403s — now typed Denied values any UI renders its own way.", ACCENT_D),
    ("7 · Record falsified predictions", "The DEVLOGs keep wrong predictions next to the runs that killed them (act III) and pre-registered predictions next to the runs that confirmed them (act IV).", ACCENT_D),
    ("8 · Boundaries by construction", "Where the language allows: capability tokens, typestate. Where it doesn't (Python): name-mangling + a lint whose failure is named — and the honesty that this is not a proof.", ACCENT_D),
    ("5 · Translate / validate split", "LLM translation of NL→rules is unsound — always followed by a sound solver step. Humans review rules sentence-by-sentence, never agent edits.", ACCENT_D),
]
xs2, yw = [40, 500], 420
yy0 = H - 108
for i, (t, b, col) in enumerate(gr):
    x = xs2[i % 2]
    yy = yy0 - (i // 2) * 96
    panel(x, yy - 88, yw, 88, fill=HexColor("#F3F0FF") if i == 0 else PANEL)
    c.setFont(FB, 11)
    c.setFillColor(col)
    c.drawString(x + 14, yy - 20, t)
    text_block(x + 14, yy - 36, b, size=9.4, width=yw - 28)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 22
header("Roadmap", "Falsifiers on the table")
c.setFont(FB, 13)
c.setFillColor(OK)
c.drawString(40, H - 110, "Held so far")
bullets(40, H - 134, [
    "RB1 (tickets land as rule diffs): held four times, and the cost curve closed — imports 0, receivables ~100 (time), Flowdeck ~60 (relations), Relay 0. Note 14's zero-lines prediction confirmed.",
    "DX verdict (notes 14–15): the loop beats conventional development for the policy-shaped core, and the redirect resolved its biggest tension — product UX is now free without weakening a single gate.",
], 880, size=10.5, gap=6)
c.setFont(FB, 13)
c.setFillColor(ACCENT_D)
c.drawString(40, H - 240, "Next")
bullets(40, H - 264, [
    "KB1 — red-team the boundary lint: a plausible bypass that passes forces AST call analysis or a process split. KB2 — a reporting/read seam (search, aggregation) that still applies the read rule per row.",
    "KB3 — the P3 harness against the kernel: concurrent writers between decide and write, on real Postgres. KB4 — nearest-allow refusal explanations that do not leak across tenants.",
    "DX1 — an outside developer ships a ruled app (rules + free htmx UI) from tickets in under a day. DX2 — the same tickets implemented conventionally by a strong LLM: does it contain the interaction holes the gates caught?",
    "RB3 — ticket→rule-diff vs ticket→handler fidelity, measured. RB4 — the Quint temporal twin (races). P8 — the same rules as Cedar policies. P9 — the invariant→Postgres-constraint compiler nobody has built.",
], 880, size=10.5, gap=6)
c.setFont(FB, 12)
c.setFillColor(MUTED)
c.drawString(40, 108, "Parked (consciously, with reasons recorded)")
text_block(40, 90,
           "Alloy (Z3 covers it) · Quint→Rust codegen (no tooling) · Kani until unbounded domains arrive · Verus (proxy-blocked; Dafny stands in).",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 23
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
    "Split the app at a kernel API: below it, 361 lines of solver-reviewed rules that hold the product",
    "to its tickets in every one of 19,200 situations; above it, a hand-written UI an agent may redesign",
    "at will — because the tests forge every request the UI hides, and the kernel refuses each one by name.",
]):
    c.drawString(70, 350 - i * 28, ln)
c.setFont(F, 11.5)
c.setFillColor(HexColor("#8FA5B5"))
c.drawString(70, 210, "Run it: examples/helpdesk/check.sh · python examples/helpdesk/app.py → http://127.0.0.1:8810/")
c.drawString(70, 190, "Read it: examples/helpdesk/DEVLOG.md (the journal) · research/15-kernel-boundary-free-ui.md")
c.drawString(70, 170, "The stack beneath: notes 13–14 (rules as the program, the DX study) · 09–12 (proof escalation) · p1–p7")
footer(title_page=True)
c.showPage()

c.save()
