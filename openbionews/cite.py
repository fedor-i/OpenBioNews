"""Per-sentence source attribution — deterministic, no LLM.

Every sentence in a story's brief is a verbatim sentence lifted from a
primary-source record (a ClinicalTrials.gov study, an FDA record, an EDGAR
filing), so the sentence-to-source binding is exact. There is no generated
prose here and therefore nothing to hallucinate: this is the honest core of
OpenBioNews's "cited" promise, and it needs no model to run.

``attribute`` walks a cluster's items — the earliest/canonical first, then the
rest — taking the lead sentence from each distinct source before filling in
further detail, so a multi-source story surfaces several primary sources rather
than repeating one. Each returned :class:`~openbionews.models.Claim` carries the
citation of the item its sentence came from.
"""

from __future__ import annotations

from . import textutil
from .models import Citation, Claim, Cluster


def _primary_citation(item) -> "Citation | None":
    return item.citations[0] if item.citations else None


def attribute(cluster: Cluster, max_claims: int = 4) -> list[Claim]:
    """Return the source-bound sentences that make up a cluster's brief."""
    # Canonical (earliest) first, then the remaining items in their given order.
    ordered = [cluster.canonical]
    ordered += [i for i in cluster.items if i is not cluster.canonical]

    # (item, [sentences]) once, so both passes reuse the same split.
    split = [(item, textutil.split_sentences(item.summary)) for item in ordered]

    claims: list[Claim] = []
    seen: set[str] = set()

    def take(text: str, citation) -> bool:
        key = text.strip().lower()
        if not key or key in seen:
            return False
        seen.add(key)
        claims.append(Claim(text=text.strip(), citation=citation))
        return len(claims) >= max_claims

    # Pass 1: the lead sentence of each distinct source.
    for item, sentences in split:
        if sentences and take(sentences[0], _primary_citation(item)):
            return claims

    # Pass 2: fill out with the remaining sentences, canonical first.
    for item, sentences in split:
        citation = _primary_citation(item)
        for sentence in sentences[1:]:
            if take(sentence, citation):
                return claims

    # Nothing but a headline to work with: cite the title to its own source.
    if not claims:
        c = cluster.canonical
        claims.append(Claim(text=c.title, citation=_primary_citation(c)))
    return claims


def number_citations(claims: list[Claim]):
    """Assign stable [n] markers to the distinct citations across ``claims``.

    Returns ``(markers, ordered)`` where ``markers`` maps each claim's index in
    ``claims`` to its 1-based citation number (absent for uncited claims), and
    ``ordered`` is the list of ``(number, Citation)`` in first-appearance order —
    the source key rendered beneath the brief.
    """
    order: dict[str, int] = {}
    ordered: list[tuple[int, Citation]] = []
    markers: dict[int, int] = {}
    for i, claim in enumerate(claims):
        cite = claim.citation
        if cite is None or not cite.url:
            continue
        n = order.get(cite.url)
        if n is None:
            n = len(ordered) + 1
            order[cite.url] = n
            ordered.append((n, cite))
        markers[i] = n
    return markers, ordered
