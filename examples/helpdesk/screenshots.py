"""Capture the running Relay with Playwright/Chromium — the evidence that
the FREE UI layer is a real product surface (custom queues, custom brand)
while every interaction stays kernel-guarded. Output lands in
docs/slides/img/; the slide deck embeds these.

    ../rule-driven-cms/.venv/bin/python screenshots.py
"""

import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent.parent / "docs" / "slides" / "img"
PORT = 8875

from playwright.sync_api import sync_playwright  # noqa: E402


def launch():
    proc = subprocess.Popen(
        [sys.executable, str(HERE / "app.py"), "--port", str(PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(200):
        line = proc.stdout.readline().decode()
        if "Relay is up" in line:
            return proc
        if not line:
            time.sleep(0.1)
    raise RuntimeError("relay did not start")


def as_user(context, name):
    context.clear_cookies()
    if name:
        context.add_cookies([{"name": "persona", "value": name,
                              "url": f"http://127.0.0.1:{PORT}"}])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    proc = launch()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path="/opt/pw-browsers/chromium")
            context = browser.new_context(
                viewport={"width": 1200, "height": 675}, device_scale_factor=2)
            page = context.new_page()
            base = f"http://127.0.0.1:{PORT}"

            def shot(name):
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(OUT / name))
                print(f"  wrote {name}")

            # 1. the working queue as the agent: both orgs, SLA badges
            as_user(context, "sam")
            page.goto(f"{base}/?q=working")
            shot("relay-sam-working.png")

            # 2. the cross-state "SLA breached" queue — a view the generic
            #    UI could never invent; counts differ per persona
            page.goto(f"{base}/?q=breached")
            shot("relay-sam-breached.png")

            # 3. the same desk as a customer: only her org exists
            as_user(context, "dana")
            page.goto(f"{base}/?q=working")
            shot("relay-dana-working.png")

            # 4. case detail as quinn (staff, not assignee): allowed buttons,
            #    locked actions naming their rules, edit form
            as_user(context, "quinn")
            page.goto(f"{base}/?q=working")
            page.click("text=Login broken for SSO users")
            page.wait_for_load_state("networkidle")
            page.locator("details.locked summary").click()
            shot("relay-quinn-detail.png")

            # 5. quinn presses the locked resolve anyway -> the named toast
            page.locator("details.locked button",
                         has_text="Resolve").click()
            shot("relay-denied-toast.png")

            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    print(f"screenshots in {OUT}")


if __name__ == "__main__":
    main()
