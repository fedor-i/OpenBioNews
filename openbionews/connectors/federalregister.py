"""Federal Register connector.

Surfaces FDA regulatory documents — guidances, advisory-committee (adcomm)
meeting notices, proposed and final rules — from the Federal Register, the daily
journal of the US government. These are the primary records behind a regulatory
calendar: when the FDA asks for comment, announces a panel, or finalises a rule.
Public JSON API, no key required; server-side, so no browser CORS limits.

Docs: https://www.federalregister.gov/developers/documentation/api/v1
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .. import textutil
from ..httputil import HTTPJSONError, get_json
from ..models import Citation, Item
from .base import Connector

API_URL = "https://www.federalregister.gov/api/v1/documents.json"
# The default agency filter — FDA. (Federal Register agency "slug".)
FDA_SLUG = "food-and-drug-administration"
FIELDS = ["title", "html_url", "publication_date", "abstract", "type",
          "document_number", "agencies"]


def _parse_date(text):
    if not text:
        return None
    try:
        return datetime.strptime(str(text)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def record_to_item(rec: dict, topic: str = "federal_register") -> Item | None:
    url = (rec.get("html_url") or "").strip()
    title = (rec.get("title") or "").strip()
    if not url or not title:
        return None
    doc_type = (rec.get("type") or "").strip()          # Notice / Rule / Proposed Rule …
    agencies = [a.get("name", "") for a in (rec.get("agencies") or []) if a.get("name")]
    published = _parse_date(rec.get("publication_date"))
    docnum = (rec.get("document_number") or "").strip()
    tag_parts = [x for x in (doc_type, (agencies[0] if agencies else "")) if x]
    return Item(
        title=title,
        link=url,
        summary=textutil.strip_html(rec.get("abstract") or ""),
        source="Federal Register",
        topic=topic,
        published=published,
        guid=docnum or url,
        citations=[Citation(label=f"Federal Register: {docnum or title}", url=url,
                            kind="regulation")],
        tag=" · ".join(tag_parts),
        meta={"type": doc_type, "agencies": agencies, "document_number": docnum},
    )


def parse_documents(payload: dict, topic: str = "federal_register") -> list[Item]:
    items: list[Item] = []
    for rec in payload.get("results", []) or []:
        item = record_to_item(rec, topic=topic)
        if item is not None:
            items.append(item)
    return items


class FederalRegisterConnector(Connector):
    name = "Federal Register"
    topic = "federal_register"

    def __init__(self, cfg: dict, watchlist: dict) -> None:
        super().__init__(cfg, watchlist)
        self.recent_days = int(cfg.get("recent_days", 30) or 0)
        self.max_per_query = int(cfg.get("max_per_query", 20) or 20)
        self.max_total = int(cfg.get("max_total", 40) or 40)
        # Default to FDA; allow override/clearing via config.
        self.agencies = cfg.get("agencies", [FDA_SLUG])
        if isinstance(self.agencies, str):
            self.agencies = [self.agencies]

    def _terms(self) -> list[str]:
        wl = self.watchlist
        seen, out = set(), []
        for value in (list(wl.get("terms", [])) + list(wl.get("interventions", []))
                      + list(wl.get("sponsors", []))):
            v = value.strip()
            k = v.lower()
            if v and k not in seen:
                seen.add(k)
                out.append(v)
        return out or [""]

    def available(self) -> tuple[bool, str]:
        who = ", ".join(self.agencies) if self.agencies else "all agencies"
        return True, f"{len([t for t in self._terms() if t])} term(s), {who}, last {self.recent_days} days"

    def _params(self, term: str) -> dict:
        params = {
            "per_page": self.max_per_query,
            "order": "newest",
            "fields[]": FIELDS,
        }
        if term:
            params["conditions[term]"] = term
        for slug in self.agencies:
            params.setdefault("conditions[agencies][]", [])
            params["conditions[agencies][]"].append(slug)
        if self.recent_days:
            since = (datetime.now(timezone.utc) - timedelta(days=self.recent_days)).strftime("%Y-%m-%d")
            params["conditions[publication_date][gte]"] = since
        return params

    def fetch(self) -> list[Item]:
        by_id: dict[str, Item] = {}
        for term in self._terms():
            try:
                payload = get_json(API_URL, params=self._params(term),
                                   timeout=30, not_found_ok=True)
            except HTTPJSONError as exc:
                raise HTTPJSONError(f"{term or 'all'}: {exc}") from exc
            for item in parse_documents(payload, topic=self.topic):
                by_id.setdefault(item.guid, item)
            if len(by_id) >= self.max_total:
                break
        items = list(by_id.values())
        items.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
                   reverse=True)
        return items[: self.max_total]
