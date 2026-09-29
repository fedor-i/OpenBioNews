"""Tests for the OpenBioNews pipeline.

Runs with pytest (`pytest`) or directly (`python tests/test_pipeline.py`) — the
bottom of the file executes every test_* function without pytest installed.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openbionews import compose, config, fetch, pipeline, render, textutil
from openbionews.llm.base import Backend
from openbionews.llm.nollm import NoLLMBackend
from openbionews.models import Item

RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>T</title>
<item><title>Alpha drug approved by regulators</title>
<link>https://ex.com/a</link><description>&lt;p&gt;First sentence. Second one here.&lt;/p&gt;</description>
<pubDate>Mon, 29 Sep 2025 13:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM_SAMPLE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>T</title>
<entry><title>Beta trial results published</title>
<link rel="alternate" href="https://ex.com/b"/>
<summary>Some summary text.</summary>
<published>2025-09-29T10:00:00Z</published></entry></feed>"""


def test_strip_html():
    assert textutil.strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert textutil.strip_html("a &amp; b") == "a & b"
    assert textutil.strip_html(None) == ""


def test_first_sentences():
    text = "One. Two. Three. Four."
    assert textutil.first_sentences(text, count=2) == "One. Two."


def test_jaccard():
    a = textutil.token_set("FDA approves CRISPR gene therapy")
    b = textutil.token_set("FDA clears CRISPR gene therapy today")
    assert textutil.jaccard(a, b) > 0.5
    assert textutil.jaccard(a, textutil.token_set("")) == 0.0


def test_parse_rss():
    items = fetch.parse_feed(RSS_SAMPLE, "Src", "biotech")
    assert len(items) == 1
    it = items[0]
    assert it.title == "Alpha drug approved by regulators"
    assert it.link == "https://ex.com/a"
    assert "First sentence." in it.summary
    assert it.published is not None and it.published.year == 2025
    assert it.topic == "biotech"


def test_parse_atom():
    items = fetch.parse_feed(ATOM_SAMPLE, "Src", "science")
    assert len(items) == 1
    assert items[0].link == "https://ex.com/b"
    assert items[0].published.hour == 10


def _item(title, link, hours_ago=1, summary="", source="S", topic="t"):
    return Item(
        title=title, link=link, summary=summary, source=source, topic=topic,
        published=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )


def test_filter_age_and_dedup():
    items = [
        _item("Fresh story", "https://ex.com/1", hours_ago=1),
        _item("Old story", "https://ex.com/2", hours_ago=100),
        _item("Fresh story dup", "https://ex.com/1?utm=x", hours_ago=1),  # same link
    ]
    kept = pipeline.filter_items(items, {"max_age_hours": 48})
    links = [i.link for i in kept]
    assert "https://ex.com/1" in links
    assert "https://ex.com/2" not in links       # too old
    assert len(kept) == 1                          # dup collapsed


def test_filter_keywords():
    items = [
        _item("Cancer breakthrough", "https://ex.com/1"),
        _item("Sports result", "https://ex.com/2"),
    ]
    inc = pipeline.filter_items(items, {"include_keywords": ["cancer"]})
    assert len(inc) == 1 and inc[0].link == "https://ex.com/1"
    exc = pipeline.filter_items(items, {"exclude_keywords": ["sports"]})
    assert len(exc) == 1 and exc[0].link == "https://ex.com/1"


def test_clustering_merges_similar():
    items = [
        _item("FDA approves CRISPR gene therapy for sickle cell", "https://ex.com/1", source="A"),
        _item("FDA clears CRISPR gene therapy for sickle cell disease", "https://ex.com/2", source="B"),
        _item("Completely unrelated wearable sensor news", "https://ex.com/3", source="C"),
    ]
    clusters = pipeline.cluster_items(items, threshold=0.5)
    sizes = sorted(len(c.items) for c in clusters)
    assert sizes == [1, 2]
    big = max(clusters, key=lambda c: len(c.items))
    assert set(big.sources) == {"A", "B"}


def test_rank_and_limit():
    titles = [
        "Regulators approve novel diabetes medication",
        "Volcano erupts near coastal fishing village",
        "Telescope captures distant spiral galaxy image",
        "Startup unveils battery recycling breakthrough",
        "Marathon runner sets unexpected world record",
    ]
    items = [_item(t, f"https://ex.com/{i}") for i, t in enumerate(titles)]
    clusters = pipeline.cluster_items(items, threshold=0.5)
    assert len(clusters) == 5  # all distinct stories
    ranked = pipeline.rank_clusters(clusters)
    limited = pipeline.limit_clusters(ranked, max_items=3, max_per_topic=0)
    assert len(limited) == 3


def test_nollm_summary():
    c = pipeline.cluster_items(
        [_item("Headline", "https://ex.com/1", summary="Lead sentence here. More detail after.")],
        threshold=0.5,
    )[0]
    blurb = NoLLMBackend().summarize(c)
    assert "Lead sentence here." in blurb


class _BoomBackend(Backend):
    name = "boom"

    def summarize(self, cluster):
        raise RuntimeError("simulated failure")


def test_compose_falls_back_on_error():
    clusters = pipeline.cluster_items(
        [_item("H", "https://ex.com/1", summary="Fallback works. Yes.")], threshold=0.5
    )
    digest, warnings = compose.compose(clusters, _BoomBackend(), {"title": "T"})
    assert "Fallback works." in digest.clusters[0].blurb
    assert len(warnings) == 1


def test_render_formats():
    clusters = pipeline.cluster_items(
        [_item("Big Story", "https://ex.com/1", summary="Summary text.")], threshold=0.5
    )
    digest, _ = compose.compose(clusters, NoLLMBackend(), {"title": "My Digest"})
    md = render.render(digest, "markdown")
    assert "# My Digest" in md and "Big Story" in md
    html = render.render(digest, "html")
    assert "<!doctype html>" in html and "Big Story" in html
    txt = render.render(digest, "text")
    assert "Big Story" in txt


def test_config_roundtrip(tmp_path=None):
    import tempfile
    d = tmp_path or Path(tempfile.mkdtemp())
    p = d / "c.json"
    cfg = config.default_config()
    config.save_config(cfg, p)
    loaded = config.load_config(p)
    assert loaded["profile"]["title"] == cfg["profile"]["title"]
    assert config.validate_config(loaded) == []


def test_wizard_writes_config(tmp_path=None):
    """Drive the interactive wizard with scripted answers."""
    import builtins
    import tempfile
    from openbionews import setup_wizard

    d = tmp_path or Path(tempfile.mkdtemp())
    p = d / "wiz.json"

    answers = iter([
        "My Test Brief",   # title
        "A subtitle",       # intro
        "1",                # bundles -> biotech
        "n",                # add own feed?
        "cancer",           # include keywords
        "",                 # exclude keywords
        "24",               # max age
        "1",                # summaries -> none (no why-it-matters prompt follows)
        "1",                # output format -> markdown
        "digest",           # output folder
        "n",                # email the digest? -> no
    ])

    orig_input = builtins.input
    orig_isatty = sys.stdin.isatty
    builtins.input = lambda *a: next(answers)
    sys.stdin.isatty = lambda: True
    try:
        cfg = setup_wizard.run_wizard(path=p)
    finally:
        builtins.input = orig_input
        sys.stdin.isatty = orig_isatty

    assert p.exists()
    assert cfg["profile"]["title"] == "My Test Brief"
    assert cfg["filters"]["include_keywords"] == ["cancer"]
    assert cfg["filters"]["max_age_hours"] == 24
    assert cfg["llm"]["backend"] == "none"


def test_importance_ranking():
    """A multi-source story with fresh, salient headline outranks a lone old one."""
    now = datetime.now(timezone.utc)
    big_a = _item("FDA approves new therapy", "https://ex.com/1", hours_ago=1, source="A")
    big_b = _item("FDA approves new therapy today", "https://ex.com/2", hours_ago=1, source="B")
    small = _item("Local gardening club meets weekly", "https://ex.com/3", hours_ago=1, source="C")
    clusters = pipeline.cluster_items([big_a, big_b, small], threshold=0.5)
    ranked = pipeline.rank_clusters(clusters)
    assert len(ranked[0].sources) == 2  # the corroborated FDA story is first
    assert pipeline.importance_score(ranked[0], now) > pipeline.importance_score(ranked[-1], now)


def test_read_minutes():
    from openbionews.compose import compose as compose_fn
    clusters = pipeline.cluster_items(
        [_item("A headline here", "https://ex.com/1", summary="Word " * 400)], threshold=0.5
    )
    digest, _ = compose_fn(clusters, NoLLMBackend(), {"title": "T"})
    assert digest.read_minutes >= 1


def test_significance_prompt_selection():
    from openbionews.llm import base
    assert "Why it matters" in base.system_prompt(True)
    assert "Why it matters" not in base.system_prompt(False)


def test_mailer_configured_and_message():
    from openbionews import mailer
    from openbionews.compose import compose as compose_fn
    assert not mailer.is_configured({"enabled": True, "smtp_host": ""})
    cfg = {
        "enabled": True, "smtp_host": "smtp.example.com", "from_addr": "me@example.com",
        "to_addrs": ["you@example.com"], "smtp_port": 587,
    }
    assert mailer.is_configured(cfg)
    clusters = pipeline.cluster_items([_item("H", "https://ex.com/1", summary="Body.")], threshold=0.5)
    digest, _ = compose_fn(clusters, NoLLMBackend(), {"title": "My Digest"})
    msg = mailer.build_message(digest, "<p>hi</p>", "hi", cfg)
    assert msg["To"] == "you@example.com"
    assert "My Digest" in msg["Subject"]
    assert msg.get_content_type() == "multipart/alternative"


def test_end_to_end_demo():
    from openbionews.cli import _demo_config
    from openbionews.run import build_digest

    result = build_digest(_demo_config())
    assert result.story_count >= 1
    # The two sample wires share one CRISPR story; it should cluster.
    multi = [c for c in result.digest.clusters if len(c.sources) > 1]
    assert multi, "expected at least one multi-source cluster"
    assert "OpenBioNews" in result.rendered or "Demo" in result.rendered


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{'all passed' if not failures else str(failures) + ' failed'}")
    sys.exit(1 if failures else 0)
