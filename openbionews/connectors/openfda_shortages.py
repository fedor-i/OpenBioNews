"""openFDA drug-shortages connector.

Surfaces current (and optionally resolved) drug shortages from the FDA's drug
shortages dataset, filtered to a watch list and a recency window, each cited to
the FDA Drug Shortages database. Public JSON API, no key required; server-side,
so no browser CORS limits.

Docs: https://open.fda.gov/apis/drug/shortages/
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone

from .. import textutil
from ..httputil import HTTPJSONError, get_json
from ..models import Citation, Item
from .base import Connector

API_URL = "https://api.fda.gov/drug/shortages.json"
FDA_SHORTAGES_SEARCH = "https://dps.fda.gov/drugshortages/search"


def _parse_date(text):
    if not text:
        return None
    text = str(text).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19] if "T" in text else text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _first(value) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value) if value else ""


def record_to_item(rec: dict, topic: str = "fda_shortages") -> Item | None:
    of = rec.get("openfda", {}) or {}
    generic = _first(rec.get("generic_name")) or _first(of.get("generic_name"))
    prop = _first(rec.get("proprietary_name")) or _first(of.get("brand_name"))
    name = (prop or generic or "").strip() or "Drug shortage"
    company = (rec.get("company_name") or "").strip()
    status = (rec.get("status") or "").strip()
    reason = rec.get("reason_for_shortage") or rec.get("availability") or ""
    published = _parse_date(rec.get("update_date") or rec.get("change_date")
                            or rec.get("initial_posting_date"))

    url = f"{FDA_SHORTAGES_SEARCH}?query={urllib.parse.quote(name)}"
    cats = rec.get("therapeutic_category") or []
    if isinstance(cats, str):
        cats = [cats]
    tag_parts = [x for x in (status, (cats[0] if cats else ""), company) if x]

    return Item(
        title=f"{name} — shortage" + (f" ({status})" if status else ""),
        link=url,
        summary=textutil.strip_html(reason),
        source="openFDA (Drug Shortages)",
        topic=topic,
        published=published,
        guid=f"{name}|{company}|{rec.get('update_date') or rec.get('initial_posting_date') or ''}",
        citations=[Citation(label=f"FDA Drug Shortages: {name}", url=url, kind="fda")],
        tag=" · ".join(tag_parts),
        meta={"status": status, "company": company, "categories": cats},
        age_exempt=True,
    )


def parse_shortages(payload: dict, topic: str = "fda_shortages") -> list[Item]:
    items: list[Item] = []
    for rec in payload.get("results", []) or []:
        item = record_to_item(rec, topic=topic)
        if item is not None:
            items.append(item)
    return items


class OpenFDAShortagesConnector(Connector):
    name = "openFDA (Drug Shortages)"
    topic = "fda_shortages"

    def __init__(self, cfg: dict, watchlist: dict) -> None:
        super().__init__(cfg, watchlist)
        self.recent_days = int(cfg.get("recent_days", 60) or 0)
        self.max_per_query = int(cfg.get("max_per_query", 20) or 20)
        self.max_total = int(cfg.get("max_total", 40) or 40)
        self.statuses = [s for s in cfg.get("statuses", ["Current"]) if s]

    def _entity_exprs(self) -> list[str]:
        wl = self.watchlist
        exprs: list[str] = []
        for s in wl.get("sponsors", []):
            if s.strip():
                exprs.append(f'company_name:"{s.strip()}"')
        for value in list(wl.get("interventions", [])) + list(wl.get("terms", [])):
            v = value.strip()
            if v:
                exprs.append(f'(generic_name:"{v}"+OR+proprietary_name:"{v}")')
        # No entities → all shortages (filtered by status below).
        if not exprs:
            exprs = [""]
        return exprs

    def available(self) -> tuple[bool, str]:
        status = ("status " + "/".join(self.statuses)) if self.statuses else "any status"
        return True, f"{len(self._entity_exprs())} quer(ies), {status}, last {self.recent_days} days"

    def _raw_query(self, expr: str) -> str:
        terms = []
        if expr:
            terms.append(expr)
        if self.statuses:
            if len(self.statuses) == 1:
                terms.append(f'status:"{self.statuses[0]}"')
            else:
                terms.append("(" + " OR ".join(f'status:"{s}"' for s in self.statuses) + ")")
        search = "+AND+".join(terms)
        enc = urllib.parse.quote(search, safe='+:"()')
        # Recency is applied client-side (date field formats vary), so no date
        # range or sort in the query — both risk silently returning nothing.
        return f"search={enc}&limit={self.max_per_query}" if search else f"limit={self.max_per_query}"

    def fetch(self) -> list[Item]:
        cutoff = None
        if self.recent_days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.recent_days)
        by_id: dict[str, Item] = {}
        for expr in self._entity_exprs():
            try:
                payload = get_json(API_URL, raw_query=self._raw_query(expr),
                                   timeout=30, not_found_ok=True)
            except HTTPJSONError as exc:
                raise HTTPJSONError(f"{expr or 'all'}: {exc}") from exc
            for item in parse_shortages(payload, topic=self.topic):
                # Keep undated records; only drop clearly-stale dated ones.
                if cutoff and item.published is not None and item.published < cutoff:
                    continue
                by_id.setdefault(item.guid, item)
            if len(by_id) >= self.max_total:
                break
        items = list(by_id.values())
        items.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
                   reverse=True)
        return items[: self.max_total]
