"""Share images for a weekly brief.

Renders two PNGs from docs/brief/data/<week-end>.json:

  docs/brief/cards/<week-end>.png       1200x630, the link-preview card (og:image)
  docs/brief/cards/<week-end>-post.png  1080x1350, a portrait image to attach to a
                                        LinkedIn post (it takes more of the feed)

Both carry the week's counts and a few named records, so a shared link or post shows
what happened instead of a generic logo. The numbers and names come straight from the
week's data file, the same one the brief page is built from.

Needs Playwright (``pip install playwright && python -m playwright install chromium``);
without it the script says so and exits 0, and the brief pages fall back to the
site-wide preview image. Set OBN_CHROMIUM to use an existing Chromium binary.

Usage:
  python tools/brief_card.py                  # the newest week in docs/brief/data
  python tools/brief_card.py --end 2026-11-22
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weekly_brief as wb  # noqa: E402

SIZES = {"card": (1200, 630), "post": (1080, 1350)}

# Counts shown as tiles, in this order, with short labels that fit a tile.
TILES = [("new_trials", "New Phase 3 trials", "New Phase 3 trial"),
         ("results", "Phase 3 results posted", "Phase 3 result posted"),
         ("stopped", "Phase 3 trials stopped", "Phase 3 trial stopped"),
         ("approvals", "FDA approvals", "FDA approval"),
         ("recalls", "Class I recalls", "Class I recall"),
         ("sec", "SEC deals & IPO filings", "SEC deal or IPO filing")]

# Named records: (section, label, how many on the card, how many on the post image).
PICKS = [("new_trials", "New Phase 3", 1, 1), ("approvals", "Approved", 1, 2),
         ("results", "Results", 1, 1), ("stopped", "Stopped", 1, 1), ("sec", "SEC", 1, 1)]


def _line(key: str, item: dict) -> tuple[str, str, str]:
    """(org, what, detail) for one record, from the key words the brief stores."""
    k = item.get("key") or {}
    org, what = k.get("org", ""), k.get("what") or wb._short(item["title"], 60)
    if key == "approvals":                       # cond holds the active ingredient here
        detail = " · ".join(x for x in (k.get("cond"), k.get("extra")) if x)
    else:
        detail = k.get("cond", "")
        if k.get("acr") and k["acr"] != what:
            detail = f"{detail} ({k['acr']})" if detail else k["acr"]
    if key == "sec":                             # ticker · the form and item
        form = (item.get("facts") or ["", ""])[1:2][0]   # "8-K Item 1.01", or "S-1" (already in what)
        detail = " · ".join(x for x in (k.get("acr"), form if form not in what else "") if x)
    if key in ("new_trials", "results", "stopped"):
        n = next((f for f in item.get("facts", []) if f.endswith("participants")), "")
        if n:
            detail = f"{detail} · {n}" if detail else n
    return org, what, detail


def card_html(brief: dict, kind: str = "card") -> str:
    """The image as a self-contained page; ``kind`` is "card" or "post"."""
    w, h = SIZES[kind]
    secs = wb.with_all_sections(brief)["sections"]
    tiles_spec = [t if not (t[0] == "sec" and secs["sec"].get("error") == wb.NOT_YET)
                  else ("fda_notices", "FDA notices", "FDA notice") for t in TILES]
    esc = html.escape

    tiles = []
    for key, many, one in tiles_spec:
        sec = secs[key]
        if "error" in sec:
            tiles.append(f'<div class="t na"><b>–</b><span>{esc(many)}: unavailable</span></div>')
        else:
            n = sec.get("total", 0)
            tiles.append(f'<div class="t"><b>{n:,}</b><span>{esc(one if n == 1 else many)}</span></div>')

    rows = []
    for key, label, n_card, n_post in PICKS:
        sec = secs[key]
        if "error" in sec:
            continue
        for item in sec.get("items", [])[: n_card if kind == "card" else n_post]:
            org, what, detail = _line(key, item)
            rows.append(f'<li><i>{esc(label)}</i><span class="x"><b>{esc(org + " · " if org else "")}'
                        f'{esc(what)}</b>{"<em>" + esc(detail) + "</em>" if detail else ""}</span></li>')

    return f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=block" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{w}px;height:{h}px;overflow:hidden}}
body{{font-family:Inter,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Liberation Sans",sans-serif;
  background:#eef6f4;color:#132321;display:flex;flex-direction:column}}
header{{background:#0f3d38;color:#e6f4f1;padding:{'34px 56px 30px' if kind == 'card' else '56px 64px 48px'}}}
.brand{{font:700 {'26px' if kind == 'card' else '34px'} Georgia,"DejaVu Serif",serif;letter-spacing:.2px}}
.kicker{{margin-top:{'10px' if kind == 'card' else '22px'};font-weight:800;letter-spacing:.06em;text-transform:uppercase;
  font-size:{'30px' if kind == 'card' else '44px'};line-height:1.15;color:#fff}}
.when{{margin-top:6px;font-size:{'20px' if kind == 'card' else '28px'};color:#9fd8cf;font-weight:600}}
main{{flex:1;padding:{'26px 56px 0' if kind == 'card' else '44px 64px 0'};display:flex;flex-direction:column;gap:{'22px' if kind == 'card' else '34px'}}}
.tiles{{display:grid;grid-template-columns:repeat({6 if kind == 'card' else 3},1fr);gap:{'12px' if kind == 'card' else '18px'}}}
.t{{background:#fff;border:1px solid #d6e6e2;border-radius:14px;padding:{'14px 14px 12px' if kind == 'card' else '18px 24px'};
  border-top:5px solid #0d9488}}
.t b{{display:block;font-weight:800;font-size:{'40px' if kind == 'card' else '60px'};line-height:1}}
.t span{{display:block;margin-top:6px;color:#5b726e;font-size:{'15px' if kind == 'card' else '24px'};line-height:1.25}}
.t.na b{{color:#b45309}}
ul{{list-style:none;display:flex;flex-direction:column;gap:{'9px' if kind == 'card' else '20px'}}}
li{{display:flex;align-items:baseline;gap:14px;font-size:{'21px' if kind == 'card' else '28px'};line-height:1.3}}
li i{{font-style:normal;flex:none;width:{'132px' if kind == 'card' else '170px'};color:#0d9488;font-weight:800;
  font-size:.72em;letter-spacing:.06em;text-transform:uppercase}}
li .x{{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#5b726e}}
li .x b{{color:#132321;font-weight:600}}
li .x em{{font-style:normal}}
{'li .x em::before{content:" · "}' if kind == 'card' else
 'li .x b,li .x em{display:block;overflow:hidden;text-overflow:ellipsis}li .x em{font-size:.86em;margin-top:2px}'}
footer{{padding:{'0 56px 28px' if kind == 'card' else '0 64px 52px'};margin-top:auto;display:flex;justify-content:space-between;
  align-items:flex-end;gap:24px;color:#5b726e;font-size:{'17px' if kind == 'card' else '24px'}}}
footer b{{color:#0f3d38}}
</style></head><body>
<header><div class="brand">OpenBioNews</div>
<div class="kicker">This week in biopharma records</div>
<div class="when">{esc(wb.week_label(brief))}</div></header>
<main><div class="tiles">{''.join(tiles)}</div><ul>{''.join(rows)}</ul></main>
<footer><span>Every item linked to its official record<br>ClinicalTrials.gov · openFDA · Federal Register · SEC EDGAR</span>
<b>fedor-i.github.io/OpenBioNews</b></footer>
</body></html>"""


def render(brief: dict, out_dir: Path) -> list[Path]:
    """Write both PNGs; returns their paths, or [] when Playwright isn't installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("brief_card: Playwright isn't installed; skipping the share images.", file=sys.stderr)
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        exe = os.environ.get("OBN_CHROMIUM")
        browser = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        for kind, suffix in (("card", ""), ("post", "-post")):
            w, h = SIZES[kind]
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            page.set_content(card_html(brief, kind), wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            path = out_dir / f"{brief['end']}{suffix}.png"
            page.screenshot(path=str(path))
            page.close()
            paths.append(path)
        browser.close()
    return paths


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--end", help="the week's end date (YYYY-MM-DD); default: the newest week")
    ap.add_argument("--out", default=str(wb.OUT))
    args = ap.parse_args(argv)
    out = Path(args.out)
    files = sorted((out / "data").glob("*.json"))
    if args.end:
        files = [f for f in files if f.stem == args.end]
    if not files:
        print("brief_card: no brief data found", file=sys.stderr)
        return 1
    brief = json.loads(files[-1].read_text("utf-8"))
    for path in render(brief, out / "cards"):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
