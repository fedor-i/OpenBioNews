"""Core data structures for the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import textutil


@dataclass
class Item:
    """A single news entry pulled from a feed."""

    title: str
    link: str
    summary: str = ""
    source: str = ""
    topic: str = ""
    published: datetime | None = None
    guid: str = ""

    def token_set(self):
        return textutil.token_set(self.title)


@dataclass
class Cluster:
    """A group of items that report the same underlying story."""

    items: list[Item] = field(default_factory=list)
    topic: str = ""
    blurb: str = ""

    @property
    def canonical(self) -> Item:
        """The representative item: the earliest published, else the first."""
        dated = [i for i in self.items if i.published is not None]
        if dated:
            return min(dated, key=lambda i: i.published)
        return self.items[0]

    @property
    def sources(self) -> list[str]:
        seen: list[str] = []
        for item in self.items:
            if item.source and item.source not in seen:
                seen.append(item.source)
        return seen

    @property
    def latest(self) -> datetime | None:
        dated = [i.published for i in self.items if i.published is not None]
        return max(dated) if dated else None


@dataclass
class Digest:
    """The finished, composed digest ready to render."""

    title: str
    intro: str
    generated_at: datetime
    clusters: list[Cluster] = field(default_factory=list)
    backend_label: str = "no-LLM"

    @property
    def read_minutes(self) -> int:
        """Rough read time at ~200 words/minute across titles and blurbs."""
        words = 0
        for cluster in self.clusters:
            words += len(cluster.canonical.title.split())
            words += len(cluster.blurb.split())
        return max(1, round(words / 200))
