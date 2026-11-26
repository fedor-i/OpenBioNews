"""A short video and a swipeable PDF of the website's front box, for LinkedIn.

LinkedIn can't play the site's live slides from a link, but it autoplays a native
video in the feed and shows an uploaded PDF as a swipeable carousel. This captures
the front box's slides from the live site (or any URL serving docs/), puts each in a
branded 1920x1080 frame with a progress strip, and writes:

  <out>/reel.mp4    ~3.5 s per slide with short crossfades (H.264, silent)
  <out>/reel.pdf    one frame per page, for a LinkedIn "document" post
  <out>/frames/     the frames as PNGs

The slides are the site's own, so every figure on them is computed from the official
records the site links to. Needs Playwright with Chromium, and ffmpeg for the video
(the PDF is made without it).

Usage:
  python tools/brief_reel.py --out reel/
  python tools/brief_reel.py --site http://localhost:8000/ --per-feed 3
"""

from __future__ import annotations

import argparse
import base64
import html
import os
import shutil
import subprocess
import sys
from pathlib import Path

SITE = "https://fedor-i.github.io/OpenBioNews/"
W, H = 1920, 1080
BOX_CSS_WIDTH = 760          # every label fits at this width (narrower truncates chips)
SCALE = 2.5                  # capture scale, so the box stays sharp at 1800 px wide

FEED_NAMES = {"brief": "This week's brief", "stopped": "Stopped Phase 3 · 30 days",
              "industry": "Industry Phase 3 · this week", "recalls": "Class I recalls · 30 days"}


def pick_slides(slides: list[dict], per_feed: int) -> list[int]:
    """Indexes to show: each feed's overview slides first (at most two), then its
    first record slides, up to ``per_feed`` slides per feed, feeds in site order."""
    out = []
    for feed in dict.fromkeys(s["feed"] for s in slides):
        idx = [i for i, s in enumerate(slides) if s["feed"] == feed]
        overview = [i for i in idx if slides[i]["kind"] != "rec"][:2]
        records = [i for i in idx if slides[i]["kind"] == "rec"]
        out += (overview + records)[:per_feed]
    return out


def frame_html(slide_png: bytes, label: str, week: str, n: int, total: int, feeds: list[str],
               feed: str) -> str:
    img = base64.b64encode(slide_png).decode()
    esc = html.escape
    steps = "".join(f'<i class="{"on" if k == n else "done" if k < n else ""}"></i>' for k in range(total))
    chips = " · ".join(f'<b>{esc(FEED_NAMES.get(f, f))}</b>' if f == feed else esc(FEED_NAMES.get(f, f))
                       for f in feeds)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=block" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden}}
body{{background:#eef6f4;color:#132321;font-family:Inter,"Segoe UI",Roboto,Arial,sans-serif;display:flex;flex-direction:column}}
header{{background:#0f3d38;color:#fff;padding:40px 60px 36px;display:flex;align-items:flex-end;justify-content:space-between}}
.brand{{font:700 30px Georgia,"DejaVu Serif",serif;color:#e6f4f1}}
.k{{margin-top:8px;font-weight:800;font-size:46px;letter-spacing:.05em;text-transform:uppercase}}
.when{{font-weight:600;font-size:32px;color:#9fd8cf}}
main{{flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 60px;gap:30px}}
main img{{width:100%;display:block;border-radius:22px;box-shadow:0 10px 40px rgba(15,61,56,.12)}}
.steps{{display:flex;gap:8px}}
.steps i{{flex:1;height:8px;border-radius:4px;background:#d6e6e2}}
.steps i.done{{background:#7fc7bc}} .steps i.on{{background:#0d9488}}
.feeds{{font-size:26px;color:#5b726e}} .feeds b{{color:#0f3d38}}
footer{{padding:0 60px 40px;display:flex;justify-content:space-between;font-size:28px;color:#5b726e}}
footer b{{color:#0f3d38}}
</style></head><body>
<header><div><div class="brand">OpenBioNews</div><div class="k">This week in biopharma records</div></div>
<div class="when">{esc(week)}</div></header>
<main><img src="data:image/png;base64,{img}"><div class="steps">{steps}</div>
<div class="feeds">{chips}</div></main>
<footer><span>Every item linked to its official record</span><b>fedor-i.github.io/OpenBioNews</b></footer>
</body></html>"""


def capture(site: str, per_feed: int, out: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright
    frames_dir = out / "frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    exe = os.environ.get("OBN_CHROMIUM")
    with sync_playwright() as p:
        browser = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        page = browser.new_page(viewport={"width": BOX_CSS_WIDTH, "height": 1000},
                                device_scale_factor=SCALE)
        page.goto(f"{site}?s=0&paused", wait_until="networkidle")
        page.wait_for_function("(document.getElementById('carousel')._slides||[]).length > 3",
                               timeout=90_000)
        slides = page.evaluate("document.getElementById('carousel')._slides"
                               ".map(s => ({feed: s.feed, kind: s.kind}))")
        # The week's dates, as the brief writes them ("Nov 16–22, 2026").
        label = page.evaluate("fetch('brief/latest.json').then(r => r.json()).then(j => j.label)"
                              ".catch(() => '')") or ""
        feeds = list(dict.fromkeys(s["feed"] for s in slides))
        chosen = pick_slides(slides, per_feed)
        shots = []
        for i in chosen:
            # Show slide i, paused; the box keeps the slide's own fixed height.
            page.goto(f"{site}?s={i}&paused", wait_until="networkidle")
            page.wait_for_function("(document.getElementById('carousel')._slides||[]).length > 3",
                                   timeout=90_000)
            page.wait_for_timeout(800)
            stage = page.query_selector("#carousel .stage")
            shots.append((stage.screenshot(), slides[i]["feed"]))
        framer = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        paths = []
        for n, (png, feed) in enumerate(shots):
            framer.set_content(frame_html(png, "", label, n, len(shots), feeds, feed),
                               wait_until="networkidle")
            framer.evaluate("document.fonts.ready")
            path = frames_dir / f"f{n:02d}.png"
            framer.screenshot(path=str(path))
            paths.append(path)
        # The PDF: one frame per page.
        pages = "".join(f'<div class="p"><img src="data:image/png;base64,'
                        f'{base64.b64encode(p.read_bytes()).decode()}"></div>' for p in paths)
        framer.set_content(f"<style>@page{{size:{W}px {H}px;margin:0}}body{{margin:0}}"
                           f".p{{width:{W}px;height:{H}px;page-break-after:always}}"
                           f".p img{{width:100%;height:100%;display:block}}</style>{pages}")
        framer.pdf(path=str(out / "reel.pdf"), width=f"{W}px", height=f"{H}px",
                   print_background=True)
        browser.close()
    return paths


def encode(frames: list[Path], out: Path, hold: float = 3.5, fade: float = 0.4) -> Path | None:
    """Crossfade the frames into an H.264 MP4 that LinkedIn and phones play."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("brief_reel: ffmpeg not found; wrote the PDF and frames only.", file=sys.stderr)
        return None
    args = [ffmpeg, "-y", "-loglevel", "error"]
    for f in frames:
        args += ["-loop", "1", "-t", str(hold + fade), "-i", str(f)]
    chain, last = [], "[0:v]"
    for k in range(1, len(frames)):
        tag = f"[x{k}]"
        chain.append(f"{last}[{k}:v]xfade=transition=fade:duration={fade}:offset={k * hold:.2f}{tag}")
        last = tag
    graph = ";".join(chain) + (";" if chain else "") + f"{last}format=yuv420p,fps=30[v]"
    path = out / "reel.mp4"
    subprocess.run(args + ["-filter_complex", graph, "-map", "[v]", "-c:v", "libx264",
                           "-preset", "slow", "-crf", "20", "-movflags", "+faststart", str(path)],
                   check=True)
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--site", default=SITE, help="the site to capture (default: the live site)")
    ap.add_argument("--per-feed", type=int, default=3, help="slides per feed (default 3)")
    ap.add_argument("--out", default="reel")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    frames = capture(args.site.rstrip("/") + "/", args.per_feed, out)
    video = encode(frames, out)
    print(f"{len(frames)} frames -> {out / 'reel.pdf'}" + (f", {video}" if video else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
