# Relay — product tickets

Relay is a customer-support helpdesk: customer organizations open cases,
the vendor's support staff work them. These seven tickets are the product
spec, written by a product owner in plain English. `rulesets/helpdesk/`
is their translation; every rule and gate property names its ticket.

This example exists to test **guardrail 10**: the rules guard the
interaction logic behind a function-level kernel API, and the UI on top
(`app.py`, hand-written htmx) is deliberately free — custom queues,
custom badges, custom flows the generic UI could never invent.

---

**HD-1 — Organizations are walls.**
Customers belong to an organization. A customer sees and touches only
their own organization's cases — reading included. Everyone in the org
can follow every case of the org (support is a team sport on the
customer side too). The public sees nothing. Our support staff (agents
and team leads) serve every organization.

**HD-2 — Opening and maintaining cases.**
Customers open cases; a case must have a subject. New cases land in the
inbox ("new"). Customers may edit their org's cases while they are being
worked — but never once a case is resolved or closed.

**HD-3 — The staff workflow.**
Agents triage new cases into the working queue, may put a working case
on hold waiting for the customer, and resolve. Customers never move
cases through staff states — a customer reply is its own thing: it pulls
a waiting case back into the working queue.

**HD-4 — Who resolves, who reopens.**
A case is resolved by the agent it is assigned to; a lead may resolve
anything. The requester's side decides whether it is actually fixed:
only customers reopen a resolved case. Staff never reopen — resolving
your own reopened dispute quietly is exactly the loop we refuse to
build.

**HD-5 — The SLA is not decoration.**
A case can carry an SLA due date. Once that date has passed, an
ordinary agent may no longer resolve the case — a breached case is
resolved by a lead, so every breach gets senior eyes.

**HD-6 — Closed means closed.**
A resolved case is closed by a lead (that is the QA step). Closed cases
are the support record: read-only forever, for everyone. Nothing in
Relay is ever deleted, by anyone.

**HD-7 — The mail robot.**
Inbound email becomes cases through a robot account. The robot opens
cases and files customer replies — and can do nothing else. If its
credential leaks, that is the entire blast radius.

**HD-8 — The case thread.**
Every case carries a discussion thread. Whoever follows a case can
comment on it: customers on their org's cases, staff everywhere, and the
mail robot files inbound email bodies as comments. A comment needs a
body. Staff can mark a comment *internal* — internal notes never reach
customers (or the robot), in any way. What was said is what was said:
comments are never edited; if something must disappear, a lead redacts
the comment and the redaction itself stays on the record. Closing the
case seals its thread — nothing new is said, nothing is redacted — but
the whole thread stays readable forever: the thread IS the record.

**HD-9 — Evidence.**
Files are attached to a case while it is being worked (new, open or
waiting): customers on their org's cases, staff everywhere, the robot
from email. An attachment needs a filename. A resolved or closed case
takes no new evidence — dispute the resolution first (HD-4). A mistaken
upload is *removed* by the person who attached it or by a lead — removal
keeps the tombstone, because nothing in Relay is ever deleted (HD-6) —
and a closed case seals its attachments exactly like its thread.
