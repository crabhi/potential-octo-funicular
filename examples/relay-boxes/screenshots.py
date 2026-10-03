"""Capture screenshots of the generated UI for README/slides.

    uv run --with playwright python screenshots.py   # writes ../../docs/slides/img/boxes-*.png
"""

import pathlib
import threading

from playwright.sync_api import sync_playwright

from relay.web import seed as demo
from relay.web import server

OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "slides" / "img"


def main() -> None:
    desk, httpd = server.build(0)
    demo.seed(desk)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    sso = next(c.id for c in desk.visible_cases(desk.actor("noor"))
               if c.subject.startswith("Login broken"))
    shots = [("boxes-queue-sam.png", "sam", "/?q=working"),
             ("boxes-case-sam.png", "sam", f"/case/{sso}"),
             ("boxes-case-dana.png", "dana", f"/case/{sso}")]
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"
                                    if pathlib.Path("/opt/pw-browsers/chromium").exists()
                                    else None)
        for name, who, path in shots:
            ctx = browser.new_context(viewport={"width": 1280, "height": 860})
            ctx.add_cookies([{"name": "persona", "value": who, "url": base}])
            page = ctx.new_page()
            page.goto(base + path)
            page.screenshot(path=str(OUT / name), full_page=False)
            ctx.close()
            print("wrote", OUT / name)
        # the honest affordance: press a locked button as quinn
        ctx = browser.new_context(viewport={"width": 1280, "height": 860})
        ctx.add_cookies([{"name": "persona", "value": "quinn", "url": base}])
        page = ctx.new_page()
        page.goto(f"{base}/case/{sso}")
        page.evaluate("""() => { const d = document.querySelector('details');
                                  if (d) d.open = true; }""")
        locked = page.locator("details button").first
        if locked.count():
            locked.click()
            page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "boxes-refusal-quinn.png"))
        print("wrote", OUT / "boxes-refusal-quinn.png")
        browser.close()
    httpd.shutdown()


if __name__ == "__main__":
    main()
