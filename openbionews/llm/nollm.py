"""The default, dependency-free summarizer.

No model, no network: it lifts the lead sentences from the article the feed
already provides. Deterministic and instant — good enough for a readable digest,
and the reason OpenBioNews works out of the box with nothing installed.
"""

from __future__ import annotations

from .. import textutil
from ..models import Cluster
from .base import Backend


class NoLLMBackend(Backend):
    name = "no-LLM"

    @property
    def label(self) -> str:
        return "no-LLM (deterministic)"

    def summarize(self, cluster: Cluster, significance: bool = False) -> str:
        # The deterministic backend can't reliably explain significance, so the
        # ``significance`` flag is accepted (for a uniform interface) but ignored.
        canonical = cluster.canonical
        # Prefer the richest available description across the cluster.
        best = ""
        for item in cluster.items:
            if len(item.summary) > len(best):
                best = item.summary
        lead = textutil.first_sentences(best, count=2)
        if not lead:
            # Nothing but a headline to work with.
            return canonical.title
        return lead
