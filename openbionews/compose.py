"""Turn ranked clusters into a finished Digest, adding a blurb to each story.

The chosen backend writes the blurbs. If it fails on a given story (a network
blip, a rate limit), that story quietly falls back to the deterministic no-LLM
summary rather than aborting the whole run.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import cite
from .llm import base
from .llm.base import Backend
from .models import Cluster, Digest


def compose(
    clusters: list[Cluster],
    backend: Backend,
    profile: dict,
    want_summaries: bool = True,
    want_significance: bool = False,
    on_status=None,
) -> tuple[Digest, list[str]]:
    """Build the Digest. Returns (digest, warnings)."""
    warnings: list[str] = []

    # The deterministic cited claims are always the factual body. An LLM, when
    # enabled and asked, adds only interpretation ("why it matters") on top —
    # never the facts — so there is nothing for it to hallucinate into the record.
    want_llm_note = want_significance and getattr(backend, "supports_significance", False)

    for i, cluster in enumerate(clusters):
        if not want_summaries:
            cluster.blurb = ""
            cluster.claims = []
            cluster.significance = ""
            continue
        # Source-bound, per-sentence brief: verbatim from the cited records.
        cluster.claims = cite.attribute(cluster)
        cluster.blurb = ""
        cluster.significance = ""
        if want_llm_note:
            try:
                text = backend.summarize(cluster, significance=True)
                cluster.significance = base.extract_significance(text)
            except Exception as exc:  # noqa: BLE001 — a failed note never sinks the run
                warnings.append(f"'{cluster.canonical.title[:50]}': {exc}")
        if on_status:
            on_status(i + 1, len(clusters))

    digest = Digest(
        title=profile.get("title", "News Digest"),
        intro=profile.get("intro", ""),
        generated_at=datetime.now(timezone.utc),
        clusters=clusters,
        backend_label=backend.label,
    )
    return digest, warnings
