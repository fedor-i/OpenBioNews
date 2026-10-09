"""PubMed connector (NCBI E-utilities).

Surfaces biomedical literature for a watch list — the publications behind a
target, drug or trial — each cited to its PubMed record (and DOI when present).
Two calls: ``esearch`` for matching PMIDs, then ``esummary`` for their metadata.
Public API, no key required (a key only raises the rate limit); server-side, so
no browser CORS limits.

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .. import textutil
from ..httputil import HTTPJSONError, get_json
from ..models import Citation, Item
from .base import Connector

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PUBMED_URL = "https://pubmed.ncbi.nlm.nih.gov/"


def _parse_pubdate(text):
    """PubMed dates come as "2026 Oct 1", "2026 Oct", or "2026" (and sometimes a
    season). Try the specific forms, then fall back to a leading 4-digit year."""
    if not text:
        return None
    text = str(text).strip()
    for fmt in ("%Y %b %d", "%Y %b"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    m = re.match(r"(\d{4})", text)
    if m:
        try:
            return datetime(int(m.group(1)), 1, 1, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _doi(rec: dict) -> str:
    for aid in rec.get("articleids", []) or []:
        if aid.get("idtype") == "doi" and aid.get("value"):
            return str(aid["value"])
    return ""


def summary_to_item(pmid: str, rec: dict, topic: str = "pubmed") -> Item | None:
    title = textutil.strip_html(rec.get("title") or "").strip()
    if not title:
        return None
    journal = (rec.get("fulljournalname") or rec.get("source") or "").strip()
    authors = [a.get("name", "") for a in (rec.get("authors") or []) if a.get("name")]
    who = authors[0] + (" et al." if len(authors) > 1 else "") if authors else ""
    pubdate = rec.get("pubdate") or rec.get("epubdate") or ""
    url = f"{PUBMED_URL}{pmid}/"
    doi = _doi(rec)
    bits = [x for x in (who, journal, str(pubdate)) if x]
    citations = [Citation(label=f"PubMed PMID {pmid}", url=url, kind="publication")]
    if doi:
        citations.append(Citation(label=f"DOI {doi}", url=f"https://doi.org/{doi}", kind="publication"))
    return Item(
        title=title,
        link=url,
        summary=" · ".join(bits),
        source="PubMed",
        topic=topic,
        published=_parse_pubdate(pubdate),
        guid=f"pmid:{pmid}",
        citations=citations,
        tag=journal,
        meta={"pmid": pmid, "doi": doi, "journal": journal, "authors": authors},
    )


def parse_summary(payload: dict, topic: str = "pubmed") -> list[Item]:
    result = payload.get("result", {}) or {}
    order = result.get("uids") or [k for k in result.keys() if k != "uids"]
    items: list[Item] = []
    for pmid in order:
        rec = result.get(pmid)
        if isinstance(rec, dict):
            item = summary_to_item(str(pmid), rec, topic=topic)
            if item is not None:
                items.append(item)
    return items


class PubMedConnector(Connector):
    name = "PubMed"
    topic = "pubmed"

    def __init__(self, cfg: dict, watchlist: dict) -> None:
        super().__init__(cfg, watchlist)
        self.recent_days = int(cfg.get("recent_days", 365) or 0)
        self.max_per_query = int(cfg.get("max_per_query", 10) or 10)
        self.max_total = int(cfg.get("max_total", 30) or 30)
        self.api_key = cfg.get("api_key", "")

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
        return out

    def available(self) -> tuple[bool, str]:
        terms = self._terms()
        if not terms:
            return False, "no terms on the watch list to search PubMed"
        return True, f"{len(terms)} term(s), last {self.recent_days} days"

    def _esearch_params(self, term: str) -> dict:
        params = {"db": "pubmed", "term": term, "retmax": self.max_per_query,
                  "retmode": "json", "sort": "date"}
        if self.recent_days:
            params["reldate"] = self.recent_days
            params["datetype"] = "pdat"
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def _esummary_params(self, pmids: list[str]) -> dict:
        params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def fetch(self) -> list[Item]:
        by_id: dict[str, Item] = {}
        for term in self._terms():
            try:
                found = get_json(ESEARCH, params=self._esearch_params(term), timeout=30)
            except HTTPJSONError as exc:
                raise HTTPJSONError(f"{term}: {exc}") from exc
            pmids = (found.get("esearchresult", {}) or {}).get("idlist", []) or []
            if not pmids:
                continue
            try:
                summ = get_json(ESUMMARY, params=self._esummary_params(pmids), timeout=30)
            except HTTPJSONError as exc:
                raise HTTPJSONError(f"{term} (esummary): {exc}") from exc
            for item in parse_summary(summ, topic=self.topic):
                by_id.setdefault(item.guid, item)
            if len(by_id) >= self.max_total:
                break
        items = list(by_id.values())
        items.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
                   reverse=True)
        return items[: self.max_total]
