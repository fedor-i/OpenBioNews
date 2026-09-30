"""openFDA drug-approvals connector (Drugs@FDA).

Surfaces recent FDA **approvals** — the highest-signal biopharma event. It reads
the Drugs@FDA application dataset, finds submissions that were approved (status
``AP``) within the recency window, and turns each into an Item that cites the
application's Drugs@FDA page. Covers both original approvals (a new drug) and
supplemental approvals (e.g. a new indication).

Public JSON API, no key required. Server-side, so no browser CORS limits.

Docs: https://open.fda.gov/apis/drug/drugsfda/
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone

from ..models import Citation, Item
from ..httputil import HTTPJSONError, get_json
from .base import Connector

API_URL = "https://api.fda.gov/drug/drugsfda.json"


def _parse_date(text):
    if not text or len(str(text)) != 8:
        return None
    try:
        return datetime.strptime(str(text), "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _display_name(app: dict) -> str:
    of = app.get("openfda", {}) or {}
    brands = of.get("brand_name") or []
    generics = of.get("generic_name") or []
    products = app.get("products") or []
    prod_brand = products[0].get("brand_name") if products else ""
    name = (brands[0] if brands else "") or prod_brand or (generics[0] if generics else "") \
        or app.get("application_number", "") or "FDA drug"
    # FDA brand names are often ALL CAPS; title-case those for display.
    return name.title() if name.isupper() else name


def _appl_url(application_number: str) -> str:
    # Link to the openFDA record the data actually came from — it always resolves
    # to this exact application. FDA's classic Drugs@FDA (accessdata) page can be
    # rerouted to a generic hub by link-preview tools and gateways, so we cite the
    # primary API record instead (as the recalls connector does).
    appno = (application_number or "").strip()
    if appno:
        return ('https://api.fda.gov/drug/drugsfda.json?search=application_number:'
                f'%22{urllib.parse.quote(appno)}%22')
    return "https://api.fda.gov/drug/drugsfda.json"


def application_items(app: dict, cutoff=None, include_supplements: bool = True,
                      topic: str = "fda_approvals") -> list[Item]:
    """Emit an Item per approved submission of one Drugs@FDA application."""
    appno = app.get("application_number", "")
    sponsor = (app.get("sponsor_name", "") or "").strip()
    name = _display_name(app)
    url = _appl_url(appno)
    products = app.get("products") or []
    form = ""
    if products:
        p = products[0]
        parts = [p.get("dosage_form", ""), p.get("route", "")]
        form = " ".join(x for x in parts if x).strip().lower()

    out: list[Item] = []
    for sub in app.get("submissions", []) or []:
        if sub.get("submission_status") != "AP":
            continue
        stype = (sub.get("submission_type") or "").upper()
        if stype == "SUPPL" and not include_supplements:
            continue
        date = _parse_date(sub.get("submission_status_date"))
        if date is None or (cutoff and date < cutoff):
            continue

        is_orig = stype != "SUPPL"
        kind = "FDA approval" if is_orig else "FDA supplemental approval"
        priority = "Priority review" if (sub.get("review_priority") or "").upper() == "PRIORITY" else ""
        sponsor_disp = sponsor.title() if sponsor.isupper() else sponsor

        summary = f"{sponsor_disp or 'The sponsor'} received {'FDA approval' if is_orig else 'a supplemental FDA approval'} for {name}"
        if form:
            summary += f" ({form})"
        summary += "."

        out.append(Item(
            title=f"{name} — {kind}",
            link=url,
            summary=summary,
            source="openFDA (Drug Approvals)",
            topic=topic,
            published=date,
            guid=f"{appno}:{stype}{sub.get('submission_number', '')}:{sub.get('submission_status_date', '')}",
            citations=[Citation(label=f"Drugs@FDA {appno}", url=url, kind="fda")],
            tag=" · ".join(x for x in ("New approval" if is_orig else "Supplement",
                                       priority, sponsor_disp) if x),
            meta={"application_number": appno, "sponsor": sponsor,
                  "submission_type": stype, "priority": priority,
                  "track": {"Type": "New approval" if is_orig else "Supplement"}},
            age_exempt=True,
        ))
    return out


def parse_approvals(payload: dict, cutoff=None, include_supplements: bool = True,
                    topic: str = "fda_approvals") -> list[Item]:
    items: list[Item] = []
    for app in payload.get("results", []) or []:
        items.extend(application_items(app, cutoff=cutoff,
                                       include_supplements=include_supplements, topic=topic))
    return items


class OpenFDAApprovalsConnector(Connector):
    name = "openFDA (Drug Approvals)"
    topic = "fda_approvals"

    def __init__(self, cfg: dict, watchlist: dict) -> None:
        super().__init__(cfg, watchlist)
        self.recent_days = int(cfg.get("recent_days", 90) or 0)
        self.max_per_query = int(cfg.get("max_per_query", 20) or 20)
        self.max_total = int(cfg.get("max_total", 40) or 40)
        self.include_supplements = bool(cfg.get("include_supplements", True))

    def _entity_exprs(self) -> list[str]:
        wl = self.watchlist
        exprs: list[str] = []
        for s in wl.get("sponsors", []):
            if s.strip():
                exprs.append(f'sponsor_name:"{s.strip()}"')
        for value in list(wl.get("interventions", [])) + list(wl.get("terms", [])):
            v = value.strip()
            if v:
                exprs.append(f'(openfda.brand_name:"{v}"+OR+openfda.generic_name:"{v}")')
        # No entities but a window set → "all recent approvals".
        if not exprs and self.recent_days:
            exprs = [""]
        return exprs

    def available(self) -> tuple[bool, str]:
        if not self._entity_exprs():
            return False, "no watch list and no recency window set"
        return True, f"{len(self._entity_exprs())} quer(ies), last {self.recent_days} days"

    def _raw_query(self, expr: str) -> str:
        terms = []
        if expr:
            terms.append(expr)
        terms.append('submissions.submission_status:"AP"')
        if self.recent_days:
            start = (datetime.now(timezone.utc) - timedelta(days=self.recent_days)).strftime("%Y%m%d")
            end = datetime.now(timezone.utc).strftime("%Y%m%d")
            terms.append(f"submissions.submission_status_date:[{start}+TO+{end}]")
        search = "+AND+".join(terms)
        enc = urllib.parse.quote(search, safe='+:[]"()')
        # No sort: sorting on a nested field is unreliable; we sort client-side.
        return f"search={enc}&limit={self.max_per_query}"

    def fetch(self) -> list[Item]:
        exprs = self._entity_exprs()
        if not exprs:
            return []
        cutoff = None
        if self.recent_days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.recent_days)
        by_id: dict[str, Item] = {}
        for expr in exprs:
            try:
                payload = get_json(API_URL, raw_query=self._raw_query(expr),
                                   timeout=30, not_found_ok=True)
            except HTTPJSONError as exc:
                raise HTTPJSONError(f"{expr or 'recent'}: {exc}") from exc
            for item in parse_approvals(payload, cutoff=cutoff,
                                        include_supplements=self.include_supplements,
                                        topic=self.topic):
                by_id.setdefault(item.guid, item)
            if len(by_id) >= self.max_total:
                break
        items = list(by_id.values())
        items.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
                   reverse=True)
        return items[: self.max_total]
