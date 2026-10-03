"""REVIEWED — the thread's and the evidence's states (HD-8/9): both keep
tombstones, nothing is deleted."""

from __future__ import annotations

from boxkit import Lifecycle, T
from relay.thread.model import AttachmentState, CommentState

COMMENT = Lifecycle("comment", CommentState, initial="posted",
                    terminal=("redacted",), transitions=[
    T("redact", "posted", "redacted"),      # HD-8: the tombstone stays
])


ATTACHMENT = Lifecycle("attachment", AttachmentState, initial="attached",
                       terminal=("removed",), transitions=[
    T("remove", "attached", "removed"),     # HD-9: the tombstone stays
])


COMMENT_ACTIONS = ("post", "read", *COMMENT.actions)
ATTACHMENT_ACTIONS = ("attach", "read", *ATTACHMENT.actions)
