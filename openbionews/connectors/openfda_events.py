"""openFDA FAERS adverse-events connector.

Individual FAERS reports are one patient each — too noisy to digest. Instead
this summarises, per watched drug, the *most-reported adverse reactions* in a
recency window, using openFDA's server-side ``count`` aggregation, and cites the
reproducible openFDA query. One high-signal Item per drug, not a flood of
single-patient reports. Public JSON API, no key required; server-side, so no
browser CORS limits.

FAERS is spontaneous reporting: a reaction count is *not* an incidence rate and
does not establish that the drug caused the event. The summary says so.

Docs: https://open.fda.gov/apis/drug/event/
"""

from __future__ import annotations

import urllib.parse

from ..httputil import HTTPJSONError, get_json
from ..models import Citation, Item
from .base import Connector

API_URL = "https://api.fda.gov/drug/event.json"
# openFDA's +AND+/+OR+ operators and quoted phrases must survive URL-encoding.
_SAFE = '+:()' + '"'
# Human-facing primary source: the FDA FAERS public dashboard.
FAERS_DASHBOARD = "https://fis.fda.gov/sense/app/95239e26-e0be-42d9-a960-9a5f7f1c25ee/sheet/7a47a261-d58b-4203-a8aa-6d3021737452/state/analysis"


def _drug_clause(term: str) -> str:
    t = term.strip().replace('"', "")
    if not t:
        return ""
    return ("(patient.drug.openfda.brand_name:\"%s\"+OR+"
            "patient.drug.openfda.generic_name:\"%s\"+OR+"
            "patient.drug.medicinalproduct:\"%s\")" % (t, t, t))


def build_summary(term: str, reactions: list[tuple[str, int]]) -> str:
    """One-line, de-jargoned summary of the top reactions (counts, not rates)."""
    if not reactions:
        return (f"No adverse-event reports found for {term} in the FAERS data. "
                "FAERS counts are spontaneous reports, not incidence rates.")
    top = ", ".join(f"{name.title()} ({count:,})" for name, count in reactions)
    return (f"Most-reported adverse reactions for {term} in FAERS: {top}. "
            "Counts are spontaneous reports, not incidence rates, and do not "
            "establish that the drug caused the reaction.")


def record_to_item(term: str, reactions: list[tuple[str, int]],
                    topic: str = "fda_events") -> Item:
    total = sum(c for _, c in reactions)
    enc = urllib.parse.quote(_drug_clause(term), safe=_SAFE)
    url = f"{API_URL}?search={enc}&count=patient.reaction.reactionmeddrapt.exact"
    tag = f"FAERS · {len(reactions)} reactions" + (f" · {total:,} reports" if total else "")
    return Item(
        title=f"{term} — top adverse reactions (FAERS)",
        link=url,
        summary=build_summary(term, reactions),
        source="openFDA (FAERS)",
        topic=topic,
        published=None,                         # aggregate has no single date
        guid=f"faers|{term.lower()}",
        citations=[Citation(label=f"openFDA FAERS query: {term}", url=url, kind="fda"),
                   Citation(label="FDA FAERS Public Dashboard", url=FAERS_DASHBOARD, kind="fda")],
        tag=tag,
        meta={"term": term, "reactions": reactions, "total": total},
        age_exempt=True,                        # no date → never age-filtered
    )


def parse_reactions(payload: dict, limit: int = 8) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for row in (payload.get("results", []) or [])[:limit]:
        name = str(row.get("term", "")).strip()
        try:
            count = int(row.get("count", 0))
        except (TypeError, ValueError):
            count = 0
        if name:
            out.append((name, count))
    return out


class OpenFDAEventsConnector(Connector):
    name = "openFDA (FAERS)"
    topic = "fda_events"

    def __init__(self, cfg: dict, watchlist: dict) -> None:
        super().__init__(cfg, watchlist)
        self.top_reactions = int(cfg.get("top_reactions", 8) or 8)
        self.max_total = int(cfg.get("max_total", 20) or 20)

    def _drugs(self) -> list[str]:
        wl = self.watchlist
        seen, out = set(), []
        for value in list(wl.get("interventions", [])) + list(wl.get("terms", [])):
            v = value.strip()
            k = v.lower()
            if v and k not in seen:
                seen.add(k)
                out.append(v)
        return out

    def available(self) -> tuple[bool, str]:
        drugs = self._drugs()
        if not drugs:
            # FAERS aggregation is meaningless without a drug to group by.
            return False, "no drugs/interventions on the watch list to summarise"
        return True, f"{len(drugs)} drug(s), top {self.top_reactions} reactions each"

    def _raw_query(self, term: str) -> str:
        enc = urllib.parse.quote(_drug_clause(term), safe=_SAFE)
        return f"search={enc}&count=patient.reaction.reactionmeddrapt.exact"

    def fetch(self) -> list[Item]:
        items: list[Item] = []
        for term in self._drugs()[: self.max_total]:
            try:
                payload = get_json(API_URL, raw_query=self._raw_query(term),
                                   timeout=30, not_found_ok=True)
            except HTTPJSONError as exc:
                raise HTTPJSONError(f"{term}: {exc}") from exc
            reactions = parse_reactions(payload, limit=self.top_reactions)
            if reactions:
                items.append(record_to_item(term, reactions, topic=self.topic))
        return items
