"""Landmark-trial benchmark: does rank_by="salience" put the trials that matter on top?

For each drug in benchmarks/landmarks.json this asks the MCP tool for that drug's
trials ranked by salience, and measures Recall@k — the share of the drug's
landmark trials that appear in the top k. The plain recency ranking is scored too,
as the baseline salience has to beat. The macro average over drugs is the headline.

It first checks the benchmark itself: every listed NCT ID must exist and its
registry acronym/title must contain one of the entry's `expect` tokens, so a typo
in the gold set is reported as such rather than counted as a ranking miss.

Needs the network (ClinicalTrials.gov). Runs in CI daily and on every release
(.github/workflows/live.yml); locally:

    python benchmarks/run_landmarks.py [--out results.json]

Exit codes: 0 ok; 1 recall fell below `min_recall_at_k` in landmarks.json;
2 the gold set has an entry that doesn't check out.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openbionews import mcp_server as ms  # noqa: E402
from openbionews.httputil import HTTPJSONError, get_json  # noqa: E402

GOLD = ROOT / "benchmarks" / "landmarks.json"
STUDY_URL = "https://clinicaltrials.gov/api/v2/studies/{}"
MODES = ("salience", "recency")
DEPTH = 20          # how deep we look, to report where a miss actually ranked


def _retry(fn, *args, **kwargs):
    for attempt in range(3):
        try:
            return fn(*args, **kwargs)
        except HTTPJSONError:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def verify_gold(drugs) -> list[str]:
    """Return a problem line per gold entry that doesn't match its registry record."""
    problems = []
    for d in drugs:
        for t in d["trials"]:
            try:
                rec = _retry(get_json, STUDY_URL.format(t["nct"]),
                             params={"fields": "NCTId,Acronym,BriefTitle,OfficialTitle"})
            except HTTPJSONError as exc:
                problems.append(f"{t['nct']} ({t['name']}): {str(exc)[:120]}")
                continue
            ident = (rec.get("protocolSection") or {}).get("identificationModule") or {}
            hay = " ".join(str(ident.get(k, "")) for k in ("acronym", "briefTitle", "officialTitle")).lower()
            if not any(tok.lower() in hay for tok in t["expect"]):
                problems.append(f"{t['nct']} ({t['name']}): registry says "
                                f"acronym={ident.get('acronym')!r} title={ident.get('briefTitle')!r}")
    return problems


def rank_ids(drug: str, mode: str) -> list[str]:
    for attempt in range(3):
        out = ms.search_clinical_trials(query=drug, rank_by=mode, limit=DEPTH, verbose=True)
        if not out.get("error"):
            return [(r.get("meta") or {}).get("nct_id") for r in out["results"]]
        if attempt < 2:
            time.sleep(5 * (attempt + 1))
    raise HTTPJSONError(out["error"])


def run(k: int, drugs) -> dict:
    per_drug = []
    for d in drugs:
        row = {"drug": d["drug"], "area": d["area"], "n": len(d["trials"])}
        for mode in MODES:
            ids = rank_ids(d["drug"], mode)
            hits, misses = [], []
            for t in d["trials"]:
                pos = ids.index(t["nct"]) + 1 if t["nct"] in ids else None
                (hits if pos and pos <= k else misses).append(
                    {"name": t["name"], "nct": t["nct"], "rank": pos})
            row[mode] = {"recall": len(hits) / len(d["trials"]), "hits": hits, "misses": misses}
        per_drug.append(row)
    macro = {m: sum(r[m]["recall"] for r in per_drug) / len(per_drug) for m in MODES}
    total = sum(r["n"] for r in per_drug)
    micro = {m: sum(len(r[m]["hits"]) for r in per_drug) / total for m in MODES}
    return {"k": k, "drugs": len(per_drug), "trials": total,
            "macro_recall": macro, "micro_recall": micro, "per_drug": per_drug}


def _miss_text(misses) -> str:
    return ", ".join(f"{m['name']} (#{m['rank']})" if m["rank"] else f"{m['name']} (not in top {DEPTH})"
                     for m in misses) or "—"


def report(res: dict) -> str:
    k = res["k"]
    lines = [f"## Landmark benchmark — Recall@{k}",
             "",
             f"{res['drugs']} drugs, {res['trials']} landmark trials. "
             f"**Salience {res['macro_recall']['salience']:.2f}** vs recency baseline "
             f"{res['macro_recall']['recency']:.2f} (macro average; micro "
             f"{res['micro_recall']['salience']:.2f} vs {res['micro_recall']['recency']:.2f}).",
             "",
             f"| Drug | Area | Salience R@{k} | Recency R@{k} | Missed by salience (rank) |",
             "|---|---|---|---|---|"]
    for r in res["per_drug"]:
        lines.append(f"| {r['drug']} | {r['area']} | {r['salience']['recall']:.2f} | "
                     f"{r['recency']['recall']:.2f} | {_miss_text(r['salience']['misses'])} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", help="write the full results as JSON here")
    ap.add_argument("--drug", action="append", help="only these drugs (repeatable)")
    args = ap.parse_args(argv)

    spec = json.loads(GOLD.read_text("utf-8"))
    drugs = [d for d in spec["drugs"] if not args.drug or d["drug"] in args.drug]
    try:
        problems = verify_gold(drugs)
        if problems:
            print("Gold set problems (fix benchmarks/landmarks.json):")
            for p in problems:
                print(f"  {p}")
                print(f"::error title=Landmark gold set::{p}")
            return 2
        res = run(spec["k"], drugs)
    except HTTPJSONError as exc:
        print(f"::warning title=Landmark benchmark::ClinicalTrials.gov unreachable: {exc}")
        return 0

    text = report(res)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(text)
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=2), "utf-8")

    floor = spec.get("min_recall_at_k")
    if floor is not None and not args.drug and res["macro_recall"]["salience"] < floor:
        print(f"::error title=Landmark benchmark::salience Recall@{res['k']} "
              f"{res['macro_recall']['salience']:.2f} is below the floor {floor}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
