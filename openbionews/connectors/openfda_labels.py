"""openFDA drug-labeling connector.

Surfaces the current FDA structured product label (SPL) for a watched drug — its
approved indications and any boxed warning — one Item per drug, cited to the
reproducible openFDA label query. This is reference data (what the label says
today), not a dated feed, so records are age-exempt. Public JSON API, no key
required; server-side, so no browser CORS limits.

Docs: https://open.fda.gov/apis/drug/label/
"""

from __future__ import annotations

import urllib.parse

from .. import textutil
from ..httputil import HTTPJSONError, get_json
from ..models import Citation, Item
from .base import Connector

API_URL = "https://api.fda.gov/drug/label.json"
# openFDA's +AND+/+OR+ operators and quoted phrases must survive URL-encoding.
_SAFE = '+:()' + '"'


def _drug_clause(term: str) -> str:
    t = term.strip().replace('"', "")
    if not t:
        return ""
    return ('(openfda.brand_name:"%s"+OR+openfda.generic_name:"%s"+OR+'
            'openfda.substance_name:"%s")' % (t, t, t))


def _first_text(value) -> str:
    if isinstance(value, list):
        return " ".join(str(v) for v in value if v)
    return str(value) if value else ""


def record_to_item(term: str, rec: dict, topic: str = "fda_labels",
                   summary_chars: int = 600) -> Item:
    of = rec.get("openfda", {}) or {}
    brand = (of.get("brand_name") or [term])[0] if of.get("brand_name") else term
    manufacturer = (of.get("manufacturer_name") or [""])[0] if of.get("manufacturer_name") else ""
    indications = textutil.strip_html(_first_text(rec.get("indications_and_usage")))
    boxed = textutil.strip_html(_first_text(rec.get("boxed_warning")))
    if len(indications) > summary_chars:
        indications = indications[:summary_chars].rsplit(" ", 1)[0] + "…"
    bits = []
    if boxed:
        bits.append("⚠ Boxed warning on the label.")
    if indications:
        bits.append("Indications: " + indications)
    summary = " ".join(bits) or "FDA label on file; no indication text parsed."

    enc = urllib.parse.quote(_drug_clause(term), safe=_SAFE)
    url = f"{API_URL}?search={enc}&limit=1"
    tag_parts = [x for x in ("Boxed warning" if boxed else "", manufacturer) if x]
    return Item(
        title=f"{brand} — FDA label (indications & warnings)",
        link=url,
        summary=summary,
        source="openFDA (Drug Labeling)",
        topic=topic,
        published=None,                                  # reference data, not a dated event
        guid=f"label|{term.lower()}",
        citations=[Citation(label=f"openFDA label: {brand}", url=url, kind="fda")],
        tag=" · ".join(tag_parts),
        meta={"term": term, "boxed_warning": bool(boxed), "manufacturer": manufacturer},
        age_exempt=True,
    )


def parse_labels(payload: dict, term: str, topic: str = "fda_labels",
                 summary_chars: int = 600) -> list[Item]:
    items: list[Item] = []
    for rec in (payload.get("results", []) or [])[:1]:       # one label per drug
        items.append(record_to_item(term, rec, topic=topic, summary_chars=summary_chars))
    return items


class OpenFDALabelsConnector(Connector):
    name = "openFDA (Drug Labeling)"
    topic = "fda_labels"

    def __init__(self, cfg: dict, watchlist: dict) -> None:
        super().__init__(cfg, watchlist)
        self.summary_chars = int(cfg.get("summary_chars", 600) or 600)
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
            return False, "no drugs/interventions on the watch list to look up"
        return True, f"{len(drugs)} drug label(s)"

    def _raw_query(self, term: str) -> str:
        enc = urllib.parse.quote(_drug_clause(term), safe=_SAFE)
        return f"search={enc}&limit=1"

    def fetch(self) -> list[Item]:
        items: list[Item] = []
        for term in self._drugs()[: self.max_total]:
            try:
                payload = get_json(API_URL, raw_query=self._raw_query(term),
                                   timeout=30, not_found_ok=True)
            except HTTPJSONError as exc:
                raise HTTPJSONError(f"{term}: {exc}") from exc
            items.extend(parse_labels(payload, term, topic=self.topic,
                                      summary_chars=self.summary_chars))
        return items
