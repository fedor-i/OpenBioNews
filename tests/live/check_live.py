"""Live contract checks against the real upstream APIs.

The unit tests run on saved sample payloads, so they can't notice when an agency
changes its API: a renamed field, a dropped parameter, a new page-size limit. Those
failures don't raise — they quietly return thinner or wrong results (the 0.8.4
enrollment bug was exactly this). This script calls each MCP tool for real and
checks the *shape* of what comes back: records exist, the fields we rely on are
filled in, filters are honoured, and a known landmark trial is still found.

Not part of the normal test suite (it needs the network and the APIs to be up).
It runs daily in CI (.github/workflows/live.yml); run it locally with:

    python tests/live/check_live.py

Exit code 1 if any contract check fails. An API that can't be reached (timeouts,
5xx after retries) is reported as UNREACHABLE and doesn't fail the run unless
--strict is passed — an agency outage isn't a bug in OpenBioNews.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from openbionews import mcp_server as ms  # noqa: E402

SELECT = "NCT03574597"   # semaglutide SELECT: 17,604 patients, Phase 3, results posted
LILLY_CIK = "0000059478"


class Unreachable(Exception):
    """The upstream API couldn't be reached — an outage, not a contract break."""


class Skipped(Exception):
    """The check can't run in this environment (e.g. missing credentials)."""


def _transient(err: str) -> bool:
    if "could not reach" in err or "timed out" in err.lower():
        return True
    m = re.search(r"HTTP (\d{3})", err)
    return bool(m) and (m.group(1).startswith("5") or m.group(1) == "429")


def call(fn, **kwargs) -> dict:
    """Call an MCP tool, retrying transient upstream errors (3 tries, backoff)."""
    for attempt in range(3):
        out = fn(**kwargs)
        err = out.get("error")
        if not err:
            return out
        if not _transient(err):
            raise AssertionError(f"upstream error: {err}")
        if attempt < 2:
            time.sleep(5 * (attempt + 1))
    raise Unreachable(err)


def share(results, pred) -> float:
    return sum(1 for r in results if pred(r)) / len(results) if results else 0.0


def need(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def meta(r: dict) -> dict:
    return r.get("meta") or {}


# --------------------------------------------------------------------------- #
# ClinicalTrials.gov
# --------------------------------------------------------------------------- #
def check_trials_fields_and_salience():
    out = call(ms.search_clinical_trials, query="semaglutide", rank_by="salience",
               limit=20, verbose=True)
    res = out["results"]
    need(len(res) >= 10, f"only {len(res)} semaglutide trials returned")
    need(out.get("ranked_by") == "salience", f"ranked_by={out.get('ranked_by')!r}")
    # The fields the salience score reads. If ct.gov prunes or renames one, the score
    # silently degrades — this is the check that would have caught the 0.8.4 bug.
    need(share(res, lambda r: (meta(r).get("enrollment") or 0) > 0) >= 0.8, "enrollment mostly missing")
    need(share(res, lambda r: meta(r).get("phases")) >= 0.8, "phases mostly missing")
    need(share(res, lambda r: meta(r).get("status")) == 1.0, "status missing")
    need(share(res, lambda r: meta(r).get("start_date")) >= 0.8, "start_date mostly missing")
    need(share(res, lambda r: meta(r).get("primary_endpoints")) >= 0.6, "primary endpoints mostly missing")
    need(any(meta(r).get("has_results") for r in res), "no result has has_results=true")
    comps = res[0].get("relevance_components") or {}
    need(set(comps) == set(ms._SALIENCE_FEATURES), f"salience components {sorted(comps)}")
    ids = [meta(r).get("nct_id") for r in res]
    need(SELECT in ids, f"landmark {SELECT} (SELECT) not in the top 20 by salience")
    return f"{len(res)} trials; SELECT at #{ids.index(SELECT) + 1}"


def check_trials_recency_window():
    out = call(ms.search_clinical_trials, query="cancer", recent_days=30, limit=20)
    res = out["results"]
    need(res, "no cancer trials updated in the last 30 days")
    cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 32 * 86400))
    old = [r["date"] for r in res if r.get("date") and r["date"] < cutoff]
    need(not old, f"records older than the 30-day window: {old[:3]}")
    dates = [r["date"] for r in res if r.get("date")]
    need(dates == sorted(dates, reverse=True), "recency mode is not newest-first")
    return f"{len(res)} trials, newest {dates[0] if dates else '?'}"


def check_trials_phase_filter():
    out = call(ms.search_clinical_trials, query="diabetes", phase="3", recent_days=365,
               limit=20, verbose=True)
    res = out["results"]
    need(res, "no Phase 3 diabetes trials in a year")
    bad = [meta(r).get("nct_id") for r in res if "PHASE3" not in (meta(r).get("phases") or [])]
    need(not bad, f"phase=3 filter leaked other phases: {bad[:3]}")
    return f"{len(res)} trials, all Phase 3"


# --------------------------------------------------------------------------- #
# openFDA
# --------------------------------------------------------------------------- #
def check_recalls():
    out = call(ms.search_fda_recalls, limit=20, rank_by="salience")
    res = out["results"]
    need(res, "no recent drug recalls")
    need(share(res, lambda r: r["facts"].get("classification")) == 1.0, "recall classification missing")
    need(share(res, lambda r: r.get("date")) == 1.0, "recall dates missing")
    return f"{len(res)} recalls"


def check_recall_negative():
    out = call(ms.search_fda_recalls, query="zzqxnotarealdrug")
    need(out.get("status") == "no_current_results",
         f"an unknown product should be a citable negative, got {out.get('status') or out.get('count')}")
    return "unknown product -> no_current_results"


def check_approvals():
    out = call(ms.search_fda_approvals, limit=10)
    res = out["results"]
    need(res, "no recent FDA approvals")
    need(share(res, lambda r: r["facts"].get("application_number")) == 1.0, "application_number missing")
    return f"{len(res)} approvals"


def check_shortages():
    out = call(ms.search_fda_shortages, limit=10)
    res = out["results"]
    need(res, "no current drug shortages")
    need(share(res, lambda r: r["facts"].get("status")) == 1.0, "shortage status missing")
    return f"{len(res)} shortages"


def check_adverse_events():
    out = call(ms.search_fda_adverse_events, query="semaglutide")
    res = out["results"]
    need(res, "no FAERS summary for semaglutide")
    f = res[0]["facts"]
    need(f.get("reactions") and (f.get("total") or 0) > 0, f"FAERS facts empty: {sorted(f)}")
    return f"{f.get('total')} reports"


def check_labels():
    out = call(ms.search_fda_labeling, query="semaglutide")
    need(out["results"], "no FDA label for semaglutide")
    return f"{len(out['results'])} labels"


# --------------------------------------------------------------------------- #
# Federal Register, PubMed, SEC EDGAR
# --------------------------------------------------------------------------- #
def check_federal_register():
    out = call(ms.search_federal_register, recent_days=60, limit=10)
    res = out["results"]
    need(res, "no FDA Federal Register documents in 60 days")
    need(share(res, lambda r: r["facts"].get("document_number")) == 1.0, "document_number missing")
    return f"{len(res)} documents"


def check_pubmed():
    out = call(ms.search_pubmed, query="semaglutide", recent_days=90, limit=10)
    res = out["results"]
    need(res, "no semaglutide papers in 90 days")
    need(share(res, lambda r: r["facts"].get("pmid")) == 1.0, "PMID missing")
    need(share(res, lambda r: "pubmed.ncbi.nlm.nih.gov" in r["source"]["url"]) == 1.0, "citation is not a PubMed URL")
    return f"{len(res)} papers"


def check_sec_entity_scoping():
    try:
        out = call(ms.search_sec_filings, company="LLY", recent_days=180, limit=10)
    except AssertionError as exc:
        if "HTTP 403" in str(exc):   # SEC wants a contact User-Agent — configuration, not a break
            raise Skipped("SEC refused the request; add a repository secret EDGAR_UA "
                          "like 'OpenBioNews-CI you@example.com'") from exc
        raise
    res = out["results"]
    need(res, f"no Eli Lilly filings in 180 days (status={out.get('status')!r}, "
              f"resolved_cik={out.get('resolved_cik')!r})")
    stray = [r["facts"].get("filer") for r in res if LILLY_CIK not in (r["facts"].get("ciks") or [])]
    need(not stray, f"entity mode returned other filers: {stray[:3]}")
    return f"{len(res)} filings, all Lilly's own"


CHECKS = [
    ("ClinicalTrials.gov: fields + salience", check_trials_fields_and_salience),
    ("ClinicalTrials.gov: recency window", check_trials_recency_window),
    ("ClinicalTrials.gov: phase filter", check_trials_phase_filter),
    ("openFDA: recalls", check_recalls),
    ("openFDA: citable negative", check_recall_negative),
    ("openFDA: approvals", check_approvals),
    ("openFDA: shortages", check_shortages),
    ("openFDA: adverse events", check_adverse_events),
    ("openFDA: labels", check_labels),
    ("Federal Register", check_federal_register),
    ("PubMed", check_pubmed),
    ("SEC EDGAR: entity scoping", check_sec_entity_scoping),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--strict", action="store_true", help="treat unreachable APIs as failures")
    args = ap.parse_args(argv)

    rows, failed, unreachable = [], 0, 0
    for name, fn in CHECKS:
        try:
            rows.append(("PASS", name, fn()))
        except Unreachable as exc:
            unreachable += 1
            rows.append(("UNREACHABLE", name, str(exc)[:200]))
        except Skipped as exc:
            rows.append(("SKIPPED", name, str(exc)[:200]))
        except AssertionError as exc:
            failed += 1
            rows.append(("FAIL", name, str(exc)[:300]))
        except Exception as exc:  # a crash is a failure too
            failed += 1
            rows.append(("FAIL", name, f"{type(exc).__name__}: {exc}"[:300]))
    for status, name, detail in rows:
        print(f"{status:<12} {name}: {detail}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## Live API contract checks\n\n| Result | Check | Detail |\n|---|---|---|\n")
            for status, name, detail in rows:
                icon = {"PASS": "✅", "FAIL": "❌"}.get(status, "⚠️")
                fh.write(f"| {icon} {status} | {name} | {detail.replace('|', '/')} |\n")

    passed = sum(1 for r in rows if r[0] == "PASS")
    print(f"\n{passed} passed, {failed} failed, {unreachable} unreachable, "
          f"{len(rows) - passed - failed - unreachable} skipped")
    for status, name, detail in rows:   # annotations show on the run page without opening logs
        if status == "FAIL":
            print(f"::error title={name}::{detail}")
        elif status in ("UNREACHABLE", "SKIPPED"):
            print(f"::warning title={name}::{status.lower()}: {detail}")
    return 1 if failed or (args.strict and unreachable) else 0


if __name__ == "__main__":
    sys.exit(main())
