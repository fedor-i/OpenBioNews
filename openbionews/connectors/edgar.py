"""SEC EDGAR full-text search connector.

Reads EDGAR's full-text search index (efts.sec.gov) for recent filings that
match a watch list, and turns each hit into an Item that cites the filing
document. This is the reliable server-side path that a browser cannot take:
SEC requires a descriptive User-Agent and does not consistently allow
cross-origin (in-browser) requests, but a server-to-server call has neither
limit.

Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ..httputil import HTTPJSONError, get_json
from ..models import Citation, Item
from .base import Connector

API_URL = "https://efts.sec.gov/LATEST/search-index"
DEFAULT_UA = "OpenBioNews/0.3 (contact: set email in config; +https://github.com/fedor-i/OpenBioNews)"


def _accession_url(hit_id: str, ciks) -> tuple[str, str]:
    """Return (document_url, accession) from an EDGAR hit _id and cik list."""
    accn, _, filename = (hit_id or "").partition(":")
    cik = (ciks[0] if ciks else "") or ""
    cik_int = str(int(cik)) if cik.isdigit() else cik
    accn_nodash = accn.replace("-", "")
    if accn and filename and cik_int:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{filename}"
    elif cik_int:
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_int}"
    else:
        url = "https://www.sec.gov/edgar/search/"
    return url, accn


def hit_to_item(hit: dict, topic: str = "sec_filings") -> Item | None:
    src = hit.get("_source", {}) or {}
    ciks = src.get("ciks") or []
    url, accn = _accession_url(hit.get("_id", ""), ciks)
    form = src.get("root_form") or src.get("form") or src.get("file_type") or "Filing"
    names = src.get("display_names") or []
    company = names[0] if names else (src.get("file_description") or "SEC filing")
    company = re.sub(r"\s*\(CIK\s*\d+\)\s*$", "", company)  # drop the "(CIK …)" suffix
    date_text = src.get("file_date") or ""
    published = None
    try:
        published = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass
    if not company and not accn:
        return None
    return Item(
        title=f"{company} — {form}",
        link=url,
        summary=src.get("file_description", "") or f"{form} filing",
        source="SEC EDGAR",
        topic=topic,
        published=published,
        guid=hit.get("_id", "") or accn,
        citations=[Citation(label=f"EDGAR {accn or 'filing'}", url=url, kind="filing")],
        tag=" · ".join(x for x in (form, ", ".join(names[1:3])) if x),
        meta={"form": form, "ciks": ciks, "accession": accn},
        age_exempt=True,
    )


def parse_hits(payload: dict, topic: str = "sec_filings") -> list[Item]:
    items: list[Item] = []
    for hit in (((payload.get("hits") or {}).get("hits")) or []):
        item = hit_to_item(hit, topic=topic)
        if item is not None:
            items.append(item)
    return items


class EdgarConnector(Connector):
    name = "SEC EDGAR"
    topic = "sec_filings"

    def __init__(self, cfg: dict, watchlist: dict) -> None:
        super().__init__(cfg, watchlist)
        self.recent_days = int(cfg.get("recent_days", 30) or 0)
        self.forms = [f for f in cfg.get("forms", []) if f]
        self.max_per_query = int(cfg.get("max_per_query", 20) or 20)
        self.max_total = int(cfg.get("max_total", 40) or 40)
        self.user_agent = cfg.get("user_agent") or DEFAULT_UA

    def _query_values(self) -> list[str]:
        wl = self.watchlist
        vals = []
        for key in ("sponsors", "interventions", "terms"):
            vals.extend(wl.get(key, []))
        return [v for v in vals if v and v.strip()]

    def available(self) -> tuple[bool, str]:
        if not self._query_values():
            return False, "no watch list (add sponsors/drugs/terms)"
        note = f"{len(self._query_values())} quer(ies)"
        if self.user_agent == DEFAULT_UA:
            note += " — set connectors.edgar.user_agent to your email (SEC asks for one)"
        return True, note

    def _params(self, q: str, offset: int) -> dict:
        params = {"q": q}
        if self.forms:
            params["forms"] = ",".join(self.forms)
        if self.recent_days:
            start = (datetime.now(timezone.utc) - timedelta(days=self.recent_days)).strftime("%Y-%m-%d")
            params["dateRange"] = "custom"
            params["startdt"] = start
            params["enddt"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if offset:
            params["from"] = offset
        return params

    def fetch(self) -> list[Item]:
        values = self._query_values()
        if not values:
            return []
        headers = {"User-Agent": self.user_agent}
        by_id: dict[str, Item] = {}
        for q in values:
            try:
                payload = get_json(API_URL, params=self._params(q, 0),
                                   headers=headers, timeout=30)
            except HTTPJSONError as exc:
                raise HTTPJSONError(f"q={q}: {exc}") from exc
            count = 0
            for item in parse_hits(payload, topic=self.topic):
                by_id.setdefault(item.guid, item)
                count += 1
                if count >= self.max_per_query:
                    break
            if len(by_id) >= self.max_total:
                break
        items = list(by_id.values())
        items.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
                   reverse=True)
        return items[: self.max_total]
