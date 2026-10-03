"""REVIEWED — the page frame (relay.web.ui): document and sidebar."""

from __future__ import annotations

from relay.cases.queues import sort_into_queues
from relay.web.seed import PEOPLE
from relay.web.server import esc
from relay.web.ui import document, sidebar


def test_document_wraps_content_verbatim():
    doc = document('<aside id="sidebar">S</aside>', "<p>CONTENT&amp;</p>")
    assert doc.lower().startswith("<!doctype html>")
    assert '<main id="content"><p>CONTENT&amp;</p></main>' in doc
    assert '<aside id="sidebar">S</aside>' in doc
    assert 'src="/static/htmx.min.js"' in doc


def test_sidebar_out_of_band_flag_and_persona_switcher(desk):
    v = desk.view(desk.actor("dana"))
    oob = sidebar(None, True, v, sort_into_queues, esc)
    assert 'id="sidebar"' in oob and 'hx-swap-oob="true"' in oob
    plain = sidebar("inbox", False, v, sort_into_queues, esc)
    assert 'hx-swap-oob' not in plain
    assert 'action="/persona"' in plain and 'name="persona"' in plain
    for p in PEOPLE:
        assert f'value="{p.name}"' in plain
