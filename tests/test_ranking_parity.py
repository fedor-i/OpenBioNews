"""Python ↔ website ranking parity.

The MCP server (openbionews/mcp_server.py) and the hosted Insights page
(docs/index.html) each implement the salience ("what matters") ranking — one in
Python, one in JavaScript. tests/fixtures/ranking_vectors.json is the shared spec:
every case is scored by BOTH implementations and checked against its expected
value, so a weight changed on one side only fails here instead of drifting.

The JavaScript side needs Node. It is skipped (with a notice) when Node isn't on
PATH, unless OBN_REQUIRE_NODE=1 — CI sets that so the check can't silently vanish.

Runs with pytest (``pytest``) or directly (``python tests/test_ranking_parity.py``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openbionews import mcp_server as ms  # noqa: E402
from openbionews.models import Item  # noqa: E402

VECTORS = json.loads((ROOT / "tests" / "fixtures" / "ranking_vectors.json").read_text("utf-8"))
TOL = VECTORS["tolerance"]
TRIALS = VECTORS["trial_salience"]["cases"]
GENERIC = VECTORS["generic_salience"]["cases"]
_SIGNALS = {"recalls": ms._recall_signal, "shortages": ms._shortage_signal}


# --------------------------------------------------------------------------- #
# Python (MCP server)
# --------------------------------------------------------------------------- #
def _published(age_days: int) -> datetime:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=age_days)


def _py_trial(case: dict) -> float:
    item = Item(title="t", link="https://example.org", meta={
        "phases": case["phases"], "enrollment": case["enrollment"],
        "status": case["status"], "has_results": case["has_results"]})
    return ms._trial_salience(item, [])["score"]


def _py_generic(case: dict) -> float:
    # Build the record so the MCP's own matcher yields the case's `match`
    # (1 = the only query term is in the title; 0.5 = one of two terms, not in the title).
    title, summary, terms = "Record", "", []
    if case["match"] == 1:
        title, terms = "Record about alpha", ["alpha"]
    elif case["match"] == 0.5:
        summary, terms = "Mentions alpha only.", ["alpha", "beta"]
    meta = {"classification": case.get("classification", ""), "status": case.get("status", "")}
    item = Item(title=title, link="https://example.org", summary=summary,
                published=_published(case["age_days"]), meta=meta)
    return ms._generic_salience(item, terms, _SIGNALS.get(case["source"]))["score"]


def test_python_trial_salience_matches_spec():
    for case in TRIALS:
        got = _py_trial(case)
        assert abs(got - case["expected"]) <= TOL, f"{case['name']}: Python {got} != {case['expected']}"


def test_python_generic_salience_matches_spec():
    for case in GENERIC:
        got = _py_generic(case)
        assert abs(got - case["expected"]) <= TOL, f"{case['name']}: Python {got} != {case['expected']}"


# --------------------------------------------------------------------------- #
# JavaScript (website)
# --------------------------------------------------------------------------- #
_JS_START = "// Shared scoring primitives."
_JS_END = "function renderInsights(){"

_JS_HARNESS = r"""
const V = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
const iso = d => { const t = new Date(); t.setUTCHours(0,0,0,0); t.setUTCDate(t.getUTCDate()-d); return t.toISOString().slice(0,10); };
const out = {trials: [], generic: []};
for (const c of V.trial_salience.cases) {
  // as normTrial builds it: "NA" is dropped from the phase list
  const rec = {agency:"trials", phase:c.phases.filter(p=>p&&p!=="NA"), enrollment:c.enrollment,
               status:c.status, hasResults:c.has_results};
  out.trials.push(iSalienceScore(rec));
}
for (const c of V.generic_salience.cases) {
  const rec = {agency:c.source, date:iso(c.age_days), title:"Record", cls:c.classification||""};
  if (c.source === "shortages") rec.title = "Record — shortage" + (c.status ? ` (${c.status})` : "");
  out.generic.push(iSalienceScore(rec, c.match));
}
console.log(JSON.stringify(out));
"""


def _js_scores():
    node = shutil.which("node")
    if not node:
        if os.environ.get("OBN_REQUIRE_NODE") == "1":
            raise AssertionError("Node is required (OBN_REQUIRE_NODE=1) but not on PATH")
        return None
    src = (ROOT / "docs" / "index.html").read_text("utf-8")
    assert _JS_START in src and _JS_END in src, "website scoring block markers moved"
    block = src[src.index(_JS_START):src.index(_JS_END)]
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "parity.js"
        script.write_text(block + "\n" + _JS_HARNESS, "utf-8")
        vec = ROOT / "tests" / "fixtures" / "ranking_vectors.json"
        proc = subprocess.run([node, str(script), str(vec)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"node failed: {proc.stderr}"
    return json.loads(proc.stdout)


def test_website_salience_matches_spec():
    js = _js_scores()
    if js is None:
        print("  (skipped: node not on PATH)")
        return
    for case, got in zip(TRIALS, js["trials"]):
        assert abs(got - case["expected"]) <= TOL, f"{case['name']}: website {got} != {case['expected']}"
    for case, got in zip(GENERIC, js["generic"]):
        assert abs(got - case["expected"]) <= TOL, f"{case['name']}: website {got} != {case['expected']}"


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failed else 0)
