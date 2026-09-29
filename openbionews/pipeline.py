"""Deterministic filtering, de-duplication and clustering.

None of this needs an LLM: stories are grouped by title-token overlap, which is
cheap, explainable and reproducible. The optional LLM only writes the prose
blurbs later, in ``compose``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import textutil
from .models import Cluster, Item


def _normalize_link(link: str) -> str:
    link = link.strip().lower()
    link = re.sub(r"[#?].*$", "", link)          # drop fragments / query strings
    link = re.sub(r"^https?://(www\.)?", "", link)  # scheme + www
    return link.rstrip("/")


def filter_items(items: list[Item], filters: dict) -> list[Item]:
    """Apply age, keyword and exact-duplicate filters. Order preserved."""
    max_age_hours = filters.get("max_age_hours") or 0
    include = [k.lower() for k in filters.get("include_keywords", []) if k.strip()]
    exclude = [k.lower() for k in filters.get("exclude_keywords", []) if k.strip()]

    cutoff = None
    if max_age_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    seen_links: set[str] = set()
    kept: list[Item] = []
    for item in items:
        if (cutoff and not item.age_exempt
                and item.published is not None and item.published < cutoff):
            continue
        haystack = f"{item.title}\n{item.summary}".lower()
        if include and not any(k in haystack for k in include):
            continue
        if exclude and any(k in haystack for k in exclude):
            continue
        # Prefer the stable guid (NCT id, recall number, EDGAR accession) — some
        # sources' links differ only by a query string, which _normalize_link
        # strips, so link-only dedup would wrongly collapse them.
        key = (item.guid or "").strip() or _normalize_link(item.link)
        if key in seen_links:
            continue
        seen_links.add(key)
        kept.append(item)
    return kept


def cluster_items(items: list[Item], threshold: float = 0.5) -> list[Cluster]:
    """Group items that report the same story using title-token similarity."""
    clusters: list[Cluster] = []
    cluster_tokens: list[list[frozenset[str]]] = []  # token sets per cluster

    for item in items:
        tset = item.token_set()
        best_idx = -1
        best_score = 0.0
        for idx, tokens_list in enumerate(cluster_tokens):
            score = max(textutil.jaccard(tset, t) for t in tokens_list)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx >= 0 and best_score >= threshold:
            clusters[best_idx].items.append(item)
            cluster_tokens[best_idx].append(tset)
        else:
            clusters.append(Cluster(items=[item], topic=item.topic))
            cluster_tokens.append([tset])

    # A cluster's topic is its canonical item's topic (stable representative).
    for cluster in clusters:
        cluster.topic = cluster.canonical.topic
    return clusters


# High-signal words that tend to mark a consequential story. Used only as a
# small, transparent nudge in the importance score — never a hard filter.
SALIENT_TERMS = {
    "approval", "approves", "approved", "fda", "ema", "recall", "recalled",
    "breakthrough", "acquires", "acquisition", "merger", "raises", "funding",
    "ipo", "results", "phase", "trial", "death", "deaths", "first", "ban",
    "banned", "lawsuit", "layoffs", "billion", "discovery", "cure",
}


def importance_score(cluster: Cluster, now: datetime | None = None) -> float:
    """A transparent, deterministic 'how big is this story' score.

    Combines three explainable signals:
      * how many distinct outlets carried it (corroboration),
      * how fresh it is,
      * whether the headline contains high-signal words.
    """
    now = now or datetime.now(timezone.utc)
    score = 3.0 * len(cluster.sources)

    latest = cluster.latest
    if latest is not None:
        age_hours = max(0.0, (now - latest).total_seconds() / 3600.0)
        if age_hours < 6:
            score += 2.0
        elif age_hours < 24:
            score += 1.0
        elif age_hours < 48:
            score += 0.5

    title_tokens = cluster.canonical.token_set()
    hits = len(title_tokens & SALIENT_TERMS)
    score += min(hits, 3) * 1.0
    return score


def rank_clusters(clusters: list[Cluster]) -> list[Cluster]:
    """Most important stories first (see :func:`importance_score`)."""
    now = datetime.now(timezone.utc)
    fallback = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(
        clusters,
        key=lambda c: (importance_score(c, now), c.latest or fallback),
        reverse=True,
    )


def limit_clusters(clusters: list[Cluster], max_items: int, max_per_topic: int) -> list[Cluster]:
    """Cap the total number of clusters and the number per topic."""
    out: list[Cluster] = []
    per_topic: dict[str, int] = {}
    for cluster in clusters:
        if max_per_topic:
            count = per_topic.get(cluster.topic, 0)
            if count >= max_per_topic:
                continue
            per_topic[cluster.topic] = count + 1
        out.append(cluster)
        if max_items and len(out) >= max_items:
            break
    return out
