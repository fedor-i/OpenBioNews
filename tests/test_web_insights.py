"""Structural guard-rail tests for the hosted Insights page (docs/index.html).

The Insights tab's analytics are deterministic, no-LLM JavaScript embedded in a
single static file. Their *behaviour* is exercised by the Playwright validators
under ``tests/web/`` (Node + a browser). Those can't run in this project's
stdlib-only, browser-free CI, so this module is the portable tripwire that runs
everywhere: it reads the page source and asserts the correctness guard rails are
still present, so a refactor can't silently drop one (e.g. re-introduce the
"always three themes" bug, or delete the rising-term noise filter).

These are intentionally coarse string/structure checks, not behavioural tests —
they protect invariants, they don't re-verify the maths. Keep the anchors in
sync with docs/index.html when the analytics are deliberately changed.

Runs with pytest (``pytest``) or directly (``python tests/test_web_insights.py``).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / "docs" / "index.html"
SRC = INDEX.read_text(encoding="utf-8")


def _script() -> str:
    """Concatenate every <script> body so checks ignore markup/CSS."""
    return "\n".join(re.findall(r"<script>(.*?)</script>", SRC, re.S))


def test_index_exists_and_has_insights_tab():
    assert INDEX.exists(), f"missing {INDEX}"
    assert "tab-insights" in SRC, "Insights tab markup/handler went missing"
    assert "window.OBN_INSIGHTS" in SRC, "Insights test hook removed"


def test_adaptive_theme_count_not_forced_to_three():
    js = _script()
    # The silhouette sweep must exist...
    assert "const silhouette=" in js, "silhouette scorer removed"
    assert re.search(r"for\(let k=2;k<=kmax", js), "adaptive-K silhouette sweep removed"
    # ...and the old bug (forcing K to 3 at the top of clusterTerms) must NOT return.
    assert not re.search(r"K\s*=\s*Math\.max\(1,\s*Math\.min\(K\s*\|\|\s*3", js), \
        "clusterTerms is forcing K=3 again — adaptive K regressed"


def test_adaptive_k_collapses_single_topic():
    # A silhouette floor must gate the split, so a mono-topic corpus stays one theme
    # instead of being cut into two near-even halves with no real structure.
    js = _script()
    assert "SIL_FLOOR" in js, "silhouette floor removed — mono-topic will be over-split"
    assert re.search(r"best<SIL_FLOOR\)\s*assign=run\(1\)", js), \
        "single-theme collapse (best<floor -> run(1)) regressed"


def test_seed_tiebreak_spreads_clusters():
    # Farthest-point seeding breaks ties by total distance to the seed set, so
    # seeds land one-per-island instead of doubling up (the k=3 degeneracy fix).
    assert "far=seeds.length-sm" in _script(), "seed tie-break (spread) regressed"


def test_theme_needs_two_records():
    # A lone record is already in Sources; don't manufacture a one-item "theme".
    assert "recIdxs[k].length<2" in _script(), "min-2-record theme guard removed"


def test_rising_terms_guard_rails():
    js = _script()
    assert "if(rN<4 || bN<4) return [];" in js, "rising-terms min-document guard removed"
    assert re.search(r"if\(rc<2\)\s*continue", js), "rising-terms min-support guard removed"
    assert "lift>=1.5" in js, "rising-terms lift threshold removed"


def test_rising_terms_exclude_undated_records():
    # Undated records must not be dumped into the baseline (that masks real momentum).
    js = _script()
    assert "function riseWindow" in js, "undated-record exclusion helper removed"


def test_supplemental_approvals_surface_but_filtered():
    js = _script()
    assert "/:s:/.test(r.id)" in js, "supplemental-approval detection removed"
    assert "Supplement" in js, "supplemental-approval label removed"
    # Only substantive (label/efficacy) supplements are notable, deduped per app —
    # otherwise one drug's routine CMC churn floods the card and buries real recalls.
    assert "SUBSTANTIVE" in js, "supplemental class filter removed (CMC/REMS churn will flood Notable)"
    assert "const out=[], suppl=new Map();" in js, "per-application supplement dedup removed"


def test_coverage_boundary_banner():
    # The scope disclaimer must stay honest: US regulators (+ PubMed literature),
    # no EMA/ex-US regulators, no press releases.
    assert 'class="icov"' in SRC, "coverage-boundary banner removed"
    assert "US regulators" in SRC
    assert "EMA" in SRC and "no press releases" in SRC


def test_insights_gathers_all_sources():
    # The Insights (beta summary) digest pulls from every source, not just the
    # original five — Federal Register and PubMed are included in the fetch and the
    # by-source agency map.
    js = _script()
    assert "function fetchFedRegInsights" in js, "Federal Register not pulled into Insights"
    assert "function fetchPubMedInsights" in js, "PubMed not pulled into Insights"
    assert "fedreg:" in js and "pubmed:" in js, "new sources missing from the Insights agency map"
    assert "const I_AGENCIES" in js, "Insights agency list (superset of TABS) removed"


def test_cross_agency_company_canonicalisation():
    # One firm counted once across agencies (strip ticker/suffix before counting).
    js = _script()
    assert "function canonCompany" in js, "company canonicalisation removed"
    assert "function companyGroups" in js, "company grouping removed"


def test_find_similar_on_references():
    # Each reference offers a TF-IDF-cosine "find similar" jump, reusing the filter.
    js = _script()
    assert "function similarRecords" in js, "find-similar similarity model removed"
    assert 'class="isim ifacet"' in js, "find-similar chip removed from source cards"
    assert "similar:" in js, "find-similar facet key removed"


def test_stoplist_covers_known_leaks():
    # Connective / discourse / comparative words that leaked into the cloud and
    # rising terms on live data must stay in the stoplist.
    js = _script()
    for w in ("which", "through", "actually", "namely", "showed", "broader", "develop"):
        assert f" {w} " in js or f'"{w} ' in js, f"stopword '{w}' missing from I_STOP"


def test_therapeutic_areas_expand_to_condition_bundles():
    # The therapeutic-area seed buttons (Oncology/Cardiometabolic/Neurology/
    # Immunology/Rare disease) must each expand to a *bundle* of representative
    # conditions, not a single disease — mirrors sources.py THERAPEUTIC_AREAS.
    # Regression guard for "Immunology returns only rheumatoid arthritis".
    js = _script()
    assert re.search(r"immunology:\{label:", js), "immunology therapeutic-area topic removed"
    for cond in ("psoriasis", "inflammatory bowel disease", "lupus"):
        assert cond in js, f"immunology lost its '{cond}' condition (narrowed to RA again)"
    # The seed buttons point at the area names (expandable topics), not lone diseases.
    for area in ("oncology", "cardiometabolic", "neurology", "immunology", "infectious"):
        assert f'data-add="{area}"' in SRC, f"{area} seed button no longer points at the area topic"
    # Each area must resolve as a multi-condition topic.
    for area in ("oncology", "cardiometabolic", "neurology", "rare_disease", "infectious"):
        assert re.search(area + r":\{label:", js), f"{area} therapeutic-area topic removed"


def test_stat_bar_labels_spell_out_on_hover():
    # Truncated company/area/source bar labels must carry their full text (data-full)
    # and be flagged for the CSS hover tooltip, so a name like "M.D. Anderson…" spells out.
    js = _script()
    assert "function markClippedBars" in js, "stat-bar clip-flagging pass removed"
    assert 'data-full="' in js, "bar rows no longer carry the full label text"
    assert "content:attr(data-full)" in SRC, "hover tooltip CSS (spell-out) removed"


def test_insights_cards_carry_full_description():
    # Insights source cards show the full detailed study write-up (behind "… more"),
    # while the analytics keep keying off the brief summary (r.text stays the brief).
    js = _script()
    assert "full:dig(ps,\"descriptionModule\",\"detailedDescription\")" in js, \
        "normTrial no longer carries the full detailed description"
    assert "r.full||r.text" in js, "Insights card no longer prefers the full description"
    assert 'ctp.append("fields",CT_FIELDS_FULL)' in js, \
        "Insights CT fetch no longer requests DetailedDescription"


def test_fda_adverse_events_tab():
    # The FAERS adverse-events tab queries openFDA's reaction COUNT aggregation and
    # must keep the "spontaneous reports, not incidence rates" causation caveat.
    js = _script()
    assert 'id="tab-events"' in SRC and 'id="panel-events"' in SRC, "FAERS tab markup removed"
    assert "function searchEvents" in js, "FAERS search handler removed"
    assert "count=patient.reaction.reactionmeddrapt.exact" in js, "FAERS count aggregation removed"
    assert "not incidence rates" in SRC, "FAERS no-causation caveat removed"


def test_custom_date_range():
    # Each time control (data tabs + Insights) offers a "Specific range…" option that
    # reveals from/to date inputs and drives an explicit historic range query.
    js = _script()
    assert "function dateRange" in js, "shared date-range resolver removed"
    assert "function windowRange" in js, "Insights custom-range resolver removed"
    assert SRC.count('class="daterange"') >= 5, "custom-range date inputs missing from a time control"
    assert SRC.count('>Specific range…<') >= 5, "'Specific range' option missing from a time control"
    assert 'id="t_from"' in SRC and 'id="i_from"' in SRC, "from/to date inputs removed"


def test_record_focused_view():
    # Every record gets a "related" affordance that opens a focus overlay pulling
    # connected records across sources — including PubMed publications.
    js = _script()
    assert "function openFocus" in js, "focused-view opener removed"
    assert "function addFocusButtons" in js, "related-record buttons removed"
    assert "FOCUS_GROUPS" in js, "focus source groups removed"
    assert "eutils.ncbi.nlm.nih.gov" in js, "PubMed (publications strand) removed from focus view"
    assert "fGroupPubs" in js and "fGroupTrials" in js, "focus group fetchers removed"
    # A trial's own linked publications (ClinicalTrials.gov referencesModule) must lead
    # the Publications group, flagged prominently, ahead of keyword-matched literature.
    assert "referencesModule" in js, "study's directly-linked publications not pulled into the focus view"
    assert '"flinked"' in js or "flinked" in SRC, "prominent styling for linked publications removed"


def test_fda_labeling_tab():
    # The FDA labels tab looks up the current SPL label per drug and surfaces its
    # approved indications and any boxed warning, cited to openFDA.
    js = _script()
    assert 'id="tab-labels"' in SRC and 'id="panel-labels"' in SRC, "FDA labels tab markup removed"
    assert "function searchLabels" in js, "FDA labels search handler removed"
    assert "api.fda.gov/drug/label" in js, "openFDA label endpoint removed"
    assert "Boxed warning" in js, "boxed-warning flag removed from the label card"


def test_federal_register_tab():
    # The Federal Register tab queries the FR documents API scoped to the FDA and
    # renders cited document cards (guidances, adcomm notices, rules).
    js = _script()
    assert 'id="tab-fedreg"' in SRC and 'id="panel-fedreg"' in SRC, "Federal Register tab markup removed"
    assert "function searchFedReg" in js, "Federal Register search handler removed"
    assert "federalregister.gov/api" in js, "Federal Register API endpoint removed"
    assert "food-and-drug-administration" in js, "FDA agency scope removed"


def test_group_sources_by_cluster():
    # The Sources list can be grouped into its emergent-theme clusters (+ an Other
    # bucket) as a clustered way to read the references.
    js = _script()
    assert "function layoutSources" in js, "grouped-sources layout removed"
    assert "function wireSourceGrouping" in js, "grouped-sources toggle wiring removed"
    assert 'id="isrcview"' in js, "Sources view toggle removed"
    assert '"isrc-grp"' in js or "isrc-grp" in SRC, "cluster-section heading removed"
    # No duplicates in the similar set: content-duplicate records collapse, and the
    # rendered id set is deduped before it reaches the filter.
    assert re.search(r"const sig=docTokens\.map", js), "content-signature dedup removed from similarRecords"
    assert "arr.indexOf(v)===ix" in js, "id-set dedup removed from the find-similar chip"


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
