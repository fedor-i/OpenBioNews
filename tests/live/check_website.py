"""Live check of the hosted website's ready-made views.

The page (docs/index.html) queries the agencies straight from the browser, so the
Python checks can't vouch for it. This opens each "Start with a ready-made view"
card in a headless browser against the real APIs and checks that it shows
results without script errors. A card that silently comes back empty, because an
agency changed its API or a query parameter stopped working, fails here.

Needs Playwright (``pip install playwright && playwright install chromium``) and the
network. Runs daily in CI (.github/workflows/live.yml); locally:

    python tests/live/check_website.py

Exit code 1 if any card shows no results or the page throws an error.
"""

from __future__ import annotations

import functools
import http.server
import os
import sys
import threading
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent.parent / "docs"
WAIT_MS = int(os.environ.get("OBN_WAIT_MS", 60_000))     # agencies can be slow; a card has a minute to show results


def _serve() -> str:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DOCS))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/"


def main() -> int:
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    base = _serve()
    rows, failed = [], 0
    with sync_playwright() as pw:
        # OBN_CHROMIUM lets a machine with its own Chromium skip `playwright install`.
        exe = os.environ.get("OBN_CHROMIUM")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page()
        page.goto(base)
        cards = page.eval_on_selector_all(
            "#starters a[data-starter]",
            "els => els.map(a => ({label: (a.querySelector('b') || a).textContent.trim(), href: a.getAttribute('href')}))")
        if not cards:
            print("FAIL         no ready-made views found on the landing page")
            return 1
        # The front tiles fill in live counts and rotating headlines from the same queries.
        try:
            page.wait_for_function("[...document.querySelectorAll('#starters .tile .live')]"
                                   ".filter(e => e.textContent.trim()).length >= 4", timeout=WAIT_MS)
            rows.append(("PASS", "Front tiles", "all show live headlines"))
        except PWTimeout:
            empty = page.eval_on_selector_all(
                "#starters .tile", "ts => ts.filter(t => !t.querySelector('.live').textContent.trim())"
                ".map(t => t.querySelector('b').textContent)")
            rows.append(("FAIL", "Front tiles", f"no live headline on: {', '.join(empty)}"))
            failed += 1
        page.close()
        for card in cards:
            view = browser.new_page()            # a fresh page per card: clean errors and state
            errors: list[str] = []
            view.on("pageerror", lambda e: errors.append(str(e)))
            view.goto(base + card["href"])
            try:
                view.wait_for_function("document.querySelectorAll('#results article').length > 0",
                                       timeout=WAIT_MS)
                n = view.eval_on_selector_all("#results article", "els => els.length")
                status, detail = ("FAIL", f"script error: {errors[0][:150]}") if errors else ("PASS", f"{n} results")
            except PWTimeout:
                status = "FAIL"
                detail = f"no results within {WAIT_MS // 1000}s; page says: {view.text_content('#status')!r}"
            view.close()
            failed += status == "FAIL"
            rows.append((status, card["label"], detail))
        browser.close()

    for status, label, detail in rows:
        print(f"{status:<12} {label}: {detail}")
        if status == "FAIL":
            print(f"::error title=Website: {label}::{detail}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## Website ready-made views\n\n| Result | View | Detail |\n|---|---|---|\n")
            for status, label, detail in rows:
                icon = "✅" if status == "PASS" else "❌"
                fh.write(f"| {icon} {status} | {label} | {detail.replace('|', '/')} |\n")
    print(f"\n{len(rows) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
