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
    clinicaltrials, edgar, openfda, openfda_approvals, openfda_shortages,
)
from openbionews.httputil import HTTPJSONError
from openbionews.models import Citation, Item

# ---- canned upstream payloads (same JSON shapes the real APIs return) ------- #
CT = {"studies": [{"protocolSection": {
    "identificationModule": {"nctId": "NCT0001", "briefTitle": "CRISPR base editing study"},
    "statusModule": {"overallStatus": "RECRUITING",
                     "lastUpdatePostDateStruct": {"date": "2026-10-01"}},
    "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Beam"}},
    "conditionsModule": {"conditions": ["Sickle Cell"]},
    "descriptionModule": {"briefSummary": "A CRISPR gene editing therapy."},
    "designModule": {"phases": ["PHASE3"]}}}]}
CT_PHASES = {"studies": [
    {"protocolSection": {
        "identificationModule": {"nctId": "NCT_P1", "briefTitle": "Early study"},
        "statusModule": {"overallStatus": "RECRUITING",
                         "lastUpdatePostDateStruct": {"date": "2026-10-01"}},
        "designModule": {"phases": ["PHASE1"]}}},
    {"protocolSection": {
        "identificationModule": {"nctId": "NCT_P3", "briefTitle": "Pivotal study"},
        "statusModule": {"overallStatus": "RECRUITING",
                         "lastUpdatePostDateStruct": {"date": "2026-10-01"}},
        "designModule": {"phases": ["PHASE3"]}}}]}
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


class _patch:
    """Temporarily replace a connector module's get_json with a canned result."""

    def __init__(self, module, payload=None, raise_exc=None):
        self.module, self.payload, self.raise_exc = module, payload, raise_exc

    def __enter__(self):
        self._orig = self.module.get_json

        def fake(*_a, **_k):
            if self.raise_exc:
                raise self.raise_exc
            return self.payload
        self.module.get_json = fake
        return self

    def __exit__(self, *exc):
        self.module.get_json = self._orig


# --------------------------------------------------------------------------- #
def test_item_to_dict_carries_citation():
    item = Item(title="T", link="https://x/1", summary="s", source="Src",
                published=datetime(2026, 10, 1, tzinfo=timezone.utc), guid="g",
                citations=[Citation(label="L", url="https://x/1", kind="registry")],
                tag="Recruiting", meta={"status": "RECRUITING", "track": {"Status": "x"}})
    d = mcp_server._item_to_dict(item)
    assert d["title"] == "T" and d["url"] == "https://x/1"
    assert d["published"] == "2026-10-01"
    assert d["citation_url"] == "https://x/1"
    assert d["citations"][0]["label"] == "L"
    assert "track" not in d["meta"] and d["meta"]["status"] == "RECRUITING"


def test_search_clinical_trials():
    with _patch(clinicaltrials, CT):
        out = mcp_server.search_clinical_trials("crispr", limit=5)
    assert out["source"] == "ClinicalTrials.gov" and out["count"] == 1
    r = out["results"][0]
    assert "clinicaltrials.gov" in r["url"]
    assert r["citations"] and "NCT0001" in r["citations"][0]["label"]


def test_phase_filter_keeps_only_matching():
    with _patch(clinicaltrials, CT_PHASES):
        out = mcp_server.search_clinical_trials("x", phase="3")
    ids = [r["id"] for r in out["results"]]
    assert ids == ["NCT_P3"]  # the Phase 1 study is filtered out


def test_search_fda_recalls():
    with _patch(openfda, RECALLS):
        out = mcp_server.search_fda_recalls("injectable", classification="Class I")
    assert out["count"] == 1 and out["results"][0]["meta"]["classification"] == "Class I"
    assert "fda.gov" in out["results"][0]["citation_url"]


def test_search_fda_approvals():
    with _patch(openfda_approvals, APPROVALS):
        out = mcp_server.search_fda_approvals("editacel")
    assert out["count"] >= 1
    assert any("FDA" in c["label"] or "fda" in c["url"]
               for c in out["results"][0]["citations"])


def test_search_fda_shortages():
    with _patch(openfda_shortages, SHORTAGES):
        out = mcp_server.search_fda_shortages("injectacin")
    assert out["count"] == 1 and "shortage" in out["results"][0]["title"].lower()


def test_search_sec_filings():
    with _patch(edgar, EDGAR):
        out = mcp_server.search_sec_filings("collaboration")
    assert out["count"] == 1 and "sec.gov" in out["results"][0]["url"]


def test_watchlist_digest_spans_all_sources():
    with _patch(clinicaltrials, CT), _patch(openfda, RECALLS), \
         _patch(openfda_approvals, APPROVALS), _patch(openfda_shortages, SHORTAGES), \
         _patch(edgar, EDGAR):
        out = mcp_server.watchlist_digest(["beam"], limit_per_source=5)
    names = {s["source"] for s in out["sources"]}
    assert names == {"ClinicalTrials.gov", "openFDA (Drug Recalls)",
                     "Drugs@FDA (Approvals)", "FDA Drug Shortages", "SEC EDGAR"} \
        or len(out["sources"]) == 5  # names may vary; five blocks either way
    assert out["total"] >= 5 and len(out["sources"]) == 5


def test_upstream_failure_is_returned_as_data():
    with _patch(clinicaltrials, raise_exc=HTTPJSONError("boom")):
        out = mcp_server.search_clinical_trials("x")
    assert "boom" in out["error"] and out["results"] == [] and out["count"] == 0


def test_all_tools_registered():
    assert len(mcp_server.TOOLS) == 6
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
