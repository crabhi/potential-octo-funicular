"""Relay — a customer-support helpdesk (tickets HD-1…HD-9, ../../TICKETS.md).

REVIEWED code, organised by business area:

    people      who uses Relay (roles, actors)
    policy      refusals as values, the guard-rule registry, deny_inactive
    cases       HD-1…HD-6: the case — model + transitions, rules, queues, pages
    thread      HD-8/9: the discussion thread and the evidence of a case
    mail        HD-7: the mail robot — interpreting inbound email, the gateway
    kernel      the only owner of state; DeskReader, its read-only face
    web         the HTTP front: routing, layout, the server, the demo seed

Every black box declared here has its body in the mirror package
`generated.relay.*` (src/generated/relay/…), generated and never reviewed.
"""
