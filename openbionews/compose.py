"""Turn ranked clusters into a finished Digest, adding a blurb to each story.

The chosen backend writes the blurbs. If it fails on a given story (a network
blip, a rate limit), that story quietly falls back to the deterministic no-LLM
summary rather than aborting the whole run.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import cite
from .llm.base import Backend
from .llm.nollm import NoLLMBackend
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
    fallback = NoLLMBackend()

    for i, cluster in enumerate(clusters):
        if not want_summaries:
            cluster.blurb = ""
            cluster.claims = []
            continue
        # The source-bound, per-sentence brief is deterministic and backend-
        # independent: it is lifted verbatim from the cited primary records, so
        # it stands on its own even when an LLM blurb is also requested.
        cluster.claims = cite.attribute(cluster)
        try:
            cluster.blurb = backend.summarize(cluster, significance=want_significance)
        except Exception as exc:  # noqa: BLE001 — any backend failure degrades gracefully
            cluster.blurb = fallback.summarize(cluster)
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
