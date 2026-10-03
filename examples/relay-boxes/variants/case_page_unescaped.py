# (appended to the generated module by check.sh — this later def replaces the box)
# PRESERVED BAD VARIANT — well-typed, plausible, and an XSS hole: it
# interpolates user text without the `esc` capability. Types cannot see
# this; the reviewed hostile-text test must.


def case_page(case_id: int, notice: Notice | None, desk: DeskReader,
              esc: Escape) -> str:
    case = desk.case(case_id)
    if not isinstance(case, Case):
        return "<p>This case is not available.</p>"
    rows = "".join(f"<li>{c.author}: {c.body}</li>" for c in desk.thread(case_id))
    return f"<h1>{case.subject}</h1><p>{case.org}</p><ul>{rows}</ul>"
