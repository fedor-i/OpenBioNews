"""openFDA drug-enforcement (recalls) connector.

Reads the FDA's enforcement-report dataset — drug recalls with their reason,
classification (Class I/II/III), status and dates — and turns recent ones into
Items that cite the FDA record. Public JSON API, no key required (an optional
key raises the rate limit). Server-side, so no browser CORS limits apply.

Docs: https://open.fda.gov/apis/drug/enforcement/
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone

from .. import textutil
from ..httputil import HTTPJSONError, get_json
from ..models import Citation, Item
from .base import Connector

API_URL = "https://api.fda.gov/drug/enforcement.json"


def _parse_date(text: str | None) -> datetime | None:
    """openFDA dates are YYYYMMDD strings."""
    if not text or len(text) != 8:
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def record_to_item(rec: dict, topic: str = "fda_recalls") -> Item | None:
    """Map one openFDA enforcement record into an Item."""
    firm = rec.get("recalling_firm", "")
    product = rec.get("product_description", "")
    reason = rec.get("reason_for_recall", "")
    classification = rec.get("classification", "")
    status = rec.get("status", "")
    number = rec.get("recall_number", "")
    brand = (rec.get("openfda", {}) or {}).get("brand_name") or []

    title = (brand[0] if brand else "") or textutil.first_sentences(product, 1, 90) \
        or (f"{firm} recall" if firm else "FDA drug recall")
    if not number and not product and not firm:
        return None

    # The authoritative record on openFDA (human-readable FDA recalls page is
    # not per-record addressable, so cite the openFDA record for provenance).
    if number:
        src = f"{API_URL}?search=recall_number:%22{urllib.parse.quote(number)}%22"
    else:
        src = "https://www.fda.gov/drugs/drug-recalls"

    tag_parts = [x for x in (classification, status, firm) if x]
    return Item(
        title=title.strip(),
        link=src,
        summary=textutil.strip_html(reason),
        source="openFDA (Drug Recalls)",
        topic=topic,
        published=_parse_date(rec.get("report_date")),
        guid=number or (firm + product)[:80],
        citations=[Citation(label=f"FDA recall {number or 'record'}", url=src, kind="fda")],
        tag=" · ".join(tag_parts),
        meta={
            "recall_number": number,
            "classification": classification,
            "status": status,
            "firm": firm,
            "product": product,
            "track": {k: v for k, v in
                      (("Classification", classification), ("Status", status)) if v},
        },
        age_exempt=True,
    )


def parse_enforcement(payload: dict, topic: str = "fda_recalls") -> list[Item]:
    items: list[Item] = []
    for rec in payload.get("results", []) or []:
        item = record_to_item(rec, topic=topic)
        if item is not None:
            items.append(item)
    return items


class OpenFDAConnector(Connector):
    name = "openFDA (Drug Recalls)"
    topic = "fda_recalls"

    def __init__(self, cfg: dict, watchlist: dict) -> None:
        super().__init__(cfg, watchlist)
        self.recent_days = int(cfg.get("recent_days", 30) or 0)
        self.max_per_query = int(cfg.get("max_per_query", 20) or 20)
        self.max_total = int(cfg.get("max_total", 40) or 40)
        self.classifications = [c for c in cfg.get("classifications", []) if c]

    def _queries(self) -> list[tuple[str, str]]:
        wl = self.watchlist
        pairs: list[tuple[str, str]] = []
        for value in wl.get("sponsors", []):
            pairs.append(("recalling_firm", value))
        for value in wl.get("interventions", []):
            pairs.append(("product_description", value))
        for value in wl.get("terms", []):
            pairs.append(("reason_for_recall", value))
        pairs = [(f, v) for f, v in pairs if v and v.strip()]
        # With no entity watch list, fall back to "all recent recalls".
        if not pairs and self.recent_days:
            pairs = [("", "")]
        return pairs

    def available(self) -> tuple[bool, str]:
        if not self._queries():
            return False, "no watch list and no recency window set"
        return True, f"{len(self._queries())} quer(ies), last {self.recent_days} days"

    def _build_raw_query(self, field: str, value: str) -> str:
        terms = []
        if field and value:
            terms.append(f'{field}:"{value.replace(chr(34), "")}"')
        if self.classifications:
            if len(self.classifications) == 1:
                terms.append(f'classification:"{self.classifications[0]}"')
            else:
                group = " OR ".join(f'classification:"{c}"' for c in self.classifications)
                terms.append(f"({group})")
        if self.recent_days:
            start = (datetime.now(timezone.utc) - timedelta(days=self.recent_days)).strftime("%Y%m%d")
            end = datetime.now(timezone.utc).strftime("%Y%m%d")
            terms.append(f"report_date:[{start}+TO+{end}]")
        search = "+AND+".join(terms) if terms else ""
        # Encode each term but keep the +AND+/+TO+ operators and quotes usable.
        enc = urllib.parse.quote(search, safe='+:[]"()')
        return f"search={enc}&sort=report_date:desc&limit={self.max_per_query}"

    def fetch(self) -> list[Item]:
        queries = self._queries()
        if not queries:
            return []
        by_id: dict[str, Item] = {}
        for field, value in queries:
            raw = self._build_raw_query(field, value)
            try:
                payload = get_json(API_URL, raw_query=raw, timeout=30, not_found_ok=True)
            except HTTPJSONError as exc:
                raise HTTPJSONError(f"{field or 'recent'}={value}: {exc}") from exc
            for item in parse_enforcement(payload, topic=self.topic):
                key = item.meta.get("recall_number") or item.guid
                by_id.setdefault(key, item)
            if len(by_id) >= self.max_total:
                break
        items = list(by_id.values())
        items.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
                   reverse=True)
        return items[: self.max_total]
