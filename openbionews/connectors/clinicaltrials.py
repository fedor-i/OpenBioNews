"""ClinicalTrials.gov connector (API v2).

Reads the official trial registry and turns recent study developments into
Items, each tracing back to its NCT record. No API key required.

Docs: https://clinicaltrials.gov/data-api/api
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .. import textutil
from ..httputil import HTTPJSONError, get_json
from ..models import Citation, Item
from .base import Connector

API_URL = "https://clinicaltrials.gov/api/v2/studies"

# The specific leaf fields we need — keeps the payload small.
FIELDS = [
    "NCTId", "BriefTitle", "OverallStatus", "LastUpdatePostDate",
    "LeadSponsorName", "Condition", "InterventionName", "BriefSummary",
    "Phase", "StudyType", "HasResults",
]


def _dig(obj: dict, *path: str):
    """Walk a nested dict/list structure, returning None if any step is missing."""
    cur = obj
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
        if cur is None:
            return None
    return cur


def _pretty_status(status: str) -> str:
    return status.replace("_", " ").title() if status else ""


def _pretty_phase(phases) -> str:
    if not phases:
        return ""
    labels = []
    for p in phases:
        p = (p or "").upper()
        if p == "NA":
            continue
        labels.append(p.replace("PHASE", "Phase ").replace("EARLY_Phase 1", "Early Phase 1"))
    return "/".join(labels)


def _parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def study_to_item(study: dict, topic: str = "clinical_trials") -> Item | None:
    """Map one ClinicalTrials.gov v2 study object into an Item. None if unusable."""
    ps = study.get("protocolSection", study)
    nct = _dig(ps, "identificationModule", "nctId")
    title = _dig(ps, "identificationModule", "briefTitle")
    if not nct or not title:
        return None

    status = _dig(ps, "statusModule", "overallStatus") or ""
    date_text = _dig(ps, "statusModule", "lastUpdatePostDateStruct", "date")
    sponsor = _dig(ps, "sponsorCollaboratorsModule", "leadSponsor", "name") or ""
    conditions = _dig(ps, "conditionsModule", "conditions") or []
    interventions = [
        i.get("name", "") for i in (_dig(ps, "armsInterventionsModule", "interventions") or [])
        if isinstance(i, dict) and i.get("name")
    ]
    phases = _dig(ps, "designModule", "phases") or []
    summary = _dig(ps, "descriptionModule", "briefSummary") or ""
    has_results = bool(study.get("hasResults"))

    link = f"https://clinicaltrials.gov/study/{nct}"
    tag_parts = [x for x in (_pretty_status(status), _pretty_phase(phases), sponsor) if x]

    # Fields worth watching for change between runs (see history.py).
    track = {"Status": _pretty_status(status) or status}
    if has_results:
        track["Results"] = "Posted"

    return Item(
        title=title.strip(),
        link=link,
        summary=textutil.strip_html(summary),
        source="ClinicalTrials.gov",
        topic=topic,
        published=_parse_date(date_text),
        guid=nct,
        citations=[Citation(label=f"ClinicalTrials.gov {nct}", url=link, kind="registry")],
        tag=" · ".join(tag_parts),
        meta={
            "nct_id": nct,
            "status": status,
            "phases": phases,
            "sponsor": sponsor,
            "conditions": conditions,
            "interventions": interventions,
            "has_results": has_results,
            "track": track,
        },
        age_exempt=True,
    )


def parse_studies(payload: dict, topic: str = "clinical_trials") -> list[Item]:
    """Parse a v2 /studies response body into Items."""
    items: list[Item] = []
    for study in payload.get("studies", []) or []:
        item = study_to_item(study, topic=topic)
        if item is not None:
            items.append(item)
    return items


class ClinicalTrialsConnector(Connector):
    name = "ClinicalTrials.gov"
    topic = "clinical_trials"

    def __init__(self, cfg: dict, watchlist: dict) -> None:
        super().__init__(cfg, watchlist)
        self.recent_days = int(cfg.get("recent_days", 30) or 0)
        self.max_per_query = int(cfg.get("max_per_query", 20) or 20)
        self.max_total = int(cfg.get("max_total", 60) or 60)
        self.statuses = [s for s in cfg.get("statuses", []) if s]

    def _queries(self) -> list[tuple[str, str]]:
        """Turn the watch list into (api_field, value) query pairs."""
        wl = self.watchlist
        pairs: list[tuple[str, str]] = []
        for value in wl.get("sponsors", []):
            pairs.append(("query.spons", value))
        for value in wl.get("conditions", []):
            pairs.append(("query.cond", value))
        for value in wl.get("interventions", []):
            pairs.append(("query.intr", value))
        for value in wl.get("terms", []):
            pairs.append(("query.term", value))
        return [(f, v) for f, v in pairs if v and v.strip()]

    def available(self) -> tuple[bool, str]:
        if not self._queries():
            return False, "no watch list set (add sponsors/conditions/drugs/terms)"
        return True, f"{len(self._queries())} watch quer(ies), last {self.recent_days} days"

    def fetch(self) -> list[Item]:
        queries = self._queries()
        if not queries:
            return []

        cutoff = None
        if self.recent_days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.recent_days)

        by_nct: dict[str, Item] = {}
        for field, value in queries:
            params = {
                field: value,
                "sort": "LastUpdatePostDate:desc",
                "pageSize": self.max_per_query,
                "fields": ",".join(FIELDS),
            }
            if self.statuses:
                params["filter.overallStatus"] = ",".join(self.statuses)
            try:
                payload = get_json(API_URL, params=params, timeout=30)
            except HTTPJSONError as exc:
                raise HTTPJSONError(f"{field}={value}: {exc}") from exc

            for item in parse_studies(payload, topic=self.topic):
                if cutoff and item.published is not None and item.published < cutoff:
                    continue
                nct = item.meta.get("nct_id", item.guid)
                if nct not in by_nct:
                    by_nct[nct] = item
            if len(by_nct) >= self.max_total:
                break

        items = list(by_nct.values())
        items.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
                   reverse=True)
        return items[: self.max_total]
