"""Offline demo digest.

Builds a mixed digest — trade-press RSS plus primary sources (ClinicalTrials.gov,
FDA recalls, SEC filings) — entirely from bundled fixtures, with no network. It
runs the real pipeline (filter → cluster → rank → compose → render), so
``openbionews run --demo`` is an honest preview of what the tool produces,
including source citations, on any machine.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import fetch, pipeline, render
from .compose import compose
from .connectors.clinicaltrials import parse_studies
from .connectors.edgar import parse_hits
from .connectors.openfda import parse_enforcement
from .llm.nollm import NoLLMBackend
from .models import Digest

DATA = Path(__file__).parent / "data"


def demo_items() -> list:
    """Collect Items from every bundled sample source (offline)."""
    items = []
    # Trade-press RSS samples (read from local files, no network).
    feeds = [
        {"name": "Sample Wire A", "url": str(DATA / "sample_feed_a.xml"), "topic": "biotech"},
        {"name": "Sample Wire B", "url": str(DATA / "sample_feed_b.xml"), "topic": "biotech"},
    ]
    rss_items, _ = fetch.fetch_all(feeds)
    items.extend(rss_items)
    # Primary-source fixtures, parsed by the real connector parsers.
    items.extend(parse_studies(json.loads((DATA / "demo_clinicaltrials.json").read_text("utf-8"))))
    items.extend(parse_enforcement(json.loads((DATA / "demo_openfda.json").read_text("utf-8"))))
    items.extend(parse_hits(json.loads((DATA / "demo_edgar.json").read_text("utf-8"))))
    return items


def build_demo_digest(fmt: str = "markdown", group_by: str = "topic") -> tuple[str, Digest]:
    """Return (rendered, digest) for the offline demo."""
    items = demo_items()
    # Keep everything: the fixtures use fixed dates, so don't age them out.
    items = pipeline.filter_items(items, {"max_age_hours": 0})
    clusters = pipeline.cluster_items(items, threshold=0.5)
    clusters = pipeline.rank_clusters(clusters)
    clusters = pipeline.limit_clusters(clusters, max_items=40, max_per_topic=0)
    profile = {
        "title": "OpenBioNews — Demo Digest",
        "intro": "Built offline from bundled samples: trade-press RSS plus primary "
                 "sources (ClinicalTrials.gov, FDA recalls, SEC filings), each cited.",
    }
    digest, _ = compose(clusters, NoLLMBackend(), profile, want_summaries=True)
    digest.generated_at = datetime.now(timezone.utc)
    return render.render(digest, fmt=fmt, group_by=group_by), digest
