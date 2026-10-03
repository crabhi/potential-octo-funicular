"""Generated, additive tests pinning the `intake_email` description."""
from __future__ import annotations

import pytest

from relay.cases.model import CaseDraft
from relay.mail.intake import intake_email
from relay.mail.model import Email, MailBounce, MailNewCase, MailReply

DIRECTORY = {"dana@acme.test": "acme", "omar@zephyr.test": "zephyr"}


def org_of(sender):
    return DIRECTORY.get(sender)


def mail(subject="Help", body="body", sender="dana@acme.test", attachments=()):
    return Email(sender, subject, body, list(attachments))


def run(m):
    return intake_email(m, org_of)


# --------------------------------------------------------------------- reply

def test_reply_basic():
    r = run(mail(subject="Re: Login [#12]", body="  thanks\n", attachments=["a.png"]))
    assert r == MailReply(12, "thanks", ["a.png"])


@pytest.mark.parametrize("subject", ["[#7] hello", "hello [#7]", "a [#7] b", "Re: Fwd: [#7]", "[#7]"])
def test_reply_tag_anywhere_in_subject(subject):
    r = run(mail(subject=subject))
    assert isinstance(r, MailReply) and r.case_id == 7


def test_reply_does_not_consult_directory():
    r = intake_email(mail(subject="Re: [#3]", sender="stranger@nowhere"), lambda s: None)
    assert r == MailReply(3, "body", [])


def test_reply_multi_digit_id():
    assert run(mail(subject="[#1234] x")).case_id == 1234


def test_reply_drops_empty_attachments_keeps_order_and_names():
    r = run(mail(subject="[#1]", attachments=["b.txt", "", "a.txt", ""]))
    assert r.attachments == ["b.txt", "a.txt"]


def test_reply_body_trimmed_only_at_ends():
    r = run(mail(subject="[#1]", body="\n\t  line one\n\nline two  \n"))
    assert r.body == "line one\n\nline two"


def test_reply_with_empty_body():
    r = run(mail(subject="[#1]", body="   "))
    assert r == MailReply(1, "", [])


# ------------------------------------------------------------------ new case

def test_new_case_basic():
    r = run(mail(subject="Cannot log in", body=" please help ", attachments=["x.png"]))
    assert r == MailNewCase(CaseDraft("Cannot log in", "acme", "med", None), "please help", ["x.png"])


def test_new_case_org_comes_from_directory():
    r = run(mail(sender="omar@zephyr.test"))
    assert isinstance(r, MailNewCase) and r.draft.org == "zephyr"


def test_directory_is_called_with_sender():
    seen = []

    def d(s):
        seen.append(s)
        return "acme"

    intake_email(mail(sender="who@x"), d)
    assert seen and set(seen) == {"who@x"}


def test_unknown_sender_bounces_naming_sender():
    r = run(mail(sender="stranger@evil.test"))
    assert isinstance(r, MailBounce)
    assert "stranger@evil.test" in r.reason


@pytest.mark.parametrize("subject,expected", [
    ("Re: Help", "Help"),
    ("RE: Help", "Help"),
    ("re: Help", "Help"),
    ("Fwd: Help", "Help"),
    ("FWD: Help", "Help"),
    ("Fw: Help", "Help"),
    ("FW: Help", "Help"),
    ("Re: Re: Help", "Help"),
    ("Re: Fwd: Fw: re: Help", "Help"),
    ("   Re:   Help   ", "Help"),
    ("  Help me  ", "Help me"),
    ("Re:Help", "Help"),
])
def test_prefixes_stripped_and_subject_trimmed(subject, expected):
    r = run(mail(subject=subject))
    assert isinstance(r, MailNewCase)
    assert r.draft.subject == expected


@pytest.mark.parametrize("subject", ["Reply needed", "Regarding billing", "Forward progress", "Fwd", "Resolve this"])
def test_non_prefix_words_are_kept(subject):
    assert run(mail(subject=subject)).draft.subject == subject


def test_prefix_only_in_the_middle_is_kept():
    assert run(mail(subject="Help Re: this")).draft.subject == "Help Re: this"


@pytest.mark.parametrize("subject", ["", "   ", "Re:", "Re: Re:", "Fwd:  ", "FW: Re: Fw:"])
def test_empty_subject_bounces(subject):
    assert run(mail(subject=subject)) == MailBounce("empty subject")


@pytest.mark.parametrize("word", ["urgent", "URGENT", "Urgent", "outage", "OUTAGE", "Outage"])
def test_high_severity_from_subject(word):
    r = run(mail(subject=f"{word} problem", body="plain"))
    assert r.draft.severity == "high"


@pytest.mark.parametrize("word", ["urgent", "URGENT", "outage", "Outage"])
def test_high_severity_from_body(word):
    r = run(mail(subject="plain subject", body=f"this is {word} please"))
    assert r.draft.severity == "high"


def test_high_severity_when_word_is_inside_a_longer_word():
    assert run(mail(subject="Outages again")).draft.severity == "high"
    assert run(mail(subject="x", body="very urgently")).draft.severity == "high"


def test_default_severity_is_med():
    assert run(mail(subject="Export garbled", body="columns shifted")).draft.severity == "med"


def test_high_severity_via_stripped_prefix_subject():
    assert run(mail(subject="Re: URGENT login")).draft.severity == "high"


def test_sla_is_none():
    assert run(mail(subject="urgent outage")).draft.sla_due is None


def test_attachments_drop_empty_and_keep_order():
    r = run(mail(attachments=["", "z.log", "", "a.log"]))
    assert r.attachments == ["z.log", "a.log"]


def test_no_attachments():
    assert run(mail(attachments=[])).attachments == []


def test_body_trimmed():
    assert run(mail(body="\n  hi there \t\n")).body == "hi there"


def test_body_is_not_part_of_draft_subject():
    r = run(mail(subject="Subject only", body="Body text"))
    assert r.draft.subject == "Subject only"


def test_result_types():
    assert isinstance(run(mail(subject="[#1]")), MailReply)
    assert isinstance(run(mail()), MailNewCase)
    assert isinstance(run(mail(sender="nobody")), MailBounce)
