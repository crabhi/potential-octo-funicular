# Flowdeck — the ticket pack (the product spec, as a PM would write it)

A small multi-tenant team kanban SaaS. These seven tickets are the entire
product definition; the rule base translates them sentence by sentence.
This file is the *source* text — every rule and every gate property in
`rulesets/taskboard/` carries the ticket it came from.

**TB-1 · Teams and privacy.** Flowdeck serves multiple teams. A team's
board is completely invisible to every other team — reading included.
Members and leads only ever act inside their own team, and a task can only
be created *into* the team of the person creating it. Site staff (admin)
can see and support everything, but the teams' work is the teams' own:
staff never decides reviews.

**TB-2 · The kanban flow.** A task moves `backlog → in progress →
in review → done`, and finished work is eventually `archived`. Tasks are
created into the backlog and must have a title. "Done" may only ever be
reached through an approved review — no shortcuts, ever, including future
features.

**TB-3 · The working agreement.** Only the person a task is assigned to
may start it and submit it for review. No work starts without an estimate
— planning is not optional.

**TB-4 · Review integrity.** Only team leads decide reviews: approve, or
send the task back with remarks. Nobody may approve a task they did
themselves — not even a lead, not even staff. While a task is under
review, its content is sealed: no edits until the review is decided.

**TB-5 · The record.** Done and archived tasks are the team's history:
read-only forever (archiving a done task is the one exception). Nothing is
ever deleted, by anyone. Deletion is not a feature.

**TB-6 · The janitor.** A platform bot archives stale done tasks — those
past their due date. The janitor must not be able to do anything else, and
it must never archive a task before its due date has passed. Every team
retains the right to archive manually (leads), at any time.

**TB-7 · Deactivation.** A deactivated account can do nothing at all,
whatever its role or team.
