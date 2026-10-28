"""Tests for the MCP server's tool logic (openbionews.mcp_server).

The tool functions are plain standard-library code — the optional ``mcp`` package
is only needed to actually speak the protocol (serve()), not to compute results —
so these run in the stdlib-only CI. Upstream HTTP is mocked per connector, so no
network is touched.

Runs with pytest or directly (``python tests/test_mcp.py``).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openbionews import mcp_server
from openbionews.connectors import (
    clinicaltrials, edgar, federalregister, openfda, openfda_approvals,
    openfda_events, openfda_labels, openfda_shortages, pubmed,
)
from openbionews.httputil import HTTPJSONError
from openbionews.models import Citation, Item


def _ct_study(nct, title, date, phase="PHASE3", enrollment=120,
              status="RECRUITING", has_results=False):
    return {"hasResults": has_results, "protocolSection": {
        "identificationModule": {"nctId": nct, "briefTitle": title},
        "statusModule": {"overallStatus": status,
                         "lastUpdatePostDateStruct": {"date": date},
                         "startDateStruct": {"date": "2026-01-15"},
                         "primaryCompletionDateStruct": {"date": "2027-06-30"}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Beam"}},
        "conditionsModule": {"conditions": ["Sickle Cell"]},
        "descriptionModule": {"briefSummary": "A CRISPR gene editing therapy."},
        "designModule": {"phases": [phase], "enrollmentInfo": {"count": enrollment}},
        "outcomesModule": {"primaryOutcomes": [{"measure": "Change in HbF at 24 weeks"}]}}}


# ---- canned upstream payloads (same JSON shapes the real APIs return) ------- #
CT = {"studies": [_ct_study("NCT0001", "CRISPR base editing study", "2026-10-01")]}
CT_MANY = {"studies": [
    _ct_study("NCT_A", "Study A", "2026-10-10"),
    _ct_study("NCT_B", "Study B", "2026-10-05"),
    _ct_study("NCT_C", "Study C", "2026-08-01"),
]}
CT_PHASES = {"studies": [
    _ct_study("NCT_P1", "Early study", "2026-10-01", phase="PHASE1"),
    _ct_study("NCT_P3", "Pivotal study", "2026-10-01", phase="PHASE3"),
]}
RECALLS = {"results": [{
    "recall_number": "D-1111-2026", "product_description": "Injectable 10 mg/mL",
    "recalling_firm": "Insilico", "reason_for_recall": "Contamination risk.",
    "classification": "Class I", "status": "Ongoing", "report_date": "20261001",
    "openfda": {"brand_name": ["Injectacin"]}}]}
APPROVALS = {"results": [{
    "application_number": "BLA761000", "sponsor_name": "BEAM THERAPEUTICS",
    "openfda": {"brand_name": ["EDITACEL"], "generic_name": ["examplecel"]},
    "submissions": [{"submission_status": "AP", "submission_type": "ORIG",
                     "submission_status_date": "20261001", "submission_number": "1",
                     "submission_class_code": "EFFICACY"}]}]}
SHORTAGES = {"results": [{
    "proprietary_name": ["Injectacin"], "generic_name": ["examplecin"],
    "company_name": "Insilico", "status": "Current",
    "reason_for_shortage": "Demand increase.", "update_date": "2026-10-01",
    "openfda": {}}]}
EDGAR = {"hits": {"hits": [{"_id": "0001-26-000001:filing.htm", "_source": {
    "ciks": ["0001628280"], "display_names": ["BEAM THERAPEUTICS INC (RXRX)"],
    "root_form": "8-K", "file_date": "2026-10-01",
    "file_description": "Material agreement on a collaboration."}}]}}
# SEC's registrant directory (name/ticker -> CIK), as company_tickers.json returns it.
TICKERS = {
    "0": {"cik_str": 1607678, "ticker": "VKTX", "title": "Viking Therapeutics, Inc."},
    "1": {"cik_str": 1628280, "ticker": "BEAM", "title": "Beam Therapeutics Inc."},
}
# A subject's OWN filings, as data.sec.gov/submissions/CIK##########.json returns them.
VIKING_SUBMISSIONS = {"cik": "1607678", "name": "Viking Therapeutics, Inc.",
    "filings": {"recent": {
        "form": ["8-K", "10-Q"],
        "filingDate": ["2026-10-10", "2026-09-30"],
        "accessionNumber": ["0001607678-26-000045", "0001607678-26-000040"],
        "primaryDocument": ["vktx-8k.htm", "vktx-10q.htm"],
        "primaryDocDescription": ["Current report", "Quarterly report"]}}}
EVENTS = {"results": [{"term": "NAUSEA", "count": 42}, {"term": "HEADACHE", "count": 17}]}
LABELS = {"results": [{
    "openfda": {"brand_name": ["Examplor"], "generic_name": ["examplemab"],
                "manufacturer_name": ["Beam"]},
    "indications_and_usage": ["Indicated for sickle cell disease."],
    "boxed_warning": ["WARNING: SERIOUS INFECTIONS"]}]}
FEDREG = {"results": [{
    "title": "Guidance for Industry; Availability", "type": "Notice",
    "html_url": "https://www.federalregister.gov/documents/2026/10/01/2026-9/g",
    "publication_date": "2026-10-01", "document_number": "2026-9",
    "agencies": [{"name": "Food and Drug Administration"}]}]}
PM_SEARCH = {"esearchresult": {"idlist": ["40000001"]}}
PM_SUMMARY = {"result": {"uids": ["40000001"], "40000001": {
    "title": "Base editing in sickle cell disease.", "source": "N Engl J Med",
    "pubdate": "2026 Sep 15", "authors": [{"name": "Smith J"}],
    "articleids": [{"idtype": "doi", "value": "10.1056/ex"}]}}}
def _pubmed_fake(url, *a, **k):
    return PM_SUMMARY if "esummary" in url else PM_SEARCH


class _patch:
    """Temporarily replace a connector module's get_json with a canned result."""

    def __init__(self, module, payload=None, raise_exc=None):
        self.module, self.payload, self.raise_exc = module, payload, raise_exc

    def __enter__(self):
        self._orig = self.module.get_json

        def fake(*a, **k):
            if self.raise_exc:
                raise self.raise_exc
            # A callable payload lets a connector that makes several calls (e.g.
            # PubMed: esearch then esummary) return a different shape per URL.
            if callable(self.payload):
                return self.payload(*a, **k)
            return self.payload
        self.module.get_json = fake
        return self

    def __exit__(self, *exc):
        self.module.get_json = self._orig


# --- A. lean serialisation: one source object, no triplicate citation -------- #
def test_item_to_dict_is_lean_by_default():
    item = Item(title="T", link="https://x/1", summary="s", source="Src",
                published=datetime(2026, 10, 1, tzinfo=timezone.utc), guid="g",
                citations=[Citation(label="L", url="https://x/1", kind="registry")],
                tag="Recruiting", meta={"status": "RECRUITING", "track": {"Status": "x"}})
    d = mcp_server._item_to_dict(item)
    # The link lives in exactly one place now — the source object.
    assert d["source"] == {"id": "g", "name": "Src", "url": "https://x/1", "kind": "registry"}
    assert "url" not in d and "citation_url" not in d and "citations" not in d
    assert d["date"] == "2026-10-01" and d["status"] == "Recruiting"
    # facts promote structured meta, drop the internal track key.
    assert d["facts"] == {"status": "RECRUITING"}


def test_item_to_dict_verbose_restores_full_payload():
    item = Item(title="T", link="https://x/1", summary="s", source="Src",
                published=datetime(2026, 10, 1, tzinfo=timezone.utc), guid="g",
                citations=[Citation(label="L", url="https://x/1", kind="registry")],
                tag="Recruiting", meta={"status": "RECRUITING", "track": {"x": 1}})
    d = mcp_server._item_to_dict(item, verbose=True)
    assert d["citation_url"] == "https://x/1" and d["citations"][0]["label"] == "L"
    assert d["id"] == "g" and "track" not in d["meta"]


def test_second_citation_rides_in_source_also():
    item = Item(title="T", link="https://pm/1", source="PubMed", guid="g",
                citations=[Citation(label="PMID", url="https://pm/1", kind="literature"),
                           Citation(label="DOI", url="https://doi.org/x", kind="doi")])
    d = mcp_server._item_to_dict(item)
    assert d["source"]["url"] == "https://pm/1"
    assert d["source"]["also"][0]["url"] == "https://doi.org/x"


# --- B. the numbers travel in facts, so a model needn't invent them ---------- #
def test_trials_facts_carry_the_hard_numbers():
    with _patch(clinicaltrials, CT):
        out = mcp_server.search_clinical_trials("crispr", limit=5)
    assert out["source"] == "ClinicalTrials.gov" and out["count"] == 1
    f = out["results"][0]["facts"]
    assert f["enrollment"] == 120
    assert f["start_date"] == "2026-01-15" and f["primary_completion_date"] == "2027-06-30"
    assert f["primary_endpoints"] == ["Change in HbF at 24 weeks"]
    assert out["results"][0]["source"]["url"].startswith("https://clinicaltrials.gov")


def test_ct_fields_request_the_leaves_the_parser_reads():
    # ct.gov's `fields` param prunes everything else, so a leaf the parser reads but
    # FIELDS omits comes back empty in real queries (silent, since mocks ignore fields).
    # Guard the salience/facts inputs specifically.
    fields = set(clinicaltrials.FIELDS)
    for required in ("EnrollmentCount", "StartDate", "PrimaryCompletionDate",
                     "PrimaryOutcomeMeasure", "HasResults", "Phase", "OverallStatus"):
        assert required in fields, f"ct.gov FIELDS missing {required} (parser reads it)"


def test_adverse_event_counts_are_structured():
    with _patch(openfda_events, EVENTS):
        out = mcp_server.search_fda_adverse_events("semaglutide")
    r = out["results"][0]
    assert r["facts"]["total"] >= 1 and r["facts"]["reactions"]
    assert "not incidence rates" in r["summary"]


# --- phase filter still works, now addressing the lean source id ------------- #
def test_phase_filter_is_pushed_server_side():
    # The phase filter must ride in the ct.gov request (so the recency/page limit
    # applies to matching studies), not be a post-fetch pass over a truncated page.
    captured = {}
    orig = clinicaltrials.get_json
    clinicaltrials.get_json = lambda url, *a, **k: (captured.update(k.get("params") or {}) or CT_PHASES)
    try:
        mcp_server.search_clinical_trials("x", phase="3", require_match=False)
    finally:
        clinicaltrials.get_json = orig
    assert "filter.advanced" in captured, "phase was not pushed into the ct.gov query"
    assert captured["filter.advanced"] == "AREA[Phase](PHASE3)"


def test_phase_normalisation():
    assert mcp_server._norm_phase("3") == "PHASE3"
    assert mcp_server._norm_phase("Phase 2") == "PHASE2"
    assert mcp_server._norm_phase("PHASE4") == "PHASE4"
    assert mcp_server._norm_phase("early") == "EARLY_PHASE1"


CT_LEAK = {"studies": [
    _ct_study("NCT_TZP", "Tirzepatide for obesity", "2026-10-05"),
    _ct_study("NCT_SEC", "Secukinumab for psoriasis", "2026-10-06"),
]}


# A substantial phase-3 study (older) vs. a tiny phase-1 pilot (newer): recency and
# relevance disagree, so ranking order is a real signal, not an artifact of dates.
CT_RANK = {"studies": [
    _ct_study("NCT_HI", "Aspirin cardiovascular outcomes", "2026-09-01",
              phase="PHASE3", enrollment=2000),
    _ct_study("NCT_LO", "Aspirin pilot study", "2026-10-18",
              phase="PHASE1", enrollment=20),
]}


def test_relevance_score_present_and_bounded():
    with _patch(clinicaltrials, CT_RANK):
        out = mcp_server.search_clinical_trials("aspirin")
    assert all(0.0 <= r["relevance_score"] <= 1.0 for r in out["results"])
    assert len(out["results"]) == 2


def test_rank_by_relevance_reorders_vs_recency():
    with _patch(clinicaltrials, CT_RANK):
        by_recency = mcp_server.search_clinical_trials("aspirin")              # default
        by_relevance = mcp_server.search_clinical_trials("aspirin", rank_by="relevance")
    # recency puts the newer phase-1 pilot first; relevance puts the phase-3 study first
    assert by_recency["results"][0]["source"]["id"] == "NCT_LO"
    assert by_relevance["results"][0]["source"]["id"] == "NCT_HI"
    assert by_relevance["results"][0]["relevance_score"] > \
        by_relevance["results"][1]["relevance_score"]


# A large mature Phase-3 trial updated outside the 90-day window vs. a small recent
# Phase-1 one: recency/relevance surface the small recent; salience surfaces the big one.
CT_SALIENCE = {"studies": [
    _ct_study("NCT_BIG", "Semaglutide cardiovascular outcomes", "2026-05-01",
              phase="PHASE3", enrollment=1024),
    _ct_study("NCT_SMALL", "Semaglutide pilot dose study", "2026-10-18",
              phase="PHASE1", enrollment=40),
]}


def test_salience_surfaces_large_mature_trial():
    with _patch(clinicaltrials, CT_SALIENCE):
        sal = mcp_server.search_clinical_trials("semaglutide", rank_by="salience")
        recent = mcp_server.search_clinical_trials("semaglutide")   # default recency, 90d
    assert sal["ranked_by"] == "salience"
    assert sal["results"][0]["source"]["id"] == "NCT_BIG"           # size/maturity wins
    # the default 90-day window cuts the older landmark — salience's wide window is what
    # lets it compete (fixes the "never enters the pool" problem)
    assert "NCT_BIG" not in [r["source"]["id"] for r in recent["results"]]
    assert "NCT_BIG" in [r["source"]["id"] for r in sal["results"]]


def test_salience_widens_candidate_pool():
    cap = {}
    orig = clinicaltrials.get_json
    clinicaltrials.get_json = lambda url, *a, **k: (cap.update(k.get("params") or {}) or {"studies": []})
    try:
        mcp_server.search_clinical_trials("x", rank_by="salience", require_match=False)
    finally:
        clinicaltrials.get_json = orig
    assert int(cap.get("pageSize", 0)) >= 250, "salience should pull a wide candidate pool"


# A landmark trial (huge enrollment, last updated years ago) + two small recent ones.
# The recency pass never sees the landmark; the enrollment pass does.
_SELECT = _ct_study("NCT_SELECT", "Semaglutide SELECT cardiovascular outcomes",
                    "2024-08-01", phase="PHASE3", enrollment=17604)
_SMALL_A = _ct_study("NCT_SA", "Semaglutide pilot A", "2026-10-10", phase="PHASE1", enrollment=30)
_SMALL_B = _ct_study("NCT_SB", "Semaglutide pilot B", "2026-10-09", phase="PHASE2", enrollment=60)


def _ct_sort_router(url, *a, **k):
    sort = (k.get("params") or {}).get("sort", "")
    if "EnrollmentCount" in sort:        # the salience enrollment pass sees the landmark
        return {"studies": [_SELECT, _SMALL_A, _SMALL_B]}
    return {"studies": [_SMALL_A, _SMALL_B]}   # recency pass: recent small trials only


def test_salience_reaches_landmark_via_enrollment_pass():
    with _patch(clinicaltrials, _ct_sort_router):
        sal = mcp_server.search_clinical_trials("semaglutide", rank_by="salience", limit=10)
        recent = mcp_server.search_clinical_trials("semaglutide")   # default recency, 90d
    assert sal["ranked_by"] == "salience"
    assert sal["results"][0]["source"]["id"] == "NCT_SELECT"        # 17,604-pt landmark tops
    # the recency window never surfaces it (it enters only via the enrollment pass)
    assert "NCT_SELECT" not in [r["source"]["id"] for r in recent["results"]]


def test_salience_pivotal_outcomes_beats_recent_phase4():
    # The failure the landmark-recall validation caught: a recent Phase-4 label-expansion
    # study crowding out a pivotal, large, completed Phase-3 with results. Salience must
    # rank on maturity/results/enrollment/phase (equal blend, no recency), not freshness.
    pivotal = _ct_study("NCT_PIVOTAL", "Semaglutide SELECT cardiovascular outcomes",
                        "2024-08-01", phase="PHASE3", enrollment=17000,
                        status="COMPLETED", has_results=True)
    recent_p4 = _ct_study("NCT_P4", "Semaglutide label-expansion study", "2026-10-15",
                          phase="PHASE4", enrollment=60, status="RECRUITING")

    def router(url, *a, **k):
        sort = (k.get("params") or {}).get("sort", "")
        return {"studies": [pivotal, recent_p4]} if "EnrollmentCount" in sort \
            else {"studies": [recent_p4]}

    with _patch(clinicaltrials, router):
        sal = mcp_server.search_clinical_trials("semaglutide", rank_by="salience",
                                                limit=10, verbose=True)
    top = sal["results"][0]
    assert top["source"]["id"] == "NCT_PIVOTAL", "recent Phase-4 crowded out the pivotal trial"
    assert "maturity" in top["relevance_components"]          # maturity signal present
    assert top["relevance_score"] > sal["results"][1]["relevance_score"]


def test_salience_phase3_outranks_phase4_when_otherwise_equal():
    # Pivotal weighting: with identical enrollment/results/maturity, the registrational
    # Phase 3 must outrank the post-marketing Phase 4 (the fix that took recall to 1.0).
    p3 = _ct_study("NCT_P3", "Drug pivotal outcomes", "2026-01-01", phase="PHASE3",
                   enrollment=1000, status="COMPLETED", has_results=True)
    p4 = _ct_study("NCT_P4b", "Drug post-marketing", "2026-01-01", phase="PHASE4",
                   enrollment=1000, status="COMPLETED", has_results=True)
    with _patch(clinicaltrials, {"studies": [p4, p3]}):
        out = mcp_server.search_clinical_trials("drug", rank_by="salience", limit=10)
    assert out["results"][0]["source"]["id"] == "NCT_P3"


def test_salience_enrollment_pass_is_best_effort():
    # If the API rejects the enrollment sort, salience must still work off the recency
    # pool, not fail the whole fetch.
    def router(url, *a, **k):
        if "EnrollmentCount" in (k.get("params") or {}).get("sort", ""):
            raise HTTPJSONError("HTTP 400: unsupported sort")
        return {"studies": [_SMALL_A, _SMALL_B]}
    with _patch(clinicaltrials, router):
        out = mcp_server.search_clinical_trials("semaglutide", rank_by="salience")
    assert out["ranked_by"] == "salience" and out["count"] >= 1


def test_unknown_rank_by_coerces_safely_in_direct_call():
    # The MCP boundary rejects unknown rank_by via the Literal enum; a direct Python
    # call coerces to the safe recency default rather than crashing.
    with _patch(clinicaltrials, CT):
        out = mcp_server.search_clinical_trials("crispr", rank_by="impact")
    assert out.get("ranked_by") in (None, "recency")


def test_salience_falls_back_for_unsupported_source():
    with _patch(pubmed, _pubmed_fake):
        out = mcp_server.search_pubmed("base editing", rank_by="salience")
    assert out["ranked_by"] == "relevance" and "salience" in out["ranking_note"]


def test_rank_by_semantic_scores_or_falls_back():
    # Works whether or not the optional [ml] extra is installed: semantic ranking when
    # available, a clean fall back to lexical relevance (with a note) when not.
    with _patch(clinicaltrials, CT_RANK):
        out = mcp_server.search_clinical_trials("aspirin", rank_by="semantic")
    assert all("relevance_score" in r for r in out["results"])
    if "ranking_note" in out:
        # fell back (no [ml]): must report the honest mode, not still claim "semantic"
        assert out["ranked_by"] == "relevance" and "[ml]" in out["ranking_note"]
    else:
        assert out["ranked_by"] == "semantic"      # [ml] present, real semantic ran


def test_relevance_components_in_verbose():
    with _patch(clinicaltrials, CT_RANK):
        out = mcp_server.search_clinical_trials("aspirin", rank_by="relevance", verbose=True)
    comp = out["results"][0]["relevance_components"]
    assert set(comp) >= {"match", "phase", "recency", "enrollment",
                         "results_posted", "status"}


RECALLS_SEV = {"results": [
    {"recall_number": "D-3-2026", "product_description": "Aspirin low dose",
     "recalling_firm": "X", "reason_for_recall": "Label mix-up.",
     "classification": "Class III", "status": "Ongoing", "report_date": "20261019",
     "openfda": {"brand_name": ["Aspirin Low"]}},
    {"recall_number": "D-1-2026", "product_description": "Aspirin extra",
     "recalling_firm": "X", "reason_for_recall": "Contamination.",
     "classification": "Class I", "status": "Ongoing", "report_date": "20260822",
     "openfda": {"brand_name": ["Aspirin Extra"]}},
]}


def test_recall_relevance_weights_severity():
    with _patch(openfda, RECALLS_SEV):
        rel = mcp_server.search_fda_recalls("aspirin", rank_by="relevance")
    # Class I (most serious) outranks the newer Class III despite recency
    assert rel["results"][0]["facts"]["classification"] == "Class I"
    assert all("relevance_score" in r for r in rel["results"])


def test_relevance_score_present_across_sources():
    with _patch(pubmed, _pubmed_fake):
        assert "relevance_score" in mcp_server.search_pubmed("base editing")["results"][0]
    with _patch(openfda_approvals, APPROVALS):
        assert "relevance_score" in mcp_server.search_fda_approvals("editacel")["results"][0]
    with _patch(federalregister, FEDREG):
        assert "relevance_score" in mcp_server.search_federal_register("guidance")["results"][0]


def test_watchlist_rank_by_relevance_scores_blocks():
    with _patch(clinicaltrials, CT), _patch(edgar, EDGAR):
        out = mcp_server.watchlist_digest(["beam"], sources=["trials", "sec"],
                                          rank_by="relevance")
    trials = next(b for b in out["sources"] if b["key"] == "trials")
    assert trials["results"] and all("relevance_score" in r for r in trials["results"])


def test_require_match_drops_keyword_strays():
    # The registry leaks loosely-matched studies; require_match (default) removes
    # the one where the query term appears in no field.
    with _patch(clinicaltrials, CT_LEAK):
        strict = mcp_server.search_clinical_trials("tirzepatide")
        loose = mcp_server.search_clinical_trials("tirzepatide", require_match=False)
    assert [r["source"]["id"] for r in strict["results"]] == ["NCT_TZP"]
    assert len(loose["results"]) == 2        # opt out to see everything + self-filter


# --- per-source smoke tests on the lean shape -------------------------------- #
def test_search_fda_recalls():
    with _patch(openfda, RECALLS):
        out = mcp_server.search_fda_recalls("injectable", classification="Class I")
    r = out["results"][0]
    assert out["count"] == 1 and r["facts"]["classification"] == "Class I"
    assert "fda.gov" in r["source"]["url"]


def test_search_fda_approvals():
    with _patch(openfda_approvals, APPROVALS):
        out = mcp_server.search_fda_approvals("editacel")
    assert out["count"] >= 1
    assert "fda" in out["results"][0]["source"]["url"].lower()


def test_search_fda_shortages():
    with _patch(openfda_shortages, SHORTAGES):
        out = mcp_server.search_fda_shortages("injectacin")
    assert out["count"] == 1 and "shortage" in out["results"][0]["title"].lower()


def test_search_fda_labeling():
    with _patch(openfda_labels, LABELS):
        out = mcp_server.search_fda_labeling("examplemab")
    r = out["results"][0]
    assert out["count"] == 1 and r["facts"]["boxed_warning"] is True
    assert "/drug/label.json" in r["source"]["url"]


def test_search_pubmed():
    with _patch(pubmed, _pubmed_fake):
        out = mcp_server.search_pubmed("base editing")
    r = out["results"][0]
    assert out["count"] == 1 and "pubmed.ncbi.nlm.nih.gov/40000001" in r["source"]["url"]
    assert any("doi.org" in c["url"] for c in r["source"]["also"])


def test_search_federal_register():
    with _patch(federalregister, FEDREG):
        out = mcp_server.search_federal_register("guidance")
    r = out["results"][0]
    assert out["count"] == 1 and "federalregister.gov" in r["source"]["url"]
    assert r["source"]["name"] == "Federal Register"


def _edgar_router(url, *a, **k):
    """Route EDGAR calls by URL: registrant directory, submissions, or full-text."""
    if "company_tickers" in url:
        return TICKERS
    if "data.sec.gov/submissions" in url:
        return VIKING_SUBMISSIONS
    return EDGAR  # efts.sec.gov full-text


def test_search_sec_filings_fulltext_mode():
    with _patch(edgar, EDGAR):
        out = mcp_server.search_sec_filings("collaboration")
    assert out["count"] == 1 and "sec.gov" in out["results"][0]["source"]["url"]


# --- C. relevance signal + SEC own-filer scope ------------------------------- #
def test_match_reports_which_terms_hit_and_where():
    with _patch(clinicaltrials, CT):
        out = mcp_server.search_clinical_trials("crispr", limit=5)
    m = out["results"][0]["match"]
    assert "crispr" in [t.lower() for t in m["terms"]]
    assert "summary" in m["where"] or "title" in m["where"]


def test_sec_company_scopes_to_own_filings_query_optional():
    # company alone (no query) must work, and return only the subject's OWN filings.
    edgar._TICKERS_CACHE = None
    with _patch(edgar, _edgar_router):
        out = mcp_server.search_sec_filings(company="Viking Therapeutics")
    assert out["resolved_cik"] == "0001607678" and out["own_filer_only"] is True
    assert out["count"] == 2                         # both VKTX own filings
    filers = {r["title"].split(" — ")[0] for r in out["results"]}
    assert filers == {"Viking Therapeutics, Inc."}   # no Persistent/Buffalo noise


def test_sec_own_filer_only_resolves_the_query_as_entity():
    edgar._TICKERS_CACHE = None
    with _patch(edgar, _edgar_router):
        out = mcp_server.search_sec_filings(query="Viking Therapeutics", own_filer_only=True)
    assert out["resolved_cik"] == "0001607678" and out["count"] == 2


def test_sec_ticker_resolves_to_cik():
    edgar._TICKERS_CACHE = None
    with _patch(edgar, _edgar_router):
        out = mcp_server.search_sec_filings(company="VKTX")
    assert out["resolved_cik"] == "0001607678" and out["count"] == 2


def test_sec_entity_not_found_is_explicit():
    edgar._TICKERS_CACHE = None
    with _patch(edgar, _edgar_router):
        out = mcp_server.search_sec_filings(company="Nonexistent Holdings")
    assert out["status"] == "entity_not_found" and out["entity"] == "Nonexistent Holdings"
    assert out["count"] == 0 and out["results"] == []


def test_sec_requires_query_or_company():
    out = mcp_server.search_sec_filings()
    assert "error" in out and out["count"] == 0


def test_sec_missing_ua_gives_actionable_403():
    import os
    saved = os.environ.pop("OPENBIONEWS_EDGAR_UA", None)  # force the default UA
    try:
        with _patch(edgar, raise_exc=HTTPJSONError(
                "HTTP 403 from https://efts.sec.gov/LATEST/search-index: <html>Forbidden</html>")):
            out = mcp_server.search_sec_filings("collaboration")
    finally:
        if saved is not None:
            os.environ["OPENBIONEWS_EDGAR_UA"] = saved
    assert "OPENBIONEWS_EDGAR_UA" in out["error"]        # actionable, not raw 403 HTML


def test_resolve_cik_handles_names_tickers_and_raw_ciks():
    edgar._TICKERS_CACHE = None
    with _patch(edgar, _edgar_router):
        assert edgar.resolve_cik("Viking Therapeutics") == "0001607678"   # name
        assert edgar.resolve_cik("viking therapeutics inc") == "0001607678"  # + suffix
        assert edgar.resolve_cik("VKTX") == "0001607678"                  # ticker
        assert edgar.resolve_cik("1607678") == "0001607678"               # raw CIK
        assert edgar.resolve_cik("No Such Biotech") is None               # miss


# --- D. a successful-but-empty search is an explicit, citable negative -------- #
def test_empty_search_returns_no_current_results():
    with _patch(openfda_shortages, {"results": []}):
        out = mcp_server.search_fda_shortages("tirzepatide")
    assert out["status"] == "no_current_results" and out["count"] == 0
    assert out["results"] == [] and "query_used" in out and out["as_of"]


# --- E. since cursor filters + flags is_new ---------------------------------- #
def test_since_filters_and_flags_new():
    with _patch(clinicaltrials, CT_MANY):
        out = mcp_server.search_clinical_trials("study", since="2026-09-01", limit=10)
    ids = [r["source"]["id"] for r in out["results"]]
    assert "NCT_C" not in ids                        # Aug study is before the cursor
    assert all(r["is_new"] for r in out["results"])  # everything returned is new


# --- F. provenance travels on every block ------------------------------------ #
def test_provenance_fields_present():
    with _patch(clinicaltrials, CT):
        out = mcp_server.search_clinical_trials("crispr")
    assert out["endpoint"].startswith("https://clinicaltrials.gov")
    assert out["as_of"] and "T" in out["retrieved_at"]


# --- G. token-budgeted pagination ------------------------------------------- #
def test_pagination_offset_and_truncated_flag():
    with _patch(clinicaltrials, CT_MANY):
        page1 = mcp_server.search_clinical_trials("study", limit=2, offset=0)
        page2 = mcp_server.search_clinical_trials("study", limit=2, offset=2)
    assert page1["count"] == 2 and page1["truncated"] is True
    assert page2["count"] == 1 and page2["truncated"] is False
    assert {r["source"]["id"] for r in page1["results"]}.isdisjoint(
        {r["source"]["id"] for r in page2["results"]})


# --- H. watchlist source filter ---------------------------------------------- #
def test_watchlist_digest_spans_all_sources():
    with _patch(clinicaltrials, CT), _patch(openfda, RECALLS), \
         _patch(openfda_approvals, APPROVALS), _patch(openfda_shortages, SHORTAGES), \
         _patch(openfda_events, EVENTS), _patch(openfda_labels, LABELS), \
         _patch(federalregister, FEDREG), _patch(pubmed, _pubmed_fake), \
         _patch(edgar, EDGAR):
        out = mcp_server.watchlist_digest(["beam"], limit_per_source=5)
    assert out["total"] >= 9 and len(out["sources"]) == 9
    assert {s["key"] for s in out["sources"]} == set(mcp_server._DIGEST_KEYS)


def test_watchlist_digest_sources_filter_restricts_blocks():
    with _patch(clinicaltrials, CT), _patch(edgar, EDGAR):
        out = mcp_server.watchlist_digest(["beam"], sources=["sec", "trials"])
    keys = {s["key"] for s in out["sources"]}
    assert keys == {"sec", "trials"}
    assert out["sources_requested"] == ["sec", "trials"]


# --- revision regressions ---------------------------------------------------- #
def test_match_uses_word_boundaries_not_substrings():
    it = Item(title="Long-term trials of statins", link="x",
              summary="Also recruiting adults with GLP-1 base-editing", source="s")
    hits = lambda q: mcp_server._match(it, {}, [q])["terms"]
    assert hits("ALS") == []            # not inside "trials" / "also"
    assert hits("statin") == ["statin"]  # a longer word may run on (plural)
    assert hits("GLP-1") == ["GLP-1"]    # punctuation-insensitive
    assert hits("base editing") == ["base editing"]
    assert hits("adult") == ["adult"]


def test_paging_past_end_is_not_a_false_negative():
    with _patch(clinicaltrials, CT_MANY):
        out = mcp_server.search_clinical_trials("study", limit=2, offset=10)
    assert out.get("status") != "no_current_results"    # results exist, just not here
    assert out["count"] == 0 and "page_note" in out


def test_salience_works_without_a_query():
    with _patch(openfda, RECALLS_SEV):
        out = mcp_server.search_fda_recalls(rank_by="salience")
    assert out["ranked_by"] == "salience"
    assert out["results"][0]["facts"]["classification"] == "Class I"


def test_salience_components_report_only_scored_signals():
    with _patch(clinicaltrials, CT_SALIENCE):
        out = mcp_server.search_clinical_trials("semaglutide", rank_by="salience", verbose=True)
    comp = out["results"][0]["relevance_components"]
    assert set(comp) == {"enrollment", "phase", "results_posted", "maturity"}


def test_digest_salience_reaches_landmark_and_respects_limit():
    sorts = []
    def router(url, *a, **k):
        sorts.append((k.get("params") or {}).get("sort"))
        return _ct_sort_router(url, *a, **k)
    with _patch(clinicaltrials, router):
        out = mcp_server.watchlist_digest(["semaglutide"], sources=["trials"],
                                          rank_by="salience", limit_per_source=2)
    blk = out["sources"][0]
    assert "EnrollmentCount:desc" in sorts                 # enrollment pass ran
    assert blk["results"][0]["source"]["id"] == "NCT_SELECT"
    assert blk["count"] == 2 and blk["truncated"] is True  # capped at limit_per_source


def test_digest_rejects_unknown_source_keys():
    out = mcp_server.watchlist_digest(["x"], sources=["trial"])
    assert "unknown source key(s): trial" in out["error"] and out["sources"] == []


def test_paging_inputs_are_sanitised():
    cap = {}
    orig = clinicaltrials.get_json
    clinicaltrials.get_json = lambda url, *a, **k: (cap.update(k.get("params") or {}) or CT_MANY)
    try:
        out = mcp_server.search_clinical_trials("study", limit=5000, offset=-3)
    finally:
        clinicaltrials.get_json = orig
    assert int(cap["pageSize"]) <= 1000                    # never above the API maximum
    assert out["count"] == 3                               # negative offset treated as 0


def test_invalid_since_is_an_error_not_an_empty_result():
    with _patch(clinicaltrials, CT):
        out = mcp_server.search_clinical_trials("crispr", since="last week")
    assert "YYYY-MM-DD" in out["error"] and "status" not in out


def test_combined_phase_string_filters_both_phases():
    cap = {}
    orig = clinicaltrials.get_json
    clinicaltrials.get_json = lambda url, *a, **k: (cap.update(k.get("params") or {}) or CT)
    try:
        mcp_server.search_clinical_trials("crispr", phase="Phase 2/Phase 3")
    finally:
        clinicaltrials.get_json = orig
    assert cap["filter.advanced"] == "AREA[Phase](PHASE2 OR PHASE3)"


def test_upstream_failure_is_returned_as_data():
    with _patch(clinicaltrials, raise_exc=HTTPJSONError("boom")):
        out = mcp_server.search_clinical_trials("x")
    assert "boom" in out["error"] and out["results"] == [] and out["count"] == 0
    assert out["endpoint"]  # provenance still present on an error block


def test_all_tools_registered():
    assert len(mcp_server.TOOLS) == 10
    assert all(callable(fn) and fn.__doc__ for fn in mcp_server.TOOLS)
    assert hasattr(mcp_server, "serve") and hasattr(mcp_server, "build_server")


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{'all passed' if not failures else str(failures) + ' failed'}")
    sys.exit(1 if failures else 0)
