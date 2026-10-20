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
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_UA = "OpenBioNews/0.3 (contact: set email in config; +https://github.com/fedor-i/OpenBioNews)"

# Corporate-form words dropped when matching a name to a registrant (so
# "Viking Therapeutics Inc" resolves from "Viking Therapeutics"). Industry words
# like "therapeutics" are kept — they're what make the name distinctive.
_FORM_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited",
    "plc", "llc", "lp", "sa", "nv", "ag", "the",
}
_TICKERS_CACHE: list[dict] | None = None


def _norm_name(text: str) -> str:
    """Lowercase, keep alphanumerics, drop corporate-form suffix words."""
    tokens = [t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
              if t not in _FORM_SUFFIXES]
    return " ".join(tokens)


def _load_tickers(user_agent: str | None) -> list[dict]:
    """SEC's registrant directory (ticker + CIK + title), fetched once per process."""
    global _TICKERS_CACHE
    if _TICKERS_CACHE is None:
        payload = get_json(TICKERS_URL, headers={"User-Agent": user_agent or DEFAULT_UA},
                           timeout=30)
        rows = payload.values() if isinstance(payload, dict) else (payload or [])
        _TICKERS_CACHE = [
            {"cik": str(r["cik_str"]).zfill(10),
             "ticker": str(r.get("ticker", "")).upper(),
             "norm": _norm_name(r.get("title", "")),
             "title": r.get("title", "")}
            for r in rows if isinstance(r, dict) and r.get("cik_str")
        ]
    return _TICKERS_CACHE


def resolve_cik(name: str, user_agent: str | None = None) -> str | None:
    """Resolve a company name, ticker, or raw CIK to a zero-padded 10-digit CIK.

    Returns None if nothing matches confidently — the caller then reports the
    entity as not found rather than silently falling back to a noisy full-text
    search (which is what let third-party filings leak in before).
    """
    if not name or not name.strip():
        return None
    raw = name.strip()
    if raw.isdigit():                                  # already a CIK
        return raw.zfill(10)
    try:
        rows = _load_tickers(user_agent)
    except HTTPJSONError:
        return None
    upper = raw.upper()
    for r in rows:                                     # exact ticker (e.g. VKTX)
        if r["ticker"] and r["ticker"] == upper:
            return r["cik"]
    want = _norm_name(raw)
    if not want:
        return None
    exact = [r for r in rows if r["norm"] == want]
    if exact:
        return min(exact, key=lambda r: len(r["title"]))["cik"]
    want_tokens = set(want.split())                    # all query tokens appear in title
    subset = [r for r in rows if want_tokens and want_tokens.issubset(set(r["norm"].split()))]
    if subset:
        return min(subset, key=lambda r: len(r["norm"]))["cik"]
    return None


def submission_to_item(cik, entity: str, form: str, filing_date: str, accn: str,
                       primary_doc: str, desc: str, topic: str) -> Item:
    """One row of a registrant's submissions feed as an Item (its own filing)."""
    cik_int = str(int(cik)) if str(cik).isdigit() else str(cik)
    accn_nodash = (accn or "").replace("-", "")
    if accn_nodash and primary_doc:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{primary_doc}"
    elif accn_nodash:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/"
    else:
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_int}"
    published = None
    try:
        published = datetime.strptime(filing_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass
    return Item(
        title=f"{entity} — {form}",
        link=url,
        summary=desc or f"{form} filing",
        source="SEC EDGAR",
        topic=topic,
        published=published,
        guid=f"{accn}:{primary_doc}" if accn else (primary_doc or url),
        citations=[Citation(label=f"EDGAR {accn or 'filing'}", url=url, kind="filing")],
        tag=form,
        meta={"form": form, "ciks": [str(cik).zfill(10)], "accession": accn,
              "filer": entity, "track": ({"Form": form} if form else {})},
        age_exempt=True,
    )


def parse_submissions(payload: dict, topic: str = "sec_filings") -> list[Item]:
    """Turn a data.sec.gov submissions feed into Items (the entity's own filings)."""
    entity = payload.get("name") or ""
    cik = payload.get("cik") or ""
    recent = ((payload.get("filings") or {}).get("recent")) or {}
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accns = recent.get("accessionNumber") or []
    docs = recent.get("primaryDocument") or []
    descs = recent.get("primaryDocDescription") or []
    items: list[Item] = []
    for i, accn in enumerate(accns):
        items.append(submission_to_item(
            cik, entity,
            forms[i] if i < len(forms) else "",
            dates[i] if i < len(dates) else "",
            accn,
            docs[i] if i < len(docs) else "",
            descs[i] if i < len(descs) else "",
            topic))
    return items


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
        meta={"form": form, "ciks": ciks, "accession": accn,
              "track": ({"Form": form} if form else {})},
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
        # When set, scope to these registrants' OWN filings (data.sec.gov
        # submissions) instead of a full-text search that also matches filings
        # by third parties merely mentioning the name.
        self.ciks = [str(c) for c in (cfg.get("ciks") or []) if c]

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

    def _fetch_entity(self, headers: dict) -> list[Item]:
        """A registrant's own recent filings, from the submissions feed."""
        cutoff = None
        if self.recent_days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.recent_days)
        refine = [t.lower() for t in self._query_values()]  # optional within-entity text
        by_id: dict[str, Item] = {}
        for cik in self.ciks:
            try:
                payload = get_json(SUBMISSIONS_URL.format(cik=str(cik).zfill(10)),
                                   headers=headers, timeout=30)
            except HTTPJSONError as exc:
                raise HTTPJSONError(f"cik={cik}: {exc}") from exc
            for item in parse_submissions(payload, topic=self.topic):
                form = (item.meta.get("form") or "").lower()
                if self.forms and not any(f.lower() in form for f in self.forms):
                    continue
                if cutoff and item.published and item.published < cutoff:
                    continue
                if refine:
                    hay = (item.title + " " + (item.summary or "")).lower()
                    if not any(t in hay for t in refine):
                        continue
                by_id.setdefault(item.guid, item)
        items = list(by_id.values())
        items.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
                   reverse=True)
        return items[: self.max_total]

    def fetch(self) -> list[Item]:
        headers = {"User-Agent": self.user_agent}
        if self.ciks:                                 # entity-scoped: own filings only
            return self._fetch_entity(headers)
        values = self._query_values()
        if not values:
            return []
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
