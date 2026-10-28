"""Model Context Protocol (MCP) server — expose OpenBioNews as tools for an AI.

This inverts the usual relationship: the OpenBioNews core has no LLM and invents
nothing, but *any* MCP-speaking assistant (Claude Desktop, Claude Code, …) can
call these tools to pull **primary-source** biomedical records — ClinicalTrials.gov,
openFDA recalls / approvals / shortages / adverse events (FAERS) / labeling, the
Federal Register, PubMed, and SEC EDGAR — each returned with the exact URL it traces
to. The assistant gets grounded, citable facts, not our prose.

The tool *logic* here is pure standard library, so it imports and tests without
the optional ``mcp`` dependency. Only :func:`serve` pulls in ``mcp`` (lazily), so
``pip install openbionews`` stays dependency-free; MCP users install the extra:

    pip install "openbionews[mcp]"
    openbionews mcp            # speaks MCP over stdio

Every tool returns a JSON-serialisable dict carrying provenance:
    {"source", "endpoint", "retrieved_at", "as_of", "count", "results": [...]}
or, on a reachable-but-failed upstream call, {..., "error": str, "results": []},
or, on a successful-but-empty search, {..., "status": "no_current_results",
"query_used", "results": []} — a trustworthy negative the model can cite.

Records are **lean by default** (pass ``verbose=True`` for the raw payload): one
``source`` object instead of three repeated links, plus a ``facts`` block that
surfaces the structured numbers each connector already extracted — enrollment,
dates, endpoints, reaction counts, filing form — so a downstream model can cite
them rather than invent them. Nothing is summarised or fabricated.
"""

from __future__ import annotations

import math
import os
import re
from datetime import datetime, timezone
from typing import Literal

from . import __version__
from .connectors.clinicaltrials import ClinicalTrialsConnector
from .connectors.edgar import EdgarConnector, resolve_cik
from .connectors.openfda import OpenFDAConnector
from .connectors.federalregister import FederalRegisterConnector
from .connectors.openfda_approvals import OpenFDAApprovalsConnector
from .connectors.openfda_events import OpenFDAEventsConnector
from .connectors.openfda_labels import OpenFDALabelsConnector
from .connectors.openfda_shortages import OpenFDAShortagesConnector
from .connectors.pubmed import PubMedConnector
from .httputil import HTTPJSONError
from .models import Item

SERVER_NAME = "openbionews"

# Valid ``rank_by`` modes — a Literal so the MCP tool schema advertises the enum and
# the server rejects an unknown value (e.g. a typo, or "impact") instead of silently
# falling back. "semantic" needs the optional [ml] extra (falls back to "relevance").
RankBy = Literal["recency", "relevance", "semantic", "salience"]
# Valid ``watchlist_digest(sources=…)`` keys, advertised as an enum for the same reason.
DigestSource = Literal["trials", "recalls", "approvals", "shortages", "adverse_events",
                       "labeling", "federal_register", "pubmed", "sec"]

# Upstream page-size ceilings (ClinicalTrials.gov pageSize and openFDA limit are both
# capped at 1000); a larger request is rejected and would fail the whole call.
_MAX_FETCH = 1000
_MAX_LIMIT = 100

# The reproducible endpoint each source traces back to (surfaced for provenance).
_ENDPOINTS = {
    "ClinicalTrials.gov": "https://clinicaltrials.gov/api/v2/studies",
    "openFDA (Drug Recalls)": "https://api.fda.gov/drug/enforcement.json",
    "openFDA (Drug Approvals)": "https://api.fda.gov/drug/drugsfda.json",
    "openFDA (Drug Shortages)": "https://api.fda.gov/drug/shortages.json",
    "openFDA (FAERS)": "https://api.fda.gov/drug/event.json",
    "openFDA (Drug Labeling)": "https://api.fda.gov/drug/label.json",
    "Federal Register": "https://www.federalregister.gov/api/v1/documents.json",
    "PubMed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
    "SEC EDGAR": "https://efts.sec.gov/LATEST/search-index",
}


# --------------------------------------------------------------------------- #
# Serialisation + a shared runner
# --------------------------------------------------------------------------- #
def _now() -> str:
    """When this process fetched the data (RFC-3339, UTC)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _facts(item: Item) -> dict:
    """The structured values a connector already extracted, as a clean block.

    One rule: promote every non-empty ``meta`` field except the internal
    ``track`` key. Nothing is computed or inferred here — these are the exact
    numbers (enrollment, counts, dates, form, …) the upstream record carried,
    so a downstream model can cite them instead of inventing them.
    """
    out = {}
    for key, value in (item.meta or {}).items():
        if key == "track" or value in (None, "", [], {}):
            continue
        out[key] = value
    return out


def _norm_text(text) -> str:
    """Lowercase, with every run of non-alphanumerics collapsed to one space, so
    "GLP-1"/"glp 1" and "base-editing"/"base editing" compare equal."""
    return " " + re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip() + " "


def _term_regex(term):
    """A word-boundary pattern for one query term over ``_norm_text`` output.

    The term must start at a word boundary (so "ALS" never matches inside "trials" or
    "also"). A term whose last token is short (an acronym such as "ALS", "AI", the "1"
    of "GLP-1") must also END at a boundary, allowing a plural "s"; a longer final
    word may run on, so "statin" still matches "statins".
    """
    needle = _norm_text(term).strip()
    if not needle:
        return None
    tail = r"s?(?= )" if len(needle.split(" ")[-1]) <= 3 else ""
    return re.compile(" " + re.escape(needle) + tail)


def _match(item: Item, facts: dict, query_terms) -> dict:
    """Which query terms actually appear, and where — a cheap relevance signal.

    Upstream keyword search can leak loosely-matched records (a different drug,
    a third-party filer). Reporting the terms that genuinely hit, and the field
    they hit, lets a caller down-weight or drop the strays. ``terms: []`` means
    nothing matched the record's own text — treat as a likely stray.
    """
    hay = {
        "title": _norm_text(item.title or ""),
        "summary": _norm_text(item.summary or ""),
        "facts": _norm_text(" ".join(str(v) for v in facts.values())),
    }
    matched, where = [], []
    for term in query_terms or []:
        pattern = _term_regex(term)
        if pattern is None:
            continue
        hits = [field for field, text in hay.items() if pattern.search(text)]
        if hits:
            matched.append(term)
            where.extend(h for h in hits if h not in where)
    return {"terms": matched, "where": where}


# Deterministic relevance scoring (classical ML/IR — no LLM, no new deps). The score
# orders records that already exist and cite themselves; it invents nothing.
# Pivotal weighting for importance: Phase 3 (registrational — the landmark trial) ranks
# above Phase 4 (post-marketing). Validated to bring landmark-trial recall to parity with
# a web agent; the earlier PHASE4 > PHASE3 order buried pivotal outcomes trials.
_PHASE_WEIGHT = {"PHASE3": 1.0, "PHASE4": 0.8, "PHASE2": 0.6, "PHASE1": 0.35,
                 "EARLY_PHASE1": 0.25, "NA": 0.3, "": 0.3}
_TRIAL_WEIGHTS = {"match": 0.40, "phase": 0.20, "recency": 0.15,
                  "enrollment": 0.15, "results_posted": 0.05, "status": 0.05}


def _trial_relevance(item: Item, query_terms) -> dict:
    """A transparent 0–1 relevance score for a trial and its component breakdown.

    Blends lexical query match with signal features that proxy how substantial and
    current a study is — phase, recency of the last update, enrollment size, whether
    results are posted, and whether it was stopped. Deterministic and reproducible.
    """
    match, recency = _match_recency(item, query_terms)

    phases = item.meta.get("phases") or []
    phase = max((_PHASE_WEIGHT.get(str(p).upper(), 0.3) for p in phases), default=0.3)

    enr = item.meta.get("enrollment")
    enrollment = 0.0
    if isinstance(enr, (int, float)) and enr > 0:
        enrollment = min(1.0, math.log10(enr + 1) / math.log10(5001))  # ~0..1 up to 5k

    results_posted = 1.0 if item.meta.get("has_results") else 0.0

    status = (item.meta.get("status") or "").upper()
    stopped = any(s in status for s in ("TERMINATED", "WITHDRAWN", "SUSPENDED"))
    status_score = 0.3 if stopped else 1.0

    components = {"match": round(match, 3), "phase": round(phase, 3),
                  "recency": round(recency, 3), "enrollment": round(enrollment, 3),
                  "results_posted": results_posted, "status": round(status_score, 3)}
    score = sum(components[k] * w for k, w in _TRIAL_WEIGHTS.items())
    return {"score": round(score, 4), "components": components}


# "What matters" rather than "what matches". Validated against landmark-trial recall
# (6 drugs, 18 verified landmark trials): an EQUAL blend of structural maturity signals
# matched a web agent's top-7 (~0.9 recall), while the earlier recency-weighted blend
# scored ~0.39 — recency let recent Phase-4 studies crowd out pivotal Phase-3 / outcomes
# trials. So recency is dropped from salience, and so is query match (the candidate pool
# is already query-filtered; importance alone decides order within it). Fine-tuned
# coefficients did not beat the equal blend in cross-validation, so we ship the simple
# blend. NB: we intentionally do NOT use a raw reference/"publication footprint" count —
# ct.gov's referencesModule mixes BACKGROUND (the investigators' bibliography) with
# RESULT/DERIVED (papers reporting this trial), and counting all of it overweights small
# investigator-initiated trials; a footprint signal, if ever added, must use RESULT+DERIVED only.
_SALIENCE_FEATURES = ("enrollment", "phase", "results_posted", "maturity")
_STATUS_MATURITY = {
    "COMPLETED": 1.0, "ACTIVE_NOT_RECRUITING": 0.85, "ENROLLING_BY_INVITATION": 0.6,
    "RECRUITING": 0.6, "NOT_YET_RECRUITING": 0.3,
    "SUSPENDED": 0.3, "TERMINATED": 0.2, "WITHDRAWN": 0.1,
}


def _trial_maturity(item: Item) -> float:
    """How far along the study is — completed/with-results outranks just-recruiting."""
    return _STATUS_MATURITY.get((item.meta.get("status") or "").upper(), 0.5)


def _trial_salience(item: Item, query_terms) -> dict:
    base = _trial_relevance(item, query_terms)["components"]
    base["maturity"] = round(_trial_maturity(item), 3)
    # Report only the signals that actually feed the score, so a caller reading the
    # breakdown isn't misled into thinking recency or keyword match count here.
    comp = {k: base[k] for k in _SALIENCE_FEATURES}
    score = sum(comp.values()) / len(comp)
    return {"score": round(score, 4), "components": comp}


def _item_to_dict(item: Item, *, verbose: bool = False,
                  query_terms=None, since_iso: str | None = None) -> dict:
    """A primary-source record as lean JSON (or the full payload if ``verbose``)."""
    cites = [{"label": c.label, "url": c.url, "kind": c.kind} for c in item.citations]
    primary = cites[0] if cites else {"label": item.source, "url": item.link, "kind": ""}
    date_iso = item.published.date().isoformat() if item.published else None
    facts = _facts(item)
    source = {"id": item.guid, "name": item.source,
              "url": primary["url"], "kind": primary["kind"]}
    if len(cites) > 1:                        # e.g. a PubMed DOI beside the PMID link
        source["also"] = cites[1:]
    rec = {
        "title": item.title,
        "date": date_iso,
        "status": item.tag,
        "facts": facts,
        "summary": item.summary,
        "source": source,
    }
    if query_terms:
        rec["match"] = _match(item, facts, query_terms)
    if since_iso is not None:
        rec["is_new"] = bool(date_iso and date_iso >= since_iso)
    if verbose:
        rec["id"] = item.guid
        rec["citations"] = cites
        rec["citation_url"] = primary["url"]
        rec["meta"] = {k: v for k, v in (item.meta or {}).items() if k != "track"}
    return rec


def _search(connector_cls, *, cfg=None, query_terms=None, since_iso=None, verbose=False,
            page=None, require_match=False, score_fn=None, salience_fn=None,
            rank_by=None, **watch) -> dict:
    """Run one connector over a watch list built from ``watch`` and serialise.

    ``watch`` keys are the watch-list fields the connectors understand:
    ``terms``, ``sponsors``, ``conditions``, ``interventions`` (each a list).
    Upstream failures are returned as data, never raised, so a flaky agency
    doesn't take the whole call down. Every block carries provenance
    (``endpoint``, ``retrieved_at``, ``as_of``); an empty-but-successful search
    returns an explicit ``no_current_results`` status with the query used.
    """
    watchlist = {k: v for k, v in watch.items() if v}
    base = {"source": connector_cls.name,
            "endpoint": _ENDPOINTS.get(connector_cls.name, ""),
            "retrieved_at": _now(), "as_of": _today()}
    if since_iso is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(since_iso)):
        # A malformed date would silently filter everything out and read as a
        # trustworthy "no results" — reject it instead.
        return {**base, "error": f"since must be YYYY-MM-DD (got {since_iso!r})",
                "count": 0, "results": []}
    try:
        items = connector_cls(cfg or {}, watchlist).fetch()
    except HTTPJSONError as exc:
        return {**base, "error": str(exc), "count": 0, "results": []}
    if since_iso is not None:
        items = [i for i in items
                 if not i.published or i.published.date().isoformat() >= since_iso]
    if require_match and query_terms:
        # Drop records where no query term appears in the title, summary or facts —
        # the loose-keyword strays (a different drug) that upstream search leaks in.
        items = [i for i in items if _match(i, _facts(i), query_terms)["terms"]]
    # Score the whole candidate pool, then (optionally) rank by it — before paging, so
    # the top page is the most relevant, not the most relevant within a recency page.
    scores, ranked_by, note = {}, None, None
    # Salience is query-independent ("which matter most"), so it runs even with no
    # query — e.g. the most severe of all recent recalls. The other modes need terms.
    wants_scores = bool(query_terms) or rank_by == "salience"
    if wants_scores and (score_fn is not None or salience_fn is not None):
        query_terms = query_terms or []
        if rank_by == "salience":
            if salience_fn is not None:
                scores = {id(i): salience_fn(i, query_terms) for i in items}
                ranked_by = "salience"
            else:                         # this source has no salience signal
                note = "salience ranking isn't available for this source; used relevance"
        elif rank_by == "semantic":
            scores = _semantic_pool_scores(items, query_terms)
            if scores is None:            # optional [ml] extra not installed
                scores = {}
                note = ("semantic ranking needs the optional [ml] extra "
                        "(pip install \"openbionews[ml]\"); used lexical relevance")
            else:
                ranked_by = "semantic"
        if not scores and score_fn is not None:   # lexical: default, or a fallback above
            scores = {id(i): score_fn(i, query_terms) for i in items}
            # Any fall-back from a ranking mode (semantic w/o [ml], salience on an
            # unsupported source) lands on lexical relevance — report it as such.
            ranked_by = "relevance" if rank_by in _RANK_MODES else "recency"
        if ranked_by in _RANK_MODES:
            items.sort(key=lambda i: scores[id(i)]["score"], reverse=True)
    if not items:
        # The search genuinely matched nothing — a citable negative. (Decided BEFORE
        # paging: an offset past the end is not "no results", see below.)
        return {**base, "status": "no_current_results", "count": 0,
                "query_used": watchlist, "results": []}
    truncated = False
    page_note = None
    if page is not None:
        offset, count = page
        offset = max(0, int(offset))                    # sanitize agent-supplied paging
        count = max(1, min(int(count), _MAX_LIMIT))
        truncated = len(items) > offset + count
        if offset >= len(items):
            page_note = f"offset {offset} is past the last result ({len(items)} available)"
        items = items[offset:offset + count]
    results = []
    for i in items:
        rec = _item_to_dict(i, verbose=verbose, query_terms=query_terms, since_iso=since_iso)
        if id(i) in scores:
            rec["relevance_score"] = scores[id(i)]["score"]
            if verbose:
                rec["relevance_components"] = scores[id(i)]["components"]
        results.append(rec)
    out = {**base, "count": len(results), "results": results}
    if page_note:
        out["page_note"] = page_note
    if ranked_by:
        out["ranked_by"] = ranked_by
    if note:
        out["ranking_note"] = note
    if page is not None:
        out["truncated"] = truncated
    return out


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


def _norm_phase(p) -> str:
    """Normalise a phase ("3", "Phase 3", "PHASE3") to a ct.gov token ("PHASE3")."""
    s = str(p).strip().upper().replace(" ", "_")
    if "EARLY" in s:
        return "EARLY_PHASE1"
    if s in ("NA", "N/A"):
        return "NA"
    for d in "1234":
        if d in s:
            return "PHASE" + d
    return s


def _phase_list(phase) -> list[str]:
    """Expand a phase argument into ct.gov tokens. Accepts a list or a combined string:
    "2/3", "Phase 2/Phase 3" and "2,3" all mean Phase 2 OR Phase 3 (a phase-2/3 trial
    carries both tokens), rather than silently keeping only the first digit."""
    out: list[str] = []
    for raw in _as_list(phase) or []:
        for part in re.split(r"[/,|]|\band\b", str(raw), flags=re.I):
            if part.strip():
                tok = _norm_phase(part)
                if tok not in out:
                    out.append(tok)
    return out


# Generic relevance for non-trial sources: lexical match + recency, plus an optional
# per-source "signal" (recall severity, approval priority, shortage currency). Same
# classical, deterministic, invent-nothing basis as the trial scorer.
_GENERIC_WEIGHTS = {"match": 0.6, "recency": 0.4}
_SIGNAL_WEIGHTS = {"match": 0.5, "recency": 0.3, "signal": 0.2}
# Ordered most-specific first: "CLASS I" is a substring of "CLASS III"/"CLASS II".
_RECALL_CLASS = {"CLASS III": 0.3, "CLASS II": 0.6, "CLASS I": 1.0}


def _match_recency(item: Item, query_terms) -> tuple[float, float]:
    facts = _facts(item)
    terms = [t for t in (query_terms or []) if str(t).strip()]
    hit = _match(item, facts, terms)
    frac = (len(hit["terms"]) / len(terms)) if terms else 0.0
    match = min(1.0, frac + (0.25 if "title" in hit["where"] else 0.0))
    recency = 0.0
    if item.published:
        age = (datetime.now(timezone.utc) - item.published).days
        recency = max(0.0, 1.0 - age / 365.0)
    return round(match, 3), round(recency, 3)


def _generic_relevance(item: Item, query_terms, signal_fn=None) -> dict:
    match, recency = _match_recency(item, query_terms)
    comp = {"match": match, "recency": recency}
    weights = _GENERIC_WEIGHTS
    if signal_fn is not None:
        comp["signal"] = round(signal_fn(item), 3)
        weights = _SIGNAL_WEIGHTS
    return {"score": round(sum(comp[k] * w for k, w in weights.items()), 4),
            "components": comp}


def _recall_signal(item: Item) -> float:        # Class I most serious
    c = (item.meta.get("classification") or "").upper()
    return next((v for k, v in _RECALL_CLASS.items() if k in c), 0.5)


def _approval_signal(item: Item) -> float:      # priority review is more notable
    return 1.0 if "PRIORITY" in (item.meta.get("priority") or "").upper() else 0.5


def _shortage_signal(item: Item) -> float:      # a current shortage outranks a resolved one
    return 1.0 if "CURRENT" in (item.meta.get("status") or "").upper() else 0.4


def _generic_salience(item: Item, query_terms, signal_fn=None) -> dict:
    """Signal-first reweighting of the generic score for "what matters" ordering."""
    comp = _generic_relevance(item, query_terms, signal_fn)["components"]
    weights = ({"signal": 0.6, "recency": 0.3, "match": 0.1} if "signal" in comp
               else {"recency": 0.6, "match": 0.4})
    return {"score": round(sum(comp[k] * w for k, w in weights.items()), 4), "components": comp}


def _scorer(signal_fn=None):
    """Bind a per-source signal into a relevance score_fn(item, query_terms)."""
    return lambda item, q: _generic_relevance(item, q, signal_fn)


def _salience_scorer(signal_fn=None):
    """Bind a per-source signal into a salience score_fn(item, query_terms)."""
    return lambda item, q: _generic_salience(item, q, signal_fn)


_RANK_MODES = ("relevance", "semantic", "salience")


def _rank_cap(rank_by, span: int) -> tuple[bool, str, int]:
    """(ranking?, canonical rank_by, candidate cap). Ranking modes pull a wider pool so
    a page isn't scored against its recency-local neighbours only; "salience" pulls the
    widest, so a landmark (but older) record can still compete."""
    rb = str(rank_by).lower()
    rb = rb if rb in _RANK_MODES else "recency"
    span = max(0, int(span))
    cap = span + 1
    if rb == "salience":
        cap = max(span + 1, 500)   # widest, so every landmark trial for a drug can enter
    elif rb in ("relevance", "semantic"):
        cap = max(span + 1, 100)
    return rb != "recency", rb, min(cap, _MAX_FETCH)   # never above the upstream page max


def _doc_text(item: Item) -> str:
    """The text a semantic ranker reads for a record: title, summary, and facts."""
    facts = _facts(item)
    parts = [item.title or "", item.summary or ""] + [str(v) for v in facts.values()]
    return " ".join(p for p in parts if p)


def _semantic_pool_scores(items, query_terms):
    """Semantic (LSA) scores over the whole candidate pool, blended with recency.

    Returns {id(item): {score, components}}, or None when the optional ``[ml]`` extra
    isn't installed — the caller then falls back to lexical relevance.
    """
    try:
        from .mlrank import semantic_scores
    except ImportError:
        return None
    if not items:
        return {}
    sims = semantic_scores(" ".join(str(t) for t in query_terms), [_doc_text(i) for i in items])
    out = {}
    for item, sim in zip(items, sims):
        _, recency = _match_recency(item, query_terms)
        out[id(item)] = {"score": round(0.75 * sim + 0.25 * recency, 4),
                         "components": {"semantic": round(sim, 3), "recency": recency}}
    return out


# --------------------------------------------------------------------------- #
# Tool implementations (plain functions — no MCP dependency needed to call them)
# --------------------------------------------------------------------------- #
def search_clinical_trials(query: str, status: str | None = None, phase: str | None = None,
                           recent_days: int = 90, limit: int = 20, offset: int = 0,
                           since: str | None = None, require_match: bool = True,
                           rank_by: RankBy = "recency", verbose: bool = False) -> dict:
    """Search ClinicalTrials.gov for recent studies matching ``query``.

    ``status`` e.g. "RECRUITING" / "COMPLETED" / "TERMINATED"; ``phase`` e.g. "3".
    ``since`` (YYYY-MM-DD) keeps only records on/after that date and flags each
    ``is_new``; ``offset`` pages through results and sets a ``truncated`` flag.
    ``require_match`` (default true) drops studies where the query term appears in no
    field — the loose-keyword strays the registry's search leaks in; set it false to
    see everything and filter yourself via each result's ``match``.

    Every result carries a deterministic score (0–1) and ``rank_by`` picks the intent:
    "recency" (default — what's new, most recently updated first); "relevance" (lexical
    query match, over a wider recent pool); "semantic" (LSA similarity — needs the
    optional ``[ml]`` extra, falls back to "relevance" with a ``ranking_note``); or
    "salience" (**what matters** — an equal blend of enrollment, phase, results-posted
    and maturity, with recency and keyword match dropped, so a large mature pivotal trial
    outranks a small recent one; it searches a wide window and pool so a landmark older
    study can surface). The component breakdown
    is in each result's ``relevance_components`` under ``verbose``, and ``ranked_by``
    reports the mode used. Each lean result also carries a ``facts`` block (enrollment,
    start/primary-completion dates, primary endpoints, phase, sponsor) cited to its NCT
    record.
    """
    _, rb, cap = _rank_cap(rank_by, offset + limit)
    # Salience is "what matters", not "what's recent" — widen the window so a landmark
    # study updated outside the default recency window can still enter the pool.
    rd = max(recent_days, 1825) if rb == "salience" else recent_days
    cfg = {"recent_days": rd, "max_total": cap, "max_per_query": cap}
    if rb == "salience":
        # Let the connector add an enrollment-sorted candidate pass so a landmark
        # (large, older-updated) trial can enter the pool before scoring.
        cfg["salience"] = True
    if status:
        cfg["statuses"] = _as_list(status)
    if phase:
        # Filtered server-side (see the connector) so the limit applies to matching
        # studies, not to an all-phase page that is then truncated.
        cfg["phases"] = _phase_list(phase)
    return _search(ClinicalTrialsConnector, terms=_as_list(query), cfg=cfg,
                   query_terms=_as_list(query), since_iso=since, verbose=verbose,
                   require_match=require_match, page=(offset, limit),
                   score_fn=_trial_relevance, salience_fn=_trial_salience, rank_by=rb)


def search_fda_recalls(query: str = "", firm: str | None = None,
                       classification: str | None = None,
                       recent_days: int = 90, limit: int = 20, offset: int = 0,
                       since: str | None = None, rank_by: RankBy = "recency",
                       verbose: bool = False) -> dict:
    """Search openFDA drug recalls. ``query`` matches the product; ``firm`` the
    recalling company; ``classification`` e.g. "Class I". Empty query + no firm
    returns all recent recalls. ``since``/``offset``/``rank_by`` and a per-result
    ``relevance_score`` work as on search_clinical_trials — here the signal weights
    recall severity (Class I highest), so ``rank_by="salience"`` (no query needed)
    surfaces the most serious recalls first. Each result cites its openFDA record."""
    _, rb, cap = _rank_cap(rank_by, offset + limit)
    cfg = {"recent_days": recent_days, "max_total": cap, "max_per_query": cap}
    if classification:
        cfg["classifications"] = _as_list(classification)
    return _search(OpenFDAConnector, interventions=_as_list(query),
                   sponsors=_as_list(firm), cfg=cfg,
                   query_terms=_as_list(query) or _as_list(firm),
                   since_iso=since, verbose=verbose, page=(offset, limit),
                   score_fn=_scorer(_recall_signal),
                   salience_fn=_salience_scorer(_recall_signal), rank_by=rb)


def search_fda_approvals(query: str = "", company: str | None = None,
                         include_supplements: bool = True,
                         recent_days: int = 90, limit: int = 20, offset: int = 0,
                         since: str | None = None, rank_by: RankBy = "recency",
                         verbose: bool = False) -> dict:
    """Search Drugs@FDA approvals (openFDA). ``query`` matches brand/generic name;
    ``company`` the sponsor. ``since``/``offset``/``rank_by`` and a ``relevance_score``
    per result work as on search_clinical_trials (the signal weights priority review).
    Each result cites its Drugs@FDA record."""
    _, rb, cap = _rank_cap(rank_by, offset + limit)
    cfg = {"recent_days": recent_days, "max_total": cap, "max_per_query": cap,
           "include_supplements": include_supplements}
    return _search(OpenFDAApprovalsConnector, interventions=_as_list(query),
                   sponsors=_as_list(company), cfg=cfg,
                   query_terms=_as_list(query) or _as_list(company),
                   since_iso=since, verbose=verbose, page=(offset, limit),
                   score_fn=_scorer(_approval_signal),
                   salience_fn=_salience_scorer(_approval_signal), rank_by=rb)


def search_fda_shortages(query: str = "", company: str | None = None,
                         status: str = "Current", limit: int = 20, offset: int = 0,
                         rank_by: RankBy = "recency", verbose: bool = False) -> dict:
    """Search FDA drug shortages (openFDA). ``query`` matches brand/generic name;
    ``status`` e.g. "Current" / "Resolved". A product not in shortage returns an
    explicit ``no_current_results`` status (a citable negative), not a bare 0.
    ``rank_by`` and a per-result ``relevance_score`` work as on search_clinical_trials
    (a current shortage outranks a resolved one). Each result cites its openFDA record."""
    _, rb, cap = _rank_cap(rank_by, offset + limit)
    cfg = {"max_total": cap, "max_per_query": cap, "statuses": _as_list(status) or []}
    return _search(OpenFDAShortagesConnector, interventions=_as_list(query),
                   sponsors=_as_list(company), cfg=cfg,
                   query_terms=_as_list(query) or _as_list(company),
                   verbose=verbose, page=(offset, limit),
                   score_fn=_scorer(_shortage_signal),
                   salience_fn=_salience_scorer(_shortage_signal), rank_by=rb)


def search_fda_adverse_events(query: str, top_reactions: int = 8, limit: int = 20,
                              verbose: bool = False) -> dict:
    """Summarise FAERS adverse-event reports (openFDA) for one or more drugs. For each
    drug in ``query`` returns its most-reported reactions with counts (in ``facts``),
    cited to the reproducible openFDA query. Counts are spontaneous reports, NOT
    incidence rates, and do not establish causation."""
    cfg = {"top_reactions": top_reactions, "max_total": limit}
    return _search(OpenFDAEventsConnector, interventions=_as_list(query), cfg=cfg,
                   query_terms=_as_list(query), verbose=verbose)


def search_fda_labeling(query: str, limit: int = 10, verbose: bool = False) -> dict:
    """Look up the current FDA drug label (openFDA SPL) for one or more drugs. For each
    drug in ``query`` returns its approved indications and whether it carries a boxed
    warning (in ``facts``), cited to the reproducible openFDA label query."""
    cfg = {"max_total": limit}
    return _search(OpenFDALabelsConnector, interventions=_as_list(query), cfg=cfg,
                   query_terms=_as_list(query), verbose=verbose)


def search_pubmed(query: str, recent_days: int = 365, limit: int = 10, offset: int = 0,
                  since: str | None = None, require_match: bool = True,
                  rank_by: RankBy = "recency", verbose: bool = False) -> dict:
    """Search PubMed (NCBI E-utilities) for recent biomedical literature matching
    ``query``. ``since``/``offset``/``require_match``/``rank_by`` and a per-result
    ``relevance_score`` work as on search_clinical_trials (``require_match`` defaults
    true to drop loose-keyword strays). Each result cites its PubMed record (and DOI
    when present)."""
    _, rb, cap = _rank_cap(rank_by, offset + limit)
    cfg = {"recent_days": recent_days, "max_total": cap, "max_per_query": cap}
    return _search(PubMedConnector, terms=_as_list(query), cfg=cfg,
                   query_terms=_as_list(query), since_iso=since, verbose=verbose,
                   require_match=require_match, page=(offset, limit),
                   score_fn=_scorer(), rank_by=rb)


def search_federal_register(query: str = "", recent_days: int = 30, limit: int = 20,
                            offset: int = 0, all_agencies: bool = False,
                            since: str | None = None, rank_by: RankBy = "recency",
                            verbose: bool = False) -> dict:
    """Search Federal Register documents (FDA guidances, advisory-committee notices,
    proposed/final rules). ``query`` is the search text; by default results are
    limited to the FDA — set ``all_agencies`` true to search every agency.
    ``since``/``offset``/``rank_by`` and a per-result ``relevance_score`` work as on
    search_clinical_trials. Each result cites its Federal Register document."""
    _, rb, cap = _rank_cap(rank_by, offset + limit)
    cfg = {"recent_days": recent_days, "max_total": cap, "max_per_query": cap,
           "agencies": [] if all_agencies else ["food-and-drug-administration"]}
    return _search(FederalRegisterConnector, terms=_as_list(query), cfg=cfg,
                   query_terms=_as_list(query), since_iso=since, verbose=verbose,
                   page=(offset, limit), score_fn=_scorer(), rank_by=rb)


def search_sec_filings(query: str = "", company: str | None = None,
                       form: str | None = None, recent_days: int = 90, limit: int = 20,
                       offset: int = 0, own_filer_only: bool = False,
                       since: str | None = None, rank_by: RankBy = "recency",
                       verbose: bool = False) -> dict:
    """Search SEC EDGAR filings. Two modes, picked by what you pass:

    - **Entity mode** — give ``company`` (a name, ticker, or raw CIK; ``query`` is
      then optional). The subject is resolved to its CIK and only that registrant's
      *own* filings are returned, so third-party filings that merely mention it (a
      fund's 13F, an NPORT-P) are excluded. ``query``, if also given, filters those
      filings by text in the form/description. ``own_filer_only=true`` applies the
      same entity scoping when you only have ``query`` (it is resolved as the entity).
    - **Full-text mode** — give only ``query`` (and not ``own_filer_only``): a
      document full-text search that matches any filing mentioning the terms.

    ``form`` e.g. "8-K"; ``since``/``offset``/``rank_by`` and a per-result
    ``relevance_score`` work as on search_clinical_trials. Each result cites the
    filing document. Set the OPENBIONEWS_EDGAR_UA env var to your email (SEC requests
    a contact).

    Note: results are the filing *pointer* (form, filer, date, accession) — figures
    are not extracted from the document body, so read the cited filing for numbers
    rather than inferring them."""
    base = {"source": EdgarConnector.name,
            "endpoint": _ENDPOINTS.get(EdgarConnector.name, ""),
            "retrieved_at": _now(), "as_of": _today()}
    if not query and not company:
        return {**base, "error": "provide 'query' (full-text) and/or 'company' (entity)",
                "count": 0, "results": []}
    _, rb, cap = _rank_cap(rank_by, offset + limit)
    cfg = _edgar_cfg({"recent_days": recent_days, "max_total": cap, "max_per_query": cap})
    if form:
        cfg["forms"] = _as_list(form)
    qterms = _as_list(query) or _as_list(company)

    # Entity mode: scope to the subject's own filings by resolving it to a CIK.
    subject = company or (query if own_filer_only else None)
    if subject:
        cik = resolve_cik(subject, cfg.get("user_agent"))
        if not cik:
            return {**base, "status": "entity_not_found", "entity": subject,
                    "count": 0, "results": []}
        cfg["ciks"] = [cik]
        # A query distinct from the entity name refines within that filer's filings.
        refine = _as_list(query) if (query and query != subject) else None
        res = _search(EdgarConnector, cfg=cfg, terms=refine, query_terms=qterms,
                      since_iso=since, verbose=verbose, page=(offset, limit),
                      score_fn=_scorer(), rank_by=rb)
        res["resolved_cik"] = cik
        res["own_filer_only"] = True
        return res

    # Full-text mode.
    return _search(EdgarConnector, terms=_as_list(query), cfg=cfg, query_terms=qterms,
                   since_iso=since, verbose=verbose, page=(offset, limit),
                   score_fn=_scorer(), rank_by=rb)


# connector + the watch-list field a free-text term maps to, for the combined digest.
# The short key is what a caller passes to ``sources=`` to ask for only that agency.
_DIGEST_SPEC = [
    ("trials", ClinicalTrialsConnector, "terms"),
    ("recalls", OpenFDAConnector, "interventions"),
    ("approvals", OpenFDAApprovalsConnector, "interventions"),
    ("shortages", OpenFDAShortagesConnector, "interventions"),
    ("adverse_events", OpenFDAEventsConnector, "interventions"),
    ("labeling", OpenFDALabelsConnector, "interventions"),
    ("federal_register", FederalRegisterConnector, "terms"),
    ("pubmed", PubMedConnector, "terms"),
    ("sec", EdgarConnector, "terms"),
]
_DIGEST_KEYS = [key for key, _, _ in _DIGEST_SPEC]
# Per-source relevance scorer for the digest (None = leave recency order, e.g. the
# per-drug FAERS/labeling lookups where ranking isn't meaningful).
_DIGEST_SCORERS = {
    "trials": _trial_relevance,
    "recalls": _scorer(_recall_signal),
    "approvals": _scorer(_approval_signal),
    "shortages": _scorer(_shortage_signal),
    "federal_register": _scorer(),
    "pubmed": _scorer(),
    "sec": _scorer(),
}
# Salience ("what matters") scorers for the digest; sources without one fall back to
# relevance within that block.
_DIGEST_SALIENCE = {
    "trials": _trial_salience,
    "recalls": _salience_scorer(_recall_signal),
    "approvals": _salience_scorer(_approval_signal),
    "shortages": _salience_scorer(_shortage_signal),
}


def watchlist_digest(terms: list[str] | str, recent_days: int = 90,
                     limit_per_source: int = 15, sources: list[DigestSource] | None = None,
                     since: str | None = None, rank_by: RankBy = "recency",
                     verbose: bool = False) -> dict:
    """Pull recent primary-source records for ``terms`` across every source at once
    (the cross-agency watchlist). ``terms`` is a list of companies, drugs or topics.
    ``sources`` restricts to a subset by key (e.g. ["sec", "trials"]) so an SEC-only
    intent doesn't spend tokens on PubMed and FAERS; valid keys are: trials, recalls,
    approvals, shortages, adverse_events, labeling, federal_register, pubmed, sec (an
    unknown key is an error, not silently skipped). ``since`` (YYYY-MM-DD) keeps only
    records on/after that date and flags each ``is_new``. ``rank_by`` ("recency"
    default, "relevance", "semantic" or "salience") orders the records within each
    source block and adds a ``relevance_score``; "salience" also widens the trials
    pool so landmark studies can surface. Returns one grouped block per source, each
    record cited, each capped at ``limit_per_source``."""
    terms = _as_list(terms) or []
    requested = _as_list(sources)
    unknown = sorted(set(requested or []) - set(_DIGEST_KEYS))
    if unknown:
        return {"terms": terms, "error": f"unknown source key(s): {', '.join(unknown)}; "
                f"valid: {', '.join(_DIGEST_KEYS)}", "total": 0, "sources": [],
                "generated_at": _now()}
    want = set(requested or _DIGEST_KEYS)
    limit = max(1, min(int(limit_per_source), _MAX_LIMIT))
    _, rb, cap = _rank_cap(rank_by, limit)
    cap = min(cap, 100)          # a ranking pool per source, kept modest across 9 sources
    base = {"recent_days": recent_days, "max_total": cap, "max_per_query": cap}
    blocks = []
    for key, connector_cls, field in _DIGEST_SPEC:
        if key not in want:
            continue
        cfg = _edgar_cfg(base) if connector_cls is EdgarConnector else dict(base)
        if key == "trials" and rb == "salience":
            # Same as search_clinical_trials: an enrollment-sorted pass over a wide
            # window, so a landmark trial can enter before the block is ranked.
            cfg["salience"] = True
            cfg["recent_days"] = max(recent_days, 1825)
        block = _search(connector_cls, cfg=cfg, query_terms=terms, since_iso=since,
                        verbose=verbose, score_fn=_DIGEST_SCORERS.get(key),
                        salience_fn=_DIGEST_SALIENCE.get(key), rank_by=rb,
                        page=(0, limit), **{field: terms})
        block["key"] = key
        blocks.append(block)
    total = sum(s.get("count", 0) for s in blocks)
    return {"terms": terms, "sources_requested": sorted(want), "total": total,
            "sources": blocks, "generated_at": _now()}


TOOLS = [
    search_clinical_trials, search_fda_recalls, search_fda_approvals,
    search_fda_shortages, search_fda_adverse_events, search_fda_labeling,
    search_federal_register, search_pubmed, search_sec_filings, watchlist_digest,
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
            import sys

            hint = (
                "The MCP server needs the optional 'mcp' package. Install it with:\n"
                "    pip install \"openbionews[mcp]\""
            )
            if sys.version_info < (3, 10):
                hint += (
                    f"\n\nNote: the 'mcp' SDK requires Python 3.10+, but this is "
                    f"Python {sys.version_info.major}.{sys.version_info.minor}. "
                    "On 3.9 the [mcp] extra installs nothing (that is why 'mcp' is "
                    "missing here). Run OpenBioNews on Python 3.10+ for the MCP server, "
                    "e.g.  pipx install \"openbionews[mcp]\" --python python3.12"
                )
            raise ImportError(hint) from exc
    try:                                      # clients display serverInfo.version
        server = Server(SERVER_NAME, version=__version__)
    except TypeError:                         # older SDK without a version kwarg
        server = Server(SERVER_NAME)
    # Every tool is a read-only, side-effect-free lookup. Advertising that via MCP
    # tool annotations lets agent frameworks cache and parallelise calls safely.
    annotations = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}
    for fn in TOOLS:
        try:
            server.tool(annotations=annotations)(fn)
        except TypeError:          # older SDK without annotation support
            server.tool()(fn)
    return server


def serve() -> int:
    """Run the MCP server over stdio (how Claude Desktop / Code launch it)."""
    build_server().run()
    return 0
