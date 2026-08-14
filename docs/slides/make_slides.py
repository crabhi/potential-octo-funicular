#!/usr/bin/env python3
"""Generate the project slide deck (PDF, 16:9 landscape).

Audience: engineers without prior formal-verification background.
Regenerated ground-up from the current repository state (see CLAUDE.md
workflow rule: the deck always describes the repo, never accretes).
This edition leads with act V (multi-entity rules, note 16): the
developer's directive that rules must cover multiple entity types —
comments and attachments are context-sensitive — and what it took:
child entities with parent context in one rule base, the kernel doing
the join, the analyzer running per entity, and Relay growing a ruled
thread + evidence with the screenshots and forged-request tests to
prove it. Acts I–IV are compressed to evidence.
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
    c.drawString(40, 20, "Formal guardrails for LLM agents · multi-entity rules · 2026-08-14")
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
c.drawString(70, 350, "One rule base, three entity types")
c.setFont(FB, 20)
c.setFillColor(HexColor("#B3A8FF"))
c.drawString(70, 315, "formal guardrails for LLM agents, act V: rules across entities")
c.setFont(F, 15)
c.setFillColor(HexColor("#AFC3CF"))
c.drawString(70, 264, "Relay's cases now carry ruled threads and evidence: a comment's legality depends on its case's")
c.drawString(70, 242, "live state and org — decided in the kernel, which joins the parent. The client never computes context.")
c.setFont(F, 12)
c.drawString(70, 172, "With pre-registered predictions, one un-predicted fail-open lesson, screenshots of internal notes")
c.drawString(70, 154, "that do not exist for customers, and forged requests refused by name. August 2026.")
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
           "Act III built a full product (Flowdeck) to measure the developer experience — and surfaced the UI tension. "
           "Act IV resolved it with the kernel boundary. Act V, this deck's lead, is what came next.",
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
image_slide("Act IV · the product", "Nobody generated this — and nobody reviewed it for policy",
            "relay-sam-working.png",
            "The agent-written surface: dark sidebar, queue navigation with live per-persona counts (the list IS the "
            "read rule), severity dots, org chips, SLA badges. htmx partial swaps against the kernel — ~760 lines of UI "
            "in which no policy can live.",
            "python examples/helpdesk/app.py → http://127.0.0.1:8810/ — the demo desk is seeded THROUGH the kernel as "
            "the real personas, so a seed that violates policy cannot exist (the breached seed case had to route its "
            "resolution through the lead).")

# ----------------------------------------------------------------- slide 9
image_slide("Act IV · a refusal, end to end", "Press the locked button anyway: the ticket sentence answers",
            "relay-denied-toast.png",
            "quinn (staff, not the assignee) presses the locked Resolve: 403 — Refused: rule only_assignee_resolves, "
            "“HD-4: a case is resolved by the agent it is assigned to; only a lead may resolve someone else's case.” "
            "Ticket → rule id → solver vocabulary → typed Denied → toast: one unbroken chain of names.",
            "Affordances, not permissions: one kernel call powers the allowed buttons AND the locked disclosures; the "
            "presentation philosophy is the UI author's choice, the decision never is.")

# ---------------------------------------------------------------- slide 10
header("Act V · the redirect", "“Comments and attachments are context-sensitive” — the wall comes down")
panel(40, H - 226, 430, 130, fill=HexColor("#F9F1EC"))
c.setFont(FB, 11)
c.setFillColor(WARN)
c.drawString(54, H - 116, "The previous deck's own sharp-edge slide:")
text_block(54, H - 134,
           "“One entity per rule base — Relay's cases fit one rule base; case "
           "comments/attachments would force relations between ruled entities "
           "— N rule bases + client joins, or engine work.”",
           size=10, width=402, font=FI)
text_block(54, H - 196,
           "The developer picked: engine work. “Rules covering multiple "
           "entity types is a must.”", size=10, width=402, color=WARN)
panel(490, H - 226, 430, 130)
c.setFont(FB, 11)
c.setFillColor(ACCENT_D)
c.drawString(504, H - 116, "Why client joins were never an option")
text_block(504, H - 134,
           "Whoever computes “may dana post here?” from two rule bases plus a "
           "join IS an enforcement point — and guardrail 10 exists to keep "
           "the UI from ever being one. If relations live in the client, the "
           "boundary is gone.",
           size=10, width=402)
y = text_block(40, H - 252,
               "What “context-sensitive” means concretely: a comment's legality depends on the CASE it belongs to — its "
               "live state and its org. “No comments on a closed case”, “the org wall extends to the thread”, “internal "
               "notes are staff-only” are rules about a relation between two entity types:",
               size=11.5, width=880)
code_block(40, y - 8, 880, [
    ("- id: sealed_thread                            - id: org_walls_thread", ""),
    ("  entity: [comment, attachment]                  entity: [comment, attachment]", ""),
    ("  effect: deny                                    effect: deny", ""),
    ("  when: 'parent.state == \"closed\"                 when: 'actor.role == \"customer\"", ""),
    ("         and action != \"read\"'                          and not parent.same_org'", ""),
], size=9.4)
text_block(40, 74,
           "parent.state and parent.same_org are the child's window onto its parent — the whole relation mechanism.",
           size=10.5, width=880, color=ACCENT_D)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 11
header("Act V · the design", "Children declare a window onto their parent; the kernel does the join")
code_block(40, H - 96, 470, [
    ("# rules.yaml — ONE rule base, three entity types", "dim"),
    ("entity: case            # the root, unchanged", ""),
    ("children:", ""),
    ("  - entity: comment", ""),
    ("    states: [posted, redacted]", ""),
    ("    fields: [body, internal]", ""),
    ("    context: [state, same_org]   # opt-in, per atom", "cmd"),
    ("    lifecycle:", ""),
    ("      transitions:", ""),
    ("        - {action: post,   from: none,   to: posted}", ""),
    ("        - {action: redact, from: posted, to: redacted}", ""),
    ("  - entity: attachment", ""),
    ("    states: [attached, removed]", ""),
    ("    fields: [filename]", ""),
    ("    context: [state, same_org]", ""),
], size=8.2)
panel(540, 150, 380, 306)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(554, 436, "The mechanism, in four facts")
bullets(554, 412, [
    "Each entity gets its OWN situation vocabulary; `context:` imports parent atoms one by one (every boolean doubles the space — the budget discipline survives): parent.state, parent.is_author, any parent projection.",
    "Rules and gate properties carry an entity: tag, defaulting to the root — growing children touched ZERO existing rules and zero frozen gate lines.",
    "The kernel joins the live parent row into every child decision: create(actor, fields, entity=\"comment\", parent_id=case). The client cannot compute context wrong because it never computes it.",
    "Deliberate limits, stated up front: one level of nesting, one parent per child, NO aggregates (“close only if no open comments” is not expressible — see the sharp edges).",
], 350, size=9.2, gap=6)
text_block(40, 96,
           "Single-entity rule bases are the unchanged degenerate case: cms, tickets, receivables and Flowdeck replayed "
           "green on the rewritten engine BEFORE anything new was written. Back-compat proven, not assumed.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 12
header("Act V · one atom seals everything", "Close the case; the very next post meets the deny — live")
code_block(40, H - 96, 500, [
    ("# the same call, before and after the case closes", "dim"),
    (">>> desk.create(priya, {\"body\": \"confirmed fixed\"},", ""),
    ("...     entity=\"comment\", parent_id=case_id)", ""),
    ("{'id': 7, 'state': 'posted', ...}     # resolved: talks", "ok"),
    "",
    (">>> desk.act(noor, \"close\", case_id)  # the QA step", ""),
    (">>> desk.create(priya, {\"body\": \"one more thing\"},", ""),
    ("...     entity=\"comment\", parent_id=case_id)", ""),
    ("kernel.Denied: denied by sealed_thread", "fail"),
    "",
    (">>> desk.visible(priya, entity=\"comment\",", ""),
    ("...              parent_id=case_id)", ""),
    ("[<the whole thread>]   # readable forever (P13)", "ok"),
], size=8.4)
panel(570, 200, 350, 254)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(584, 432, "Why this is the interesting part")
bullets(584, 408, [
    "One deny, two entities, four verbs sealed: posting, redaction, attaching, removal — and reads deliberately NOT.",
    "The industry alternative is a `sealed` flag denormalized onto every child row, plus the sync bugs it breeds. Here there is nothing to sync: child rules read the LIVE parent.",
    "A resolved case still talks (the customer may dispute, HD-4) but takes no new evidence (fresh_evidence_only) — two different context rules, one vocabulary.",
    "All of it frozen: feat_sealed_evidence replays 19 steps through resolve → close, refusals expected by name.",
], 320, size=9.2, gap=6)
text_block(40, 120,
           "The seed data lives under the same law: the demo threads are written BEFORE their case closes, because "
           "sealed_thread refuses late seed comments exactly as it refuses late real ones. The same seal meets forged "
           "HTTP on slide 18: POST into the closed case → 403, sealed_thread, nothing written.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 13
header("Act V · the analyzer, per entity", "Round 2: predictions registered first — then PASS")
code_block(40, H - 96, 500, [
    ("$ analyze rulesets/helpdesk          # round 2, ~0.4 s", "cmd"),
    ("rules: 33 (16 deny, 17 allow) | entities: 3", ""),
    ("situation space: 37200 (case: 19200,", ""),
    ("    comment: 12000, attachment: 6000)", ""),
    ("ok: all 33 rules are effectual", "ok"),
    ("ok  [comment]    S14_threads_follow_org_walls ...", "ok"),
    ("ok  [comment]    S17_comments_immutable (no deny rule)", "ok"),
    ("ok  [attachment] S22_evidence_only_while_working ...", "ok"),
    ("ok  [comment] P13_thread_outlives_closure", "ok"),
    ("    witness: {action: read, parent.state: closed, ...}", "dim"),
    ("ok: 11 transitions live, all 9 states reachable,", "ok"),
    ("    gated entries respected", "ok"),
    ("ok  feat_thread (14)  feat_sealed_evidence (19) ...", "ok"),
    ("VERDICT: PASS (0 findings)", "ok"),
], size=8.2)
panel(570, 172, 350, 284)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(584, 434, "Pre-registered in the DEVLOG — all held")
bullets(584, 410, [
    "P-c: zero dead rules again. The new containments (comments never edited, only leads redact, the robot never reads back, removal is author-or-lead) again have NO deny rules — S17/S18/S19/S23/S24/S26 prove each universally.",
    "P-d: the 13 case ∀-properties and 9 case witnesses are byte-identical and still green.",
    "P-e: engine domain lines for the thread + evidence: 0 — nothing in the engine says comment or seal.",
    "Unpredicted gain: P13's witness — the solver picked a CLOSED parent to prove the record survives. “Readable after the parent moved on” used to be unstatable; parent.state made it a one-liner.",
], 320, size=9.0, gap=6)
text_block(40, 112,
           "Every check runs per entity, in each entity's own situation space — a child's includes every parent-context "
           "combination a rule could ever see. Two rounds, two green gates, five predictions held — and the one lesson "
           "nobody predicted is the next slide.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 14
header("Act V · the un-predicted lesson", "Untagged global denies fail OPEN — caught, tagged, pinned")
code_block(40, H - 96, 430, [
    ("# the ONE existing rule this episode touched:", "dim"),
    ("- id: deny_inactive", ""),
    ("  description: \"A deactivated account can", ""),
    ("    do nothing at all.\"", ""),
    ("  entity: [case, comment, attachment]   # ← new", "cmd"),
    ("  effect: deny", ""),
    ("  when: 'not actor.active'", ""),
    "",
    ("# pinned the same hour, per child:", "dim"),
    ("- id: S28_inactive_locked_out_of_threads", ""),
    ("  entity: comment", ""),
    ("  requires: 'actor.active'", ""),
], size=8.6)
code_block(490, H - 96, 430, [
    ("$ # verification: untag the deny, re-run the gate", "cmd"),
    ("FAIL [comment]    S28_inactive_locked_out_of_threads", "fail"),
    ("     counterexample: {role: customer, action: post,", "dim"),
    ("      active: false, parent.same_org: true, ...}", "dim"),
    ("FAIL [attachment] S29_inactive_locked_out_of_evidence", "fail"),
    ("FAIL feat_thread: step 6 (lex read):", "fail"),
    ("     expected deny by deny_inactive, got allow", "fail"),
    ("VERDICT: FAIL (3 findings)", "fail"),
], dark=True, size=8.4)
bullets(40, 226, [
    "Untagged rules apply to the ROOT only. That default fails SAFE for allows (a child grants nothing by silence) — and fails OPEN for global denies: without the tag, a deactivated customer could have posted comments.",
    "The fix is one line; the lesson is mechanical: S28/S29 joined the gate, and the negative direction was verified by temporarily untagging the rule — the analyzer produced exactly the counterexamples the bug would have shipped.",
    "Recorded as guardrail 11(a) and falsifier ME-5: an actor-only deny not tagged for every entity deserves a load-time warning. This slide exists because guardrail 7 says falsified assumptions get recorded, not smoothed over.",
], 880, size=10.2, gap=6)
footer(); c.showPage()

# --------------------------------------------------------- slides 15–17: Relay
image_slide("Act V · the thread, as staff", "sam sees THREAD (3): the internal note, amber and labeled",
            "relay-sam-thread.png",
            "The thread renders kernel lists: dana's report, sam's internal note (“Suspect SAML clock skew…”), the "
            "robot's filed email. The internal checkbox next to Post is shown to staff as a presentation choice — the "
            "kernel, not the checkbox, is what keeps customers out.",
            "Every comment card, tag and button comes from kernel.visible/affordances(entity=\"comment\") — the UI "
            "invented the layout, the rules decided the content.")

image_slide("Act V · the same case, as the customer", "dana sees THREAD (2): the internal note does not exist",
            "relay-dana-thread.png",
            "Same case, same thread — one comment fewer, no internal toggle. Not CSS hiding: visible() never returned "
            "the note, get() by forged id raises Denied(internal_is_staff_only), and the forged POST with internal=yes "
            "comes back 403. S15 proves no allowed action ever touches an internal note outside staff.",
            "The count in the heading is the read rule made visible: THREAD (3) vs THREAD (2) is the whole "
            "architecture in two characters.")

image_slide("Act V · the sealed record", "A closed case: everything readable, nothing changeable — by rule",
            "relay-sealed-record.png",
            "Case #6 as dana: the evidence renders (welcome_email.png), and both forms are replaced by the sealing "
            "rule's name — “posting is refused right now by sealed_thread”, “new evidence is refused right now by "
            "sealed_thread”. THREAD (0) is itself correct: the only comment is a lead's internal note, invisible to "
            "customers even in the record.",
            "S16/S25 prove the seal universally; P13 proves the record stays readable. The seed had to write this "
            "thread BEFORE closing the case — sealed_thread refuses late seed data exactly as it refuses late users.")

# ---------------------------------------------------------------- slide 18
header("Act V · forged child requests", "The internal flag, the robot's redact, the late post: 403 by name")
code_block(40, H - 96, 500, [
    ("# tests/test_relay.py — forge what the UI never renders", "dim"),
    ("# dana is shown no internal checkbox — send the field:", "dim"),
    ("fetch(\"POST\", f\"/case/{id}/comment\", \"dana\",", ""),
    ("      body=\"body=sneaky&internal=yes\")", ""),
    ("assert 403 and 'internal_is_staff_only'", "ok"),
    "",
    ("# the robot forges a redact it was never shown:", "dim"),
    ("fetch(\"POST\", f\"/comment/{cid}/act\", \"postbot\",", ""),
    ("      body=\"action=redact\")", ""),
    ("assert 403 and 'default_deny'", "ok"),
    "",
    ("# posting into the seed's CLOSED case:", "dim"),
    ("fetch(\"POST\", f\"/case/{closed}/attach\", \"dana\",", ""),
    ("      body=\"filename=late.log\")", ""),
    ("assert 403 and 'sealed_thread'", "ok"),
], size=8.4)
panel(570, 208, 350, 248)
c.setFont(FB, 11.5)
c.setFillColor(ACCENT_D)
c.drawString(584, 434, "Three layers, one vocabulary")
bullets(584, 410, [
    "Model: exhaustive two-backend agreement now spans all three entities — 37,200 situations, every rule, both the runtime evaluator and the Z3 compilation.",
    "Kernel: internal notes absent from customers' lists AND refused by forged id; org walls via the parent; live sealing on close; author-or-lead removal; robot contained on children.",
    "HTTP: the forged requests left — all 403, all naming the rule, nothing written. 19 tests; check.sh runs all of it plus the gate and the boundary lint in both directions.",
], 320, size=9.2, gap=6)
text_block(40, 122,
           "This suite is why the UI's freedom costs nothing: what the client never renders, the kernel still refuses — "
           "under the same rule id the ticket, the gate, the solver counterexample and the toast all use.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 19
header("Act V · sharp edges", "Kept honest — each one is a falsifier with a design attached")
fr = [
    ("Aggregates are not expressible (ME-1)", "“Close only if no open comments” needs a parent rule over child sets. An aggregate atom is NOT a free boolean — it couples the parent's space to the child rules (a frame problem), so this is genuinely hard, not missing syntax. Sound cut when a ticket forces it: kernel-computed aggregate projections, runtime-sound, analyzer-conservative."),
    ("Parent-delete cascades skip child rules (ME-6)", "Deleting a parent removes children WITHOUT consulting their delete rules — a child's immortality is only as strong as its parent's, and the per-entity gate cannot see that path. Pinned by an engine test; unreachable in Relay (nothing deletes). Fix candidates: cascade-decides, or a load-time compatibility check."),
    ("Field-level visibility (ME-3)", "A redacted comment stays a readable row; the tombstone is the UI's choice — a rude free UI could render the body. Rules cannot say “readable except this field.” Moving that inside the boundary costs per-field read atoms."),
    ("Depth and polymorphism (ME-2)", "Attachments on comments (two levels), reactions on either (two parents). The context mechanism composes on paper; the space budget and the kernel's join path are where it may crack."),
    ("The join under load (ME-4)", "Child visible() loads parent rows — cached per call, still N+1-shaped. Folds into KB2: a reporting seam that applies the read rule per row at SQL speed."),
    ("The fail-open lint (ME-5)", "An actor-only deny not tagged for every entity deserves a load-time warning — slide 14's bug, caught before it ships. Cheap, mechanical, unbuilt."),
]
for i, (t, b) in enumerate(fr):
    x = [40, 490][i % 2]
    yy = (H - 96) - (i // 2) * 122
    panel(x, yy - 114, 430, 114, fill=HexColor("#F9F1EC") if i < 2 else PANEL)
    c.setFont(FB, 11)
    c.setFillColor(WARN)
    c.drawString(x + 14, yy - 19, t)
    text_block(x + 14, yy - 36, b, size=9.1, width=402)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 20
header("Scoreboard", "Five rule bases, one engine, every claim executable")
stats = [
    ("5 : 1", "services per engine — CMS, tickets, receivables, Flowdeck, "
     "Relay on ~2,300 lines of domain-free Python (rule base 456, kernel "
     "291, analyzer 351, lint 105).", ACCENT_D),
    ("3 entities", "in one rule base — case, comment, attachment. Engine "
     "domain vocabulary added for the thread + evidence: 0 lines, the "
     "second zero in a row.", FREE),
    ("107,856", "situations checked exhaustively across the five services — "
     "runtime evaluation and the Z3 compilation agree on every one "
     "(Relay alone: 37,200 over three entities).", OK),
    ("2-way CI", "check.sh holds both directions: Relay's gate must PASS, "
     "the preserved bypass variant must FAIL the lint, the taskboard's "
     "round-2 draft must FAIL the frozen gate.", WARN),
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
c.drawString(40, 248, "Relay by the numbers — the whole product:")
bullets(40, 224, [
    "721 lines of YAML (33 rules + 29 ∀-properties + 16 ∃-witnesses + 4 gated lifecycle entries + 75 frozen feature steps across 7 features) — reviewed by the solver in ~0.4 s per change.",
    "764 lines of free htmx UI (app.py) — reviewed by nobody, for policy, ever: the boundary lint proves it cannot touch state around the kernel.",
    "19 tests across three layers; 5-stage check.sh; 8 reproducible screenshots (screenshots.py); journal with pre-registered predictions in DEVLOG.md.",
], 880, size=10.5, gap=6)
text_block(40, 108,
           "What the analyzer asks of every rule change, in seconds, per entity: dead rules · stale assumptions · "
           "∀-safety · ∃-possibility · lifecycle liveness + gated entries · frozen features with refusals by name.",
           size=10.5, width=880, color=MUTED)
footer(); c.showPage()

# ---------------------------------------------------------------- slide 21
header("Guardrails · CLAUDE.md", "Learned the hard way — the newest one is this deck's thesis")
gr = [
    ("11 · Relations are engine work, never client joins", "NEW. Child entities import parent context (parent.state, parent projections); the kernel joins the live parent into every child decision. Sharp edges kept: untagged global denies fail OPEN (tag + pin them); cascades skip child delete rules.", FREE),
    ("10 · The boundary is a kernel API, not a UI", "Rules guard interaction logic behind a function-level API; the UI above is agent-authored and free; generated UIs are scaffolding. Hold the boundary mechanically (lint), never by convention.", FREE),
    ("1 · The spec is frozen for agents", "The analyzer takes --gate from a pinned directory; agents edit rules, never the gate. Historic buggy drafts are gated forever as regressions.", ACCENT_D),
    ("2 · Gates need both directions", "Safety-only gates accept fixes that trade away liveness (“the safest system does nothing”). Every gate = safety + possibility witnesses + frozen feature runs.", ACCENT_D),
    ("3 · Gate strength beats NL steering", "Same bug, model, prompt: a stronger gate turned a partial fix into the full fix (P4). Cheaper models are fine when the gate is strong.", ACCENT_D),
    ("6 · Counterexamples are the currency", "Named and machine-readable: situation witnesses, unsat cores, denied_by 403s — typed Denied values any UI renders its own way.", ACCENT_D),
    ("7 · Record falsified predictions", "The DEVLOGs keep wrong predictions next to the runs that killed them, pre-registered predictions next to the runs that confirmed them — and slide 14's un-predicted lesson in between.", ACCENT_D),
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

# ---------------------------------------------------------------- slide 22
header("Roadmap", "Falsifiers on the table")
c.setFont(FB, 13)
c.setFillColor(OK)
c.drawString(40, H - 110, "Held so far")
bullets(40, H - 134, [
    "RB1 (tickets land as rule diffs): held five times, and the cost curve stayed closed — imports 0, receivables ~100 (time), Flowdeck ~60 (relations), Relay 0, Relay's thread + evidence 0 again.",
    "The one-entity wall came down as engine work with zero existing rules or gate lines weakened — and both multi-entity analyzer rounds were PASS with predictions pre-registered (plus one honest un-predicted lesson, slide 14).",
], 880, size=10.5, gap=6)
c.setFont(FB, 13)
c.setFillColor(ACCENT_D)
c.drawString(40, H - 250, "Next")
bullets(40, H - 274, [
    "ME-1 — aggregates, when a ticket forces them: kernel-computed aggregate projections, with the analyzer's conservatism stated. ME-6 — cascade-decides (parent delete consults child delete rules) or the load-time check.",
    "KB1 — red-team the boundary lint. KB2/ME-4 — a reporting/read seam (search, aggregation, pagination) that still applies the read rule per row. KB3 — concurrent writers between decide and write, on real Postgres (the P3 harness). KB4 — nearest-allow refusal explanations that do not leak across tenants.",
    "DX1 — an outside developer ships a ruled app (rules + free htmx UI) from tickets in under a day. DX2 — the same tickets implemented conventionally by a strong LLM: does it contain the interaction holes the gates caught?",
    "RB3 — ticket→rule-diff vs ticket→handler fidelity, measured. P8 — the same rules as Cedar policies. P9 — the invariant→Postgres-constraint compiler nobody has built.",
], 880, size=10.5, gap=6)
c.setFont(FB, 12)
c.setFillColor(MUTED)
c.drawString(40, 106, "Parked (consciously, with reasons recorded)")
text_block(40, 88,
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
    "One rule base now rules the whole product — cases, comments, attachments — because a child's rules",
    "see its parent's live state, and the kernel joins that parent into every decision: “a closed case seals",
    "its thread” is law checked in all 37,200 situations, not a flag the UI remembers to sync.",
]):
    c.drawString(70, 350 - i * 28, ln)
c.setFont(F, 11.5)
c.setFillColor(HexColor("#8FA5B5"))
c.drawString(70, 210, "Run it: examples/helpdesk/check.sh · python examples/helpdesk/app.py → http://127.0.0.1:8810/")
c.drawString(70, 190, "Read it: examples/helpdesk/DEVLOG.md · research/16-multi-entity-rules.md (and 15, the boundary beneath)")
c.drawString(70, 170, "The stack beneath: notes 13–14 (rules as the program, the DX study) · 09–12 (proof escalation) · p1–p7")
footer(title_page=True)
c.showPage()

c.save()
