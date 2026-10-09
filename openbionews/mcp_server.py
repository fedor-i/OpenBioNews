"""Model Context Protocol (MCP) server — expose OpenBioNews as tools for an AI.

This inverts the usual relationship: the OpenBioNews core has no LLM and invents
nothing, but *any* MCP-speaking assistant (Claude Desktop, Claude Code, …) can
call these tools to pull **primary-source** biomedical records — ClinicalTrials.gov,
FDA recalls / approvals / shortages, and SEC EDGAR — each returned with the exact
URL it traces to. The assistant gets grounded, citable facts, not our prose.

The tool *logic* here is pure standard library, so it imports and tests without
the optional ``mcp`` dependency. Only :func:`serve` pulls in ``mcp`` (lazily), so
``pip install openbionews`` stays dependency-free; MCP users install the extra:

    pip install "openbionews[mcp]"
    openbionews mcp            # speaks MCP over stdio

Every tool returns a JSON-serialisable dict:
    {"source": str, "count": int, "results": [ {record…}, … ]}
or, on a reachable-but-failed upstream call, {"source", "error", "results": []}.
Each record carries its citation URL — nothing is summarised or invented.
"""

from __future__ import annotations

import os
from datetime import datetime

from .connectors.clinicaltrials import ClinicalTrialsConnector
from .connectors.edgar import EdgarConnector
from .connectors.openfda import OpenFDAConnector
from .connectors.federalregister import FederalRegisterConnector
from .connectors.openfda_approvals import OpenFDAApprovalsConnector
from .connectors.openfda_events import OpenFDAEventsConnector
from .connectors.openfda_shortages import OpenFDAShortagesConnector
from .httputil import HTTPJSONError
from .models import Item

SERVER_NAME = "openbionews"


# --------------------------------------------------------------------------- #
# Serialisation + a shared runner
# --------------------------------------------------------------------------- #
def _item_to_dict(item: Item) -> dict:
    """A primary-source record as plain JSON, with its citation(s)."""
    meta = {k: v for k, v in (item.meta or {}).items() if k != "track"}
    cites = [{"label": c.label, "url": c.url, "kind": c.kind} for c in item.citations]
    return {
        "title": item.title,
        "source": item.source,
        "url": item.link,
        "published": item.published.date().isoformat() if item.published else None,
        "status_line": item.tag,
        "summary": item.summary,
        "citation_url": cites[0]["url"] if cites else item.link,
        "citations": cites,
        "id": item.guid,
        "meta": meta,
    }


def _search(connector_cls, *, cfg=None, phase=None, **watch) -> dict:
    """Run one connector over a watch list built from ``watch`` and serialise.

    ``watch`` keys are the watch-list fields the connectors understand:
    ``terms``, ``sponsors``, ``conditions``, ``interventions`` (each a list).
    Upstream failures are returned as data, never raised, so a flaky agency
    doesn't take the whole call down.
    """
    watchlist = {k: v for k, v in watch.items() if v}
    try:
        items = connector_cls(cfg or {}, watchlist).fetch()
    except HTTPJSONError as exc:
        return {"source": connector_cls.name, "error": str(exc), "count": 0, "results": []}
    if phase:
        want = str(phase).upper().replace("PHASE", "").strip()
        items = [i for i in items
                 if any(want in str(p).upper() for p in (i.meta.get("phases") or []))]
    return {"source": connector_cls.name, "count": len(items),
            "results": [_item_to_dict(i) for i in items]}


def _edgar_cfg(base: dict) -> dict:
    """SEC asks for a descriptive User-Agent with a contact; honour an env override."""
    ua = os.environ.get("OPENBIONEWS_EDGAR_UA")
    if ua:
        base = {**base, "user_agent": ua}
    return base


def _as_list(value):
    if value is None or value == "":
        return None
    return value if isinstance(value, list) else [value]


# --------------------------------------------------------------------------- #
# Tool implementations (plain functions — no MCP dependency needed to call them)
# --------------------------------------------------------------------------- #
def search_clinical_trials(query: str, status: str | None = None, phase: str | None = None,
                           recent_days: int = 90, limit: int = 20) -> dict:
    """Search ClinicalTrials.gov for recent studies matching ``query``.

    ``status`` e.g. "RECRUITING" / "COMPLETED" / "TERMINATED"; ``phase`` e.g. "3".
    Each result cites its NCT record.
    """
    cfg = {"recent_days": recent_days, "max_total": limit, "max_per_query": limit}
    if status:
        cfg["statuses"] = _as_list(status)
    return _search(ClinicalTrialsConnector, terms=_as_list(query), cfg=cfg, phase=phase)


def search_fda_recalls(query: str = "", firm: str | None = None,
                       classification: str | None = None,
                       recent_days: int = 90, limit: int = 20) -> dict:
    """Search openFDA drug recalls. ``query`` matches the product; ``firm`` the
    recalling company; ``classification`` e.g. "Class I". Empty query + no firm
    returns all recent recalls. Each result cites its openFDA record."""
    cfg = {"recent_days": recent_days, "max_total": limit, "max_per_query": limit}
    if classification:
        cfg["classifications"] = _as_list(classification)
    return _search(OpenFDAConnector, interventions=_as_list(query),
                   sponsors=_as_list(firm), cfg=cfg)


def search_fda_approvals(query: str = "", company: str | None = None,
                         include_supplements: bool = True,
                         recent_days: int = 90, limit: int = 20) -> dict:
    """Search Drugs@FDA approvals (openFDA). ``query`` matches brand/generic name;
    ``company`` the sponsor. Each result cites its Drugs@FDA record."""
    cfg = {"recent_days": recent_days, "max_total": limit, "max_per_query": limit,
           "include_supplements": include_supplements}
    return _search(OpenFDAApprovalsConnector, interventions=_as_list(query),
                   sponsors=_as_list(company), cfg=cfg)


def search_fda_shortages(query: str = "", company: str | None = None,
                         status: str = "Current", limit: int = 20) -> dict:
    """Search FDA drug shortages (openFDA). ``query`` matches brand/generic name;
    ``status`` e.g. "Current" / "Resolved". Each result cites its openFDA record."""
    cfg = {"max_total": limit, "max_per_query": limit, "statuses": _as_list(status) or []}
    return _search(OpenFDAShortagesConnector, interventions=_as_list(query),
                   sponsors=_as_list(company), cfg=cfg)


def search_fda_adverse_events(query: str, top_reactions: int = 8, limit: int = 20) -> dict:
    """Summarise FAERS adverse-event reports (openFDA) for one or more drugs. For each
    drug in ``query`` returns its most-reported reactions with counts, cited to the
    reproducible openFDA query. Counts are spontaneous reports, NOT incidence rates,
    and do not establish causation."""
    cfg = {"top_reactions": top_reactions, "max_total": limit}
    return _search(OpenFDAEventsConnector, interventions=_as_list(query), cfg=cfg)


def search_federal_register(query: str = "", recent_days: int = 30, limit: int = 20,
                            all_agencies: bool = False) -> dict:
    """Search Federal Register documents (FDA guidances, advisory-committee notices,
    proposed/final rules). ``query`` is the search text; by default results are
    limited to the FDA — set ``all_agencies`` true to search every agency. Each
    result cites its Federal Register document."""
    cfg = {"recent_days": recent_days, "max_total": limit, "max_per_query": limit,
           "agencies": [] if all_agencies else ["food-and-drug-administration"]}
    return _search(FederalRegisterConnector, terms=_as_list(query), cfg=cfg)


def search_sec_filings(query: str, company: str | None = None, form: str | None = None,
                       recent_days: int = 90, limit: int = 20) -> dict:
    """Full-text search SEC EDGAR filings. ``query`` is the search text; ``company``
    narrows by filer; ``form`` e.g. "8-K". Each result cites the filing document.
    Set the OPENBIONEWS_EDGAR_UA env var to your email (SEC requests a contact)."""
    cfg = {"recent_days": recent_days, "max_total": limit, "max_per_query": limit}
    if form:
        cfg["forms"] = _as_list(form)
    return _search(EdgarConnector, terms=_as_list(query),
                   sponsors=_as_list(company), cfg=_edgar_cfg(cfg))


# connector + the watch-list field a free-text term maps to, for the combined digest
_DIGEST_SPEC = [
    (ClinicalTrialsConnector, "terms"),
    (OpenFDAConnector, "interventions"),
    (OpenFDAApprovalsConnector, "interventions"),
    (OpenFDAShortagesConnector, "interventions"),
    (OpenFDAEventsConnector, "interventions"),
    (FederalRegisterConnector, "terms"),
    (EdgarConnector, "terms"),
]


def watchlist_digest(terms, recent_days: int = 90, limit_per_source: int = 15) -> dict:
    """Pull recent primary-source records for ``terms`` across all five agencies at
    once (the cross-agency watchlist). ``terms`` is a list of companies, drugs or
    topics. Returns one grouped block per source, each record cited."""
    terms = _as_list(terms) or []
    base = {"recent_days": recent_days, "max_total": limit_per_source,
            "max_per_query": limit_per_source}
    sources = []
    for connector_cls, field in _DIGEST_SPEC:
        cfg = _edgar_cfg(base) if connector_cls is EdgarConnector else dict(base)
        sources.append(_search(connector_cls, cfg=cfg, **{field: terms}))
    total = sum(s.get("count", 0) for s in sources)
    return {"terms": terms, "total": total, "sources": sources,
            "generated_at": datetime.utcnow().isoformat() + "Z"}


TOOLS = [
    search_clinical_trials, search_fda_recalls, search_fda_approvals,
    search_fda_shortages, search_fda_adverse_events, search_federal_register,
    search_sec_filings, watchlist_digest,
]


# --------------------------------------------------------------------------- #
# MCP wiring (imports the optional ``mcp`` package lazily)
# --------------------------------------------------------------------------- #
def build_server():
    """Create an MCP server with every tool registered. Needs ``mcp`` installed.

    Supports both the current SDK (``mcp`` >= 2, ``MCPServer``) and the older
    1.x line (``FastMCP``); the tool decorator and stdio ``run()`` are the same.
    """
    Server = None
    try:                                      # mcp >= 2
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:
        try:                                  # mcp 1.x
            from mcp.server.fastmcp import FastMCP as Server
        except ImportError as exc:  # pragma: no cover - exercised via the CLI message
            raise ImportError(
                "The MCP server needs the optional 'mcp' package. Install it with:\n"
                "    pip install \"openbionews[mcp]\""
            ) from exc
    server = Server(SERVER_NAME)
    for fn in TOOLS:
        server.tool()(fn)
    return server


def serve() -> int:
    """Run the MCP server over stdio (how Claude Desktop / Code launch it)."""
    build_server().run()
    return 0
