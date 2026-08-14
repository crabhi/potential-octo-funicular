"""Capture the running Flowdeck (and, for the generality proof, the CMS on
the same generic UI) with Playwright/Chromium. Output lands in
docs/slides/img/ — the slide deck embeds these.

    ../rule-driven-cms/.venv/bin/python screenshots.py
"""

import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ENGINE_ROOT = HERE.parent / "rule-driven-cms"
OUT = HERE.parent.parent / "docs" / "slides" / "img"
sys.path.insert(0, str(ENGINE_ROOT))

from live_demo import request, wait_ready  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 8873
CMS_PORT = 8874


def launch_flowdeck():
    proc = subprocess.Popen(
        [sys.executable, str(HERE / "app.py"), "--port", str(PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(200):
        line = proc.stdout.readline().decode()
        if "Flowdeck is up" in line:
            return proc
        if not line:
            time.sleep(0.1)
    raise RuntimeError("flowdeck did not start")


def launch_cms(tmpdb):
    proc = subprocess.Popen(
        [sys.executable, "-m", "engine.server", "--rules", "rulesets/cms",
         "--db", tmpdb, "--port", str(CMS_PORT), "--ui",
         "--seed", "rulesets/cms/features.yaml"],
        cwd=ENGINE_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    wait_ready(proc)
    # a small editorial board, seeded through the rules
    for author, title, moves in [
            ("alice", "Postgres 16 upgrade notes", ["submit"]),
            ("bob", "Why we chose rule bases", ["submit"]),
            ("alice", "Launch: search v2", ["submit"]),
    ]:
        _, doc = request(CMS_PORT, "POST", "/articles", author,
                         {"title": title, "body": "…"})
        for m in moves:
            request(CMS_PORT, "POST", f"/articles/{doc['id']}/{m}", author)
    # an editor publishes one (not their own)
    request(CMS_PORT, "POST", "/articles/1/publish", "ed")
    return proc


def as_user(context, port, name):
    context.clear_cookies()
    if name:
        context.add_cookies([{"name": "persona", "value": name,
                              "url": f"http://127.0.0.1:{port}"}])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fd = launch_flowdeck()
    import tempfile
    tmp = tempfile.TemporaryDirectory()
    cms = launch_cms(f"{tmp.name}/cms.db")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path="/opt/pw-browsers/chromium")
            context = browser.new_context(viewport={"width": 1120, "height": 630},
                                          device_scale_factor=2)
            page = context.new_page()
            base = f"http://127.0.0.1:{PORT}"

            def shot(path, name, full_page=False):
                page.goto(f"{base}{path}")
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(OUT / name), full_page=full_page)
                print(f"  wrote {name}")

            # 1. the board as a team member
            as_user(context, PORT, "tom")
            shot("/ui", "board-tom.png")

            # 2. the same board as the other team: the walls, visibly
            as_user(context, PORT, "nadia")
            shot("/ui", "board-nadia.png")

            # 3. detail as mira on her own in-review task: approve greyed
            #    with the denying rule named, send_back live
            as_user(context, PORT, "mira")
            page.goto(f"{base}/ui")
            page.click("text=Sprint 34 goals")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(OUT / "detail-mira.png"))
            print("  wrote detail-mira.png")

            # 4. she clicks approve anyway -> the named 403 banner
            page.click("button:has-text('approve')")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(OUT / "banner-denied.png"))
            print("  wrote banner-denied.png")

            # 5. the program, rendered: /ui/rules
            shot("/ui/rules", "rules-page.png")

            # 6. the SAME generic UI serving the CMS (generality proof)
            as_user(context, CMS_PORT, "ed")
            page.goto(f"http://127.0.0.1:{CMS_PORT}/ui")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(OUT / "board-cms.png"))
            print("  wrote board-cms.png")

            browser.close()
    finally:
        fd.terminate()
        cms.terminate()
        fd.wait(timeout=5)
        cms.wait(timeout=5)
        tmp.cleanup()
    print(f"screenshots in {OUT}")


if __name__ == "__main__":
    main()
