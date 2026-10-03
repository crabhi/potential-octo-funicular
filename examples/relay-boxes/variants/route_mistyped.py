# (appended to the generated module by check.sh — this later def replaces the box)
# PRESERVED BAD VARIANT — a plausible "simplification" an agent might make:
# return a loose dict instead of the reviewed Route union. ty inside Monty
# must refuse it at stage 5 of the gate, before it ever runs.


def route(req: HttpRequest) -> Route:
    if req.path == "/":
        return {"view": "queue", "queue": req.query.get("q", "inbox")}
    return NotFound()
