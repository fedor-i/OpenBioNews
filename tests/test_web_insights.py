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


def test_notable_split_into_category_drawers():
    # "Notable right now" is divided into collapsible category drawers (halted trials,
    # recalls, shortages, adverse events, approvals, Federal Register, publications).
    js = _script()
    assert "function notableCategories" in js, "Notable category grouping removed"
    assert 'cat:"halted"' in js, "halted-trials category removed from Notable"
    assert '<details class="ndrawer' in js, "Notable collapsible drawers removed"
    for key in ('cat:"recalls"', 'cat:"shortages"', 'cat:"events"', 'cat:"papers"', 'cat:"regulatory"'):
        assert key in js, f"Notable category {key} removed"


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
    # FAERS + FDA labels are "also tracked": counted in By-source but excluded from
    # the analytics corpus (their tokens are zeroed so they don't skew word cloud/themes).
    assert "function fetchFaersInsights" in js and "function fetchLabelsInsights" in js, \
        "FAERS / FDA labels not tracked in Insights"
    assert "if(r.aux) docTokens[i]=[]" in js, "aux records not excluded from the analytics corpus"
    assert 'events:"FDA adverse events"' in js and 'labels:"FDA labels"' in js, \
        "aux sources missing from the Insights agency map"


def test_aux_excluded_from_all_term_analytics():
    # Zeroing aux tokens isn't enough: YAKE! and BM25 re-tokenise raw text, and the
    # max-doc-frequency filter counts documents — all three must exclude aux too, or
    # FAERS/label reference text leaks back into key phrases, ranking, and the MDF cut.
    js = _script()
    assert "yakeKeyphrases(recs.filter(r=>!r.aux)" in js, "YAKE! key phrases still include aux reference text"
    assert "recs.reduce((n,r)=>n+(r.aux?0:1),0)" in js, "max-doc-frequency denominator still counts aux"
    assert "if(r.aux) bmScore.set(i,-Infinity)" in js, "aux records not pushed to the bottom of BM25 ranking"


def test_journal_and_agency_not_therapeutic_areas():
    # A PubMed journal name and a Federal Register issuing agency are NOT therapeutic
    # areas — they must stay out of `areas` (which feeds "Top therapeutic areas") and
    # live in their own fields instead. Regression guard for journals/agencies showing
    # up as therapeutic areas.
    js = _script()
    assert "areas:[], journal:(r.fulljournalname" in js, "PubMed journal leaking back into therapeutic areas"
    assert "areas:[], gov:ag" in js, "Federal Register agency leaking back into therapeutic areas"
    assert 'note:r.journal||"PubMed"' in js, "Notable publication note no longer reads the journal field"


def test_executive_rollup_and_headline_split():
    # The fold leads with a deterministic one-line executive rollup (cited counts), and
    # the headline count distinguishes dated developments from aux reference cards.
    js = _script()
    assert 'class="irollup"' in js, "executive rollup line removed"
    assert "High-signal in" in js and "No high-signal events flagged" in js, "rollup copy removed"
    assert "const coreN=recs.reduce((n,r)=>n+(r.aux?0:1),0)" in js, "developments/reference headline split removed"
    assert "reference card" in js, "aux reference-card framing removed from the headline"


def test_momentum_delta_half_window():
    # A half-window momentum line compares dated developments in the newer half of the
    # window against the earlier half — deterministic, no second network fetch.
    js = _script()
    assert 'class="idelta"' in js, "half-window momentum line removed"
    assert "recent half" in js and "earlier half" in js, "momentum half-window framing removed"


def test_boxed_warnings_promoted_to_notable():
    # A boxed warning is the strongest FDA label caution and must surface in Notable
    # even though the label record is aux/also-tracked. FAERS must be framed as a
    # reported-reactions signal, not an incidence rate.
    js = _script()
    assert 'cat:"boxed"' in js, "boxed-warning Notable category removed"
    assert "Boxed warnings (FDA labels)" in js, "boxed-warning drawer label removed"
    assert "boxed:boxed" in js or "boxed," in js, "label records no longer flag a boxed warning"
    assert "signal, not incidence" in js, "FAERS no-incidence framing removed from Notable"


def test_cross_agency_company_canonicalisation():
    # One firm counted once across agencies (strip ticker/suffix before counting).
    js = _script()
    assert "function canonCompany" in js, "company canonicalisation removed"
    assert "function companyGroups" in js, "company grouping removed"
    # & normalised to "and", industry descriptors stripped, suffix strip iterates —
    # so "Eli Lilly & Co" == "Eli Lilly and Company" and "Novartis Pharmaceuticals"
    # == "Novartis Pharma" collapse to one row.
    assert 'replace(/&/g," and ")' in js, "'&' not normalised to 'and' in canonCompany"
    assert "COMPANY_DESC" in js, "industry-descriptor stripping removed from canonCompany"
    assert "while(s && s!==prev)" in js, "iterative suffix stripping removed from canonCompany"


def test_monthly_volume_proration_capped_and_ranged():
    # Partial edge-month proration is capped (a 2-day sliver can't read as a 15/month
    # spike), and the sparkline uses the actual window range, not a days-ago guess.
    js = _script()
    assert "Math.min(md/covered, 3)" in js, "partial-month proration multiplier no longer capped"
    assert "monthlyVolume(recs, {from:R.fromISO, to:R.toISO})" in js, \
        "sparkline no longer uses the actual window range (breaks custom ranges)"


def test_rising_terms_truncation_honest():
    # The rising-terms card reports when it's showing only the top N of a longer list.
    js = _script()
    assert "top.total=out.length" in js, "rising-terms total count not exposed"
    assert "accelerating terms." in js, "rising-terms truncation hint removed"


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


def test_on_accent_ink_token():
    # Text on an accent/warn/crit fill uses a theme-aware ink token (white in light
    # mode, near-black in dark mode) instead of a hardcoded white that goes ~1.9:1 on
    # the bright dark-mode teal. No raw `color:#fff` should remain in the stylesheet.
    assert "--on-accent:#ffffff" in SRC, "light-mode on-accent ink token removed"
    assert "--on-accent:#06211e" in SRC, "dark-mode on-accent ink token removed"
    assert "color:#fff" not in SRC and "color:white" not in SRC, \
        "hardcoded white-on-accent re-introduced (fails contrast in dark mode)"


def test_facets_keyboard_operable():
    # Non-<button> facets (word-cloud SVG text, stat bars, chips) must be focusable
    # buttons that activate on Enter/Space and expose an aria-pressed state.
    js = _script()
    assert 'el.setAttribute("role","button")' in js, "facets not given a button role"
    assert 'el.setAttribute("tabindex","0")' in js, "facets not made focusable"
    assert 'aria-pressed' in js, "facets missing aria-pressed state"
    assert 'e.key==="Enter"||e.key===" "' in js, "facets not activated by keyboard"


def test_filter_scrolls_sources_into_view():
    # Applying a filter from a facet high on the page scrolls the Sources list into
    # view, honouring prefers-reduced-motion.
    js = _script()
    assert "scrollToSources" in js, "scroll-into-view on filter removed"
    assert "prefers-reduced-motion:reduce" in js, "reduced-motion guard missing"


def test_focus_modal_dialog_semantics():
    # The record focus overlay is a labelled modal dialog with a focus trap and
    # focus return to the trigger.
    js = _script()
    assert 'role="dialog" aria-modal="true" aria-labelledby="ftitle"' in js, \
        "focus modal missing dialog semantics"
    assert "function trapFocus" in js, "focus trap removed from the modal"
    assert "focusReturnEl" in js, "focus-return-to-trigger removed from the modal"


def test_reduced_motion_global_guard():
    assert "@media (prefers-reduced-motion:reduce)" in SRC, "global reduced-motion guard removed"


def test_summarize_disabled_during_fetch():
    js = _script()
    assert 'runBtn.disabled=true' in js, "Summarize not disabled during fetch"
    assert 'runBtn.disabled=false' in js, "Summarize not re-enabled after fetch"


def test_nsev_dead_css_removed():
    # The old per-item severity badge was replaced by category drawers; its CSS is dead.
    assert ".nsev{" not in SRC and ".nsev.n" not in SRC, "dead .nsev severity-badge CSS still present"


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
