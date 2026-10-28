# Changelog

All notable changes to OpenBioNews are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.8.6] — 2026-10-28

A full revision pass over the MCP tools and the hosted page. Every fix below was
reproduced first and is pinned by a regression test that fails on 0.8.5.

### Fixed (MCP)
- **Keyword matching used raw substrings**, so a short term matched inside unrelated
  words ("ALS" in "trials" and "also"). Since `require_match` and every relevance
  score build on it, strays could pass the filter. Matching is now word-boundary and
  punctuation-insensitive: acronyms must match a whole word (plural "s" allowed),
  longer words may run on ("statin" → "statins"), and "GLP-1" / "glp 1" or
  "base-editing" / "base editing" compare equal.
- **Paging past the end reported `no_current_results`** — the "trustworthy negative" —
  even though results existed on earlier pages (as did `limit=0`). It's now returned
  only when the search truly matched nothing; past-the-end pages come back empty with
  a `page_note`.
- **`rank_by="salience"` did nothing without a query.** Salience is query-independent,
  so it now ranks even with no terms (e.g. the most serious recent recalls first).
- **`watchlist_digest(rank_by="salience")` still couldn't reach landmark trials** — it
  never enabled the enrollment-sorted candidate pass or the wide window that
  `search_clinical_trials` uses. It now does, and every digest block is capped at
  `limit_per_source` with an accurate `truncated` flag.
- **Unknown `watchlist_digest` source keys were silently ignored** (a typo returned zero
  blocks and no error). `sources` is now a typed enum in the MCP schema (rejected at
  the protocol boundary) and an unknown key is an explicit error in direct calls.
- **Oversized `limit`** could request more than ClinicalTrials.gov / openFDA allow per
  page (max 1000), failing the call upstream; fetches are now capped at 1000 and
  `limit` at 100 per page (`offset` clamped at 0).
- **A malformed `since`** silently filtered everything out (read as "no results"); it
  is now an error naming the expected `YYYY-MM-DD` format.
- **Combined phases** such as `phase="2/3"` filtered to Phase 2 only; they now mean
  Phase 2 OR Phase 3.
- Salience's `relevance_components` now lists only the four signals that feed the
  score (enrollment, phase, results-posted, maturity), not unweighted ones.

### Fixed (website)
- **Research mode corrupted Update mode's "new since your last visit" baseline**: the
  landmark trials it pulls from beyond the window were counted as new and written into
  the baseline (evicting real entries). Research mode now neither flags nor records
  "new", and its header says Research mode is active.

### Internal / docs
- Trial relevance reuses the shared match/recency helper (no duplicated maths); lint
  (pyflakes) is clean across the package and tests.
- ROADMAP marks shipped items (per-CIK SEC filings, PyPI, ranking) and lists the open
  MCP follow-ups; ARCHITECTURE documents `mlrank.py`, the ranking modes, and the
  "request every field your parser reads" lesson from 0.8.4.

## [0.8.5] — 2026-10-21

### Changed (MCP + website — pivotal phase weighting)
- **Phase 3 now outranks Phase 4** in the salience/importance weighting (`PHASE3` 1.0,
  `PHASE4` 0.8; previously `PHASE4` 1.0 > `PHASE3` 0.85). Phase 3 is the registrational
  pivotal trial — the landmark — while Phase 4 is post-marketing; the old order buried
  pivotal outcomes trials. With the enrollment-fields fix (0.8.4), independent
  landmark-recall validation puts salience at parity with a web agent, and this phase
  fix takes it to a perfect score on that set. Applied identically to the MCP scorer and
  the website's Update/Research ranking.

## [0.8.4] — 2026-10-21

### Fixed (MCP — salience/facts inputs were not actually fetched)
- The ClinicalTrials.gov connector requested `HasResults` but **not** `EnrollmentCount`,
  `StartDate`, `PrimaryCompletionDate` or `PrimaryOutcomeMeasure` — and ct.gov's `fields`
  param prunes everything else, so in real queries `facts.enrollment`/dates/endpoints came
  back empty and the salience **enrollment signal was always 0** (the mocks ignore
  `fields`, so tests never caught it). Added the missing leaf fields and a regression
  guard that keeps `FIELDS` in sync with what the parser reads. The 0.7.0 `facts` numbers
  and the 0.8.3 salience enrollment weight now work against the live API.

### Added (website — Insights "Update vs Research" mode)
- A mode toggle on the Insights tab. **Update** (default) is the windowed "what's new"
  digest, unchanged. **Research** ranks the Sources list by the same salience blend as the
  MCP tools (enrollment · phase · results-posted · maturity) and adds a wide-window,
  enrollment-sorted candidate pass, so landmark/pivotal trials surface instead of being
  cut by the recency window. `normTrial` now carries `enrollment` and `hasResults`.

## [0.8.3] — 2026-10-21

### Changed (MCP — salience weighting, validated against landmark recall)
A landmark-recall head-to-head (6 drugs, 18 verified landmark trials) showed the
0.8.2 salience weighting scored only ~0.39 Recall@7 — recency let recent Phase-4
studies crowd out pivotal Phase-3 / outcomes trials (e.g. it missed SELECT/SUSTAIN for
semaglutide). Reweighted to match a web agent's ~0.9:

- **Salience is now an equal blend of four structural signals** — enrollment, phase,
  results-posted, and **maturity** (a new signal: completed/with-results outranks
  just-recruiting). **Recency is dropped** from salience (it hurt importance ranking),
  and so is query match (the candidate pool is already query-filtered). Cross-validation
  showed tuned coefficients didn't beat the equal blend, so the simple blend ships.
- **Wider candidate pull** for salience (pool cap 250 → 500), so every landmark trial
  for a drug can enter before ranking.
- Documented guard: salience intentionally does **not** use a raw reference /
  "publication footprint" count — ct.gov's referencesModule mixes BACKGROUND (the
  investigators' bibliography) with RESULT/DERIVED (papers reporting the trial), and
  counting all of it overweights small investigator-initiated trials; a footprint signal,
  if ever added, must use RESULT+DERIVED only.

## [0.8.2] — 2026-10-21

### Fixed (MCP)
- **Salience can now reach landmark historical trials.** `rank_by="salience"` still
  only re-ranked the N most-recently-updated studies, so a large but older-updated
  landmark (e.g. a 17,000-patient Phase 3 last updated two years ago) never entered the
  pool. The ClinicalTrials.gov connector now adds a second candidate pass sorted by
  **enrollment** in salience mode (best-effort — if the API rejects the sort, salience
  still works off the recency pool), skips the recency cutoff, and returns the whole
  union for scoring rather than truncating by date. A landmark trial now enters and
  tops the salience ranking.
- **Unknown `rank_by` values are rejected, not silently ignored.** `rank_by` is now a
  typed enum (`recency`, `relevance`, `semantic`, `salience`) advertised in every
  tool's MCP input schema, so a typo or an unimplemented mode (e.g. `impact`) is
  rejected with a clear validation error instead of no-oping to the default.

### Docs
- Clarified that `salience` is the "what matters" ranker and `relevance` is keyword
  match (use `salience` for importance).

### Website
- Insights now retries transient openFDA 500s (429/5xx, with backoff) and collapses
  duplicate per-source error lines into one with a count.

## [0.8.1] — 2026-10-21

### Added / Fixed (MCP — `rank_by="salience"`, "what matters" vs "what's new")
`rank_by="relevance"` could not surface the trials that matter: it only re-ranked a
newest-first candidate page (so a landmark study outside the recency window never
entered the pool) and its score was match-dominated (a small keyword-dense trial could
outrank a large mature one). Fixed by splitting the intent into an explicit mode:

- **`rank_by="salience"`** (new) orders by weighted signals — for trials, enrollment
  and phase and results-posted and status dominate; keyword match barely counts — so a
  large, mature study outranks a small keyword-dense one. It pulls a **wide candidate
  pool** and, for trials, a **wide time window**, so a landmark older trial can compete
  instead of being cut by the recency cap. Recalls/approvals/shortages get a
  signal-weighted salience too; sources without a salience signal fall back to
  `relevance` with a `ranking_note`. Available on every search tool and
  `watchlist_digest`.
- `rank_by="recency"` (default, what's new) and `rank_by="relevance"` (lexical match)
  are unchanged; ranking modes now also pull a wider pool (100; salience 250) so a page
  isn't scored against its recency-local neighbours only. Results report `ranked_by`.

## [0.8.0] — 2026-10-21

### Added (MCP — relevance ranking across all search tools; issue #12 phase 1)
- **`relevance_score` + `rank_by` on every search tool and `watchlist_digest`.** Each
  result now carries a deterministic `relevance_score` (0–1). `rank_by="relevance"`
  orders by it (ranked over a wider recent candidate pool, so the top page is the most
  relevant rather than the most relevant within one recency page); `rank_by="recency"`
  (default) is unchanged. The per-signal breakdown is exposed as `relevance_components`
  under `verbose`, and `watchlist_digest` applies the ranking within each source block.
- The score blends lexical query match with recency plus a per-source signal: trials
  weight phase / enrollment / results-posted / status; recalls weight severity (Class I
  highest); approvals weight priority review; shortages weight current-vs-resolved;
  PubMed / Federal Register / SEC use match + recency.
- This is classical scoring (no LLM, no new dependencies): it only orders records
  that already cite themselves and invents nothing.

### Added (MCP — optional semantic ranking; issue #12 phase 2)
- **`rank_by="semantic"` + the optional `[ml]` extra.** Ranks by meaning rather than
  keywords using TF-IDF + Latent Semantic Analysis (TruncatedSVD) — classical ML, run
  locally, deterministic (pinned `random_state`), no LLM. `pip install
  "openbionews[ml]"` enables it; the core stays dependency-free. Without the extra,
  `rank_by="semantic"` falls back to lexical `relevance` and says so in a
  `ranking_note`. Every ranked result reports `ranked_by`. Semantic scoring blends
  LSA cosine similarity with recency and, like all ranking here, only orders records
  that already cite themselves — it invents nothing. A dedicated CI job installs the
  `[ml]` extra and exercises the ranker.

### Added (website Insights — relevance ranking; issue #12 phase 3)
- **The hosted Insights "Sources" list now ranks by the same multi-signal relevance.**
  It previously ordered by BM25 (lexical match) alone; it now blends that match with
  recency and a per-source signal — trial phase/status, recall severity (Class I
  highest), original-vs-supplemental approval, current shortage — mirroring the MCP
  scorer. Deterministic, no LLM, client-side; it only reorders records that already
  cite themselves. Verified in-browser (phase-3 over phase-1, Class I over Class III).

## [0.7.3] — 2026-10-20

### Fixed (MCP — `search_clinical_trials`)
- **Phase filter is now applied server-side.** It was filtered in the tool layer
  *after* ClinicalTrials.gov returned a recency-sorted, page-size-capped set, so a
  phase-3 search could come back nearly empty even when the registry held many
  matching studies. The phase now rides in the ct.gov query itself
  (`filter.advanced=AREA[Phase](PHASE3)`), so the recency/page limit applies to
  matching studies. Accepts "3" / "Phase 3" / "PHASE3" and multiple phases
  (`["2","3"]` → `AREA[Phase](PHASE2 OR PHASE3)`). (`status` was already server-side.)

## [0.7.2] — 2026-10-20

### Added / Changed (MCP — pre-ship hardening)
- **Keyword-stray filter for trials & PubMed.** `search_clinical_trials` and
  `search_pubmed` now drop results where the query term appears in no field
  (`require_match=true`, the default) — the loose-keyword strays upstream search
  leaks in (a different drug in a results list). Set `require_match=false` to opt out
  and self-filter via each result's `match`.
- **Actionable SEC User-Agent error.** A missing `OPENBIONEWS_EDGAR_UA` now yields a
  clear message naming the variable and the `"Name email"` format, instead of SEC's
  raw 403 HTML wall.
- **`serverInfo.version` is populated** (clients display it; it was blank).

### Docs
- MCP setup now warns that the desktop app does **not** inherit shell `PATH`, so the
  config must use an **absolute** `command` path (or `python3 -m openbionews mcp`);
  the EDGAR User-Agent is called out as required for SEC; and the "why it matters"
  LLM note carries a confabulation warning (use a capable model; it's labelled
  analysis, never a cited fact). Clarified that lean output always keeps the citation
  (`source.url`), `id`, and `date`.

## [0.7.1] — 2026-10-20

### Fixed (MCP — `search_sec_filings`)
- **`company` is now a real filer filter, and `query` is optional.** Previously both
  `query` and `company` were merged into the EDGAR full-text query, so `company` never
  restricted by filer and `own_filer_only` only ran when `company` was set — which you
  couldn't set alone because `query` was required. As a result a search for a company
  returned third-party filings that merely mention it (a fund's 13F-HR, an NPORT-P).
- **Entity mode resolves the subject to its CIK.** Give `company` (a name, ticker, or
  raw CIK; `query` optional) and the tool resolves it via SEC's registrant directory
  and returns only that registrant's *own* filings (data.sec.gov submissions feed),
  reporting the `resolved_cik`. An unresolvable name returns `status:"entity_not_found"`
  rather than silently falling back to a noisy full-text search. `own_filer_only=true`
  applies the same scoping to a bare `query`. A plain `query` (no entity) still does a
  document full-text search.

## [0.7.0] — 2026-10-20

### Changed / Added (MCP tools — optimized for LLM callers)
Head-to-head local-model testing showed the root cause of confabulation wasn't the
model — a dense 9B invented precise fake financials ("$15.8M net loss") because the
tool payload carried no numbers to anchor on. These changes make the tools leaner and
harder to hallucinate against.

- **Lean output by default.** Records now carry one `source: {id, name, url, kind}`
  object instead of three repeated links (`url` + `citation_url` + `citations[]`),
  plus a `facts` block that surfaces the structured values each connector already
  extracted. Pass `verbose=true` for the full payload. Collapses redundant tokens
  substantially on every call.
- **The numbers travel in `facts`.** ClinicalTrials.gov records now include
  `enrollment`, `start_date`, `primary_completion_date` and `primary_endpoints`;
  FAERS reaction counts, SEC form/filer/accession, approval/shortage fields all ride
  in `facts` so a downstream model cites them rather than inventing them.
- **A first-class empty result.** A successful-but-empty search returns
  `status: "no_current_results"` with `query_used` and `as_of`, so a negative (e.g.
  "not in shortage") is a citable fact, not an inference from a bare `0`.
- **Relevance signal + scope filters.** Each result carries `match: {terms, where}`
  for loose-keyword strays; `search_sec_filings` gains `own_filer_only` to drop
  third-party filings (a fund's 13F) that merely mention the company.
- **Monitoring + token-budgeted paging.** `since` (YYYY-MM-DD) filters to new records
  and flags each `is_new`; `limit`/`offset` page results with a `truncated` flag;
  `watchlist_digest` takes `sources=[...]` to query only the agencies needed.
- **Provenance + MCP annotations.** Every block carries `endpoint`, `retrieved_at`
  and `as_of`; every tool is registered with `readOnlyHint`/`idempotentHint` so agent
  frameworks can cache and parallelize calls.

## [0.6.1] — 2026-10-19

### Fixed
- **`mcp` extra no longer silently downgrades on Python 3.9.** The `mcp` SDK
  requires Python 3.10+, so on 3.9 `pip install "openbionews[mcp]"` used to
  backtrack past every release that declares the extra and silently install an
  ancient, MCP-less version. The extra now carries a `python_version >= '3.10'`
  marker, so on 3.9 it resolves to nothing and the current release installs; the
  server's import error, and the README, now state the 3.10+ requirement and
  recommend `pipx`/`uv` so the `openbionews` command lands on `PATH`.

## [0.6.0] — 2026-10-19

### Added
- **MCP server (optional `mcp` extra)**. `openbionews mcp` exposes the connectors as
  ten Model Context Protocol tools so any MCP client (Claude Desktop, Claude Code, …)
  can pull primary-source records with their citation URLs. The tool logic is
  standard-library only; a CI job installs the extra and verifies the server builds
  against the live SDK so an SDK API change can't break it silently.
- **Records-first Insights layout (hosted page)**. The analytic cards (emergent
  themes, stat bars, rising terms, word cloud, key phrases) now fold into one
  collapsed "Patterns & analysis" drawer that sits just above the source records, so
  the primary-source list reads first.

### Changed / Fixed (Insights)
- **Honest time series**. The records-over-time sparkline now bins into equal
  whole-day periods (target six, ≥7 days each) anchored so the last bucket ends today,
  replacing calendar-month bins whose partial current month spiked or dipped the last
  tick; windows under two weeks render no chart. Momentum ("recent vs earlier half")
  and rising terms are scoped to the selected window and split at its midpoint.
- **PubMed dates & relevance**. Records are dated by their electronic publication date
  (never a future print-issue date; undated if only a future date exists). Results are
  the most-relevant in the window (not just newest), raised from 40 to 200, with an
  honest "showing N of M matches" note when the match total is larger.
- **No reference data in the analytics**. FAERS/label "also tracked" aux records and
  PubMed journal / Federal Register agency names are kept out of the word cloud, YAKE!
  key phrases, BM25 ranking, k-means clustering, rising terms, "Top companies" and
  "Top therapeutic areas".
- **Accessibility**. Added a WCAG-contrast ink token for text on accent fills,
  keyboard-operable facets with `aria-pressed`, a labelled modal focus dialog, a
  reduced-motion guard, an `<h1>`, and dark-mode-visible sparkline markers.

### Added (earlier)
- **"Notable right now" is now organised into category drawers (hosted page)**. The
  flat severity-ranked list is replaced by collapsible `<details>` drawers, one per
  signal type — **trials halted** (terminated / withdrawn / suspended), **recalls**,
  **shortages**, **adverse events (FAERS)**, **approvals & label expansions**,
  **Federal Register**, and **publications (PubMed)** — each with a tone dot and a
  count. The alerting categories open by default, the informational ones start
  collapsed, each item stays cited to its source, and drawers cap at 10 with a
  "+N more in Sources" note. Terminated/withdrawn trials now get their own prominent
  category (previously mixed in); routine Phase-3 listings were dropped from Notable.
- **Insights digest now spans Federal Register + PubMed (hosted page)**. The beta
  summary (Insights) tab previously gathered only ClinicalTrials.gov, FDA recalls /
  approvals / shortages and SEC EDGAR. It now also pulls Federal Register documents
  and PubMed literature for the same window, so both feed the cross-agency record
  list, the "By source" breakdown, the word cloud, clustering and rising terms — and
  the coverage banner reflects the wider scope. FAERS adverse events and FDA labels
  are now **also tracked** in the digest too: counted in the "By source" breakdown and
  shown as cited cards tagged "also tracked", but kept out of the word cloud /
  clustering / rising terms (their aggregate counts and undated reference text would
  distort the analytics).
- **Custom historic date range (hosted page)**. Every time control — the Insights
  period selector and each data tab's recency dropdown (trials, recalls, approvals,
  SEC) — keeps its "last N days" presets and adds a **"Specific range…"** option that
  reveals from/to date pickers, so you can pull e.g. all 2019 recalls or run Insights
  over any historic span. The explicit range is threaded into each source's native
  date filter (ClinicalTrials.gov `RANGE`, openFDA `report_date`, SEC `startdt/enddt`)
  and persists in shareable links.
- **Record focused view (hosted page)**. Every record now has a **"🔍 related"**
  button that opens an overlay pulling in connected records across sources, keyed
  off the record's main entity: publications (PubMed), clinical trials, FDA recalls
  / shortages / labels / adverse events, and Federal Register documents — each
  linked to its primary source. Groups load independently, so one slow or
  unreachable source never blocks the rest, and a source that can't be reached
  in-browser degrades to a per-group note. This answers "show me everything related
  to this item" — e.g. a trial's publications, or whether a drug in the news also
  has a recall.
- **PubMed — new source**. A new connector (NCBI E-utilities: `esearch` →
  `esummary`) surfaces biomedical literature for a watch term, each cited to its
  PubMed record and DOI. Added to the CLI connector registry and the MCP server
  (`search_pubmed` + the cross-agency digest, now nine sources). Powers the
  publications strand of the record focused view on the hosted page.
- **FDA drug labeling — new source**. A new connector and a hosted-page tab surface
  the current FDA structured product label (SPL) for a drug — its approved
  indications and any boxed warning. Added across the CLI connector registry, the
  MCP server (`search_fda_labeling` + the cross-agency digest) and the web app.
- **Federal Register — new source**. A new connector and a hosted-page tab surface
  FDA regulatory documents — guidances, advisory-committee (adcomm) meeting
  notices, and proposed / final rules — the primary records behind a regulatory
  calendar. Added across the CLI connector registry, the MCP server
  (`search_federal_register` + the cross-agency digest) and the web app. FDA-scoped
  by default, with an `all_agencies` option.
- **FDA adverse events (FAERS) — new source**. A new connector and a hosted-page
  tab summarise, per drug, the most-reported adverse reactions from the FDA
  Adverse Event Reporting System, using openFDA's server-side `count`
  aggregation (the high-signal view, not a flood of single-patient reports).
  Counts are spontaneous reports, not incidence rates, and the card/summary say
  so. Added across the CLI connector registry, the MCP server
  (`search_fda_adverse_events` + the cross-agency digest) and the web app.
- **Therapeutic-area presets expand to condition bundles (hosted page)**. The
  Oncology / Cardiometabolic / Neurology / Immunology / Rare-disease / Infectious
  seed buttons each now expand to a bundle of representative conditions (mirroring
  `sources.py`) instead of a single disease, so "Immunology" searches RA +
  psoriasis + IBD + lupus, not only rheumatoid arthritis.
- **Full study descriptions in Insights (hosted page)**. Insights source cards
  now show the complete ClinicalTrials.gov detailed description (behind "… more"),
  while the analytics still key off the brief summary so clustering and the word
  cloud stay fast.
- **Spell-out tooltips on Insights stat bars (hosted page)**. Truncated company /
  therapeutic-area / source labels spell out in full on hover or keyboard focus.
- **"… more" to expand a summary (hosted page)**. Study and record summaries were
  previewed at a fixed length and could cut off mid-thought. Each card now shows a
  brief, few-line preview with a **"… more"** link that expands it to the complete
  text from the record (and "show less" to collapse). The link appears only when a
  summary actually overflows, so short ones are untouched. The full cited text is
  always in the DOM and the link only toggles a CSS clamp — expanding never
  re-fetches. Works on every tab (trials, recalls, approvals, shortages, SEC) and
  the Insights source list.

## [0.5.0] — 2026-10-09

### Changed
- **Preset chips now feed the watchlist (hosted page)**. The per-tab topic /
  area / company example chips used to fill one tab's fields; they duplicated the
  watchlist but without its cross-agency reach, persistence, topic expansion or
  "what's new." They're replaced by a single **"Quick add"** seed row on the
  watchlist bar (shown while the list is empty) — one click adds that
  area/topic/company to the universal watchlist, so topics get proper expansion
  and every tab updates at once. The genuinely tab-specific filter chips (recall
  Class, shortage Status, SEC form types) stay in their panels.

### Added
- **MCP server — call the primary sources from an AI assistant**. A new
  `openbionews mcp` command runs a [Model Context Protocol](https://modelcontextprotocol.io)
  server (stdio) that exposes the connectors as tools: `search_clinical_trials`,
  `search_fda_recalls`, `search_fda_approvals`, `search_fda_shortages`,
  `search_sec_filings`, and `watchlist_digest` (all five agencies at once). This
  inverts the usual relationship — the core still has no LLM and invents nothing,
  but any MCP client (Claude Desktop, Claude Code, …) can call these tools to pull
  **primary-source** records, each returned as JSON with the exact `citation_url`
  it traces to. The `mcp` dependency is optional (`pip install "openbionews[mcp]"`);
  the core stays dependency-free. Supports both the current SDK (`mcp` ≥ 2) and the
  1.x line. Tool logic is standard-library and unit-tested without the `mcp` package.
- **Insights (beta) — a deterministic, no-LLM cross-agency digest (hosted page)**.
  A new **📊 Insights** tab gathers a broad recent sample of the primary-source
  records for your watchlist (or a typed subject) across all five agencies at once
  and summarizes them with *classical, state-of-the-art text-mining* — no LLM, so
  nothing is invented and every figure is counted from the records, which are
  listed beneath (each cited to its source):
  - **TextRank** (Mihalcea & Tarau, 2004) ranks terms by centrality in a word
    co-occurrence graph — term salience, sized (not raw count) in the word map.
  - **Packed word cloud** — a deterministic Wordle-style spiral layout (largest
    term first, each spiralling out until it clears the placed words; ~a quarter
    set vertical; text measured with canvas `measureText`), rendered as pure SVG.
    Terms are **sized by TextRank salience** and **colored by their k-means cluster**
    (the same clustering as the themes card, validated 3-hue palette), so terms
    used in similar contexts share a colour and the colours match the theme chips.
    The legend labels each colour by its top member terms. Click a term to filter.
  - **YAKE!** (Campos et al., 2020) extracts the **key phrases** (unsupervised,
    statistical; casing + position + frequency + dispersion + context).
  - **BM25** (Robertson / Spärck Jones) ranks the source records by relevance to
    the subject.
  - **Emergent themes** — **spherical k-means on PPMI co-occurrence vectors**:
    each salient term becomes a vector of what it appears beside, and cosine
    k-means groups terms used in similar contexts (deterministic farthest-point
    seeding + fixed Lloyd iterations). Records are assigned to the cluster their
    tokens most belong to; each theme shows its top terms + record count. The same
    clustering colours the word cloud, so theme chips and cloud colours agree. This
    replaced label propagation, which collapsed a dense term graph into one theme.
    **The theme count now fits the data** — instead of always forcing three
    clusters, K is chosen by **mean cosine silhouette** over K = 2…6, so a broad
    watchlist spreads while a genuinely single-topic one stays **one theme**: a
    silhouette floor gates the split, so no artificial boundary is drawn through a
    coherent corpus. (The floor is tuned so a large, vocabulary-dense pull —
    hundreds of records sharing generic clinical/AI language — still separates into
    its real sub-themes instead of collapsing to one, which also keeps the word
    cloud multi-coloured and the Grouped-by-cluster toggle available.) Farthest-point seeding breaks ties by *total* distance to the
    seed set, so seeds land one-per-island instead of doubling up and leaving a
    real theme unseeded. A cluster needs **≥2 records** to earn a theme chip (a lone
    record is already in Sources — no one-item "themes"), and the word cloud keeps
    three distinct hues with any further themes drawn muted so the palette stays
    readable.
  - **Rising terms** — deterministic novelty/burst detection: terms whose share in
    the highlighted window materially exceeds (or are entirely new vs.) the older
    baseline, so "what's new" names the *themes that are accelerating*, not just a
    raw record count. **Guard rails** keep a short window from turning every
    single-mention term into "new": both halves need ≥4 documents to compare, a
    term needs ≥2 recent mentions (real support, not a one-off), and the lift must
    clear 1.5×. The recent/older split is computed over **only the records we can
    date** — undated records are neither "recent" nor "old", so they no longer leak
    into the baseline and mask genuine momentum. When there isn't enough dated
    history to compute momentum the card says so explicitly, instead of silently
    disappearing (which looked like a bug).
  - **Notable right now** — a deterministic, rule-based scan surfacing the
    high-signal events analysts look for first — Class I/II recalls, Phase 3
    (pivotal) trials, terminated/withdrawn/suspended trials, original (new) FDA
    approvals, **substantive supplemental approvals** and active drug shortages —
    ordered by severity, each shown with a cited excerpt from the record. Only
    *label/efficacy* supplements count as notable (routine CMC/manufacturing churn
    is filtered out via `submission_class_code`), deduped to the most recent per
    application and ranked below a Class II recall, so one blockbuster's label
    history can't flood the card or bury a real recall.
  - **Coverage-boundary banner** — the digest now states plainly what it does and
    does not see (ClinicalTrials.gov · FDA recalls / approvals / shortages · SEC
    EDGAR — **US regulators only**; no EMA / ex-US, no press releases, no
    literature), so an empty result reads as "not in these sources" rather than
    "nothing happened."
  - **Plural/singular grouping**: a lightweight deterministic singulariser folds
    plural forms into one term (formulations→formulation, antibodies→antibody,
    cells→cell), so the cloud, clustering and ranking count them together instead
    of showing both. Stopwords are matched on the original form too, so plural
    stop-entries never leak back in as a singular.
  - **Noun-ish term filtering**: the word cloud and key phrases drop common verbs,
    adverbs, adjectives and clinical-trial boilerplate (a deterministic heuristic
    stoplist — no POS model) **plus a dynamic max-document-frequency filter** that
    removes any term appearing in >55% of the records (corpus-specific
    boilerplate), so the terms read as concepts rather than trial jargon — keeping
    dual-use domain nouns (target, screen, guide, support,
    vector), so the terms read as concepts rather than sentence fragments.
  - **Time window drives the pull, fully paginated** — the window selector
    (7 / 30 / 90 days, 6 months, 1 year) now scopes what is *fetched*, and each
    source paginates through the whole window (ClinicalTrials.gov by page token,
    openFDA by skip, SEC by offset) until the reported total is reached — no fixed
    first-page cap, so different topics over different periods each get their
    complete set. Analysis runs over every record; the source list renders the top
    150 by relevance to keep the page light, but a filter (a theme, company, term
    or "find similar") pulls in any matching record that ranked below that cap on
    demand, so filtering is never silently limited to the shown top-150. "New since
    your last visit" is still highlighted via the per-watchlist seen-state.
  - **Cross-agency company canonicalisation** — the same firm is written
    differently per agency ("Recursion Pharmaceuticals" as a trial sponsor vs
    "RECURSION PHARMACEUTICALS INC (RXRX)" as an SEC filer), which used to split
    one company across two "Top companies" rows and inflate "who's most active".
    Companies are now canonicalised (drop a trailing ticker, lowercase, strip the
    corporate suffix + punctuation) before counting, so one firm is counted once
    and its row links to its records across every agency.
  - **Honest "new since your last visit"** — Insights now keeps its *own*
    seen-state, keyed by the subject it actually pulled, instead of borrowing the
    per-tab watchlist views' partial scroll state. First look makes no "new" claim;
    a later visit diffs against exactly what Insights showed you before.
  - Counted **stats** — records by source, top companies, top therapeutic areas,
    trial phases — plus a pure-SVG **monthly-volume sparkline** whose partial edge
    months (the window's first month and the current, not-yet-finished month) are
    **prorated to a full-month rate**, so the trend line isn't dragged down at the
    ends; interior full months stay as the raw count.
  - **Numbered citations across every list**: each card (and each Notable event)
    now carries a sequential reference number — markers run 1..N by position, and
    a card's inline markers match its source line — instead of every marker
    rendering as "1".
  - **Click-to-drill-in**: clicking a theme, company, therapeutic area, word-cloud
    term or key phrase filters the Sources list to the matching records (with a
    clear-filter banner). All client-side, zero-dependency, shareable by URL.
  - **Group the Sources by cluster** — a *Ranked / Grouped by cluster* toggle on
    the Sources list. "Grouped" sections the references under their emergent-theme
    cluster (largest first) with an "Other" bucket for unclustered records, as a
    clustered way to read the list instead of one flat BM25 ranking. It reuses the
    same record→cluster map that drives the Themes card and is purely a re-layout
    of the existing cards, so citations, the "find similar" chips and all filtering
    keep working; the choice is remembered per viewer. (Hidden when there aren't at
    least two clusters to group by.)
  - **"Find similar" on every reference** — each source card carries a *find
    similar* control that narrows the Sources list to that record and its nearest
    neighbours. Similarity is deterministic and LLM-free: each record is a TF-IDF
    bag-of-terms vector (IDF computed over this corpus, so shared boilerplate
    counts for little and distinctive terms drive the match) compared by cosine,
    over the same filtered tokens as the rest of the digest. Only genuinely close
    records are offered (a cosine floor), so an off-topic record surfaces nothing
    rather than a spurious "match", and the neighbour set leads with the anchor so
    it stays in view. Duplicates are collapsed — a content-duplicate of the anchor
    (the same item arriving twice under different ids) is never offered as its own
    match, and duplicate records fold to a single representative — so every entry
    in "similar" is a distinct record. Cosine is computed over the whole pulled
    corpus, not just the rendered references, and a neighbour that ranked below the
    source-list cap is pulled into the list when you click, so "find similar" isn't
    limited to the top records on screen.
- **Build-your-own topics (hosted page)** — a "+ New topic" builder on the
  watchlist bar: name a topic and give it a bundle of terms and companies (e.g.
  "My ADC competitors" → Seagen, Daiichi Sankyo, antibody-drug conjugate). Saved
  in `localStorage`, it then behaves exactly like a built-in topic — add it once
  and every tab searches all of its terms, matched by the topic's name anywhere
  you'd type a watch term. Custom topics appear as quick-add chips (editable and
  deletable), expand to the exact terms you listed (no acronym filtering — your
  choices are respected), and need no backend or LLM.
- **Sort control on every tab (hosted page)** — a single *Most recent / Most
  relevant* selector in the results bar, applied to the active tab and to the
  watchlist. Server-side where the API supports it (ClinicalTrials.gov
  `@relevance`; openFDA recalls by `report_date`; "relevant" omits the date sort
  so openFDA/EDGAR rank by match score), and client-side by date for sources with
  no usable date-sort parameter (openFDA drug shortages, Drugs@FDA approvals, SEC
  EDGAR). The choice is shareable in the URL (`?sort=`) and
  remembered in `localStorage`. (Replaces the trials-only sort dropdown.)
- **Cross-tab watchlist (hosted page)** — a persistent bar at the top where you
  add companies, drugs or topics once; every tab then shows that agency's news
  for them. Each term is matched across the right fields per source (company *or*
  drug *or* topic): ClinicalTrials.gov, FDA recalls, Drugs@FDA approvals, FDA
  shortages and SEC EDGAR. Persists in `localStorage`, is shareable via the URL
  (`?w=…`), and works with Load-more and auto-refresh. A manual search in any tab
  temporarily overrides the watchlist for that tab.
  - **Name-variant expansion** so one list matches across agencies that record a
    company differently (SEC's "BRISTOL MYERS SQUIBB CO" vs ClinicalTrials.gov's
    "Bristol-Myers Squibb" vs "BMS"). Each term is widened with its corporate
    suffix stripped (`Moderna Inc` also matches `Moderna`) plus a small
    high-precision alias map; the extra variants are OR'd in, so expansion only
    adds true matches and never drops your own term.
  - **Topic expansion** — a short topic word like "AI" is useless as a raw
    keyword (it matches the token "AI" inside product names such as the
    "Sureclick AI" auto-injector, not the concept). When a watch term names a
    known topic (AI in drug discovery, NAM, gene & cell therapy, CRISPR, mRNA,
    ADCs, radiopharma, GLP-1/obesity, psychedelics, longevity) it now searches
    the concept's meaningful phrases plus its lead companies instead of the bare
    token — so the topic returns real cross-agency results and the device-name
    collisions disappear. Ultra-short acronyms (≤3 chars, e.g. "ADC", "AAV") are
    dropped from the expansion for the same reason. Topic chips are tinted and
    carry a tooltip showing what they expand to. Mirrors `sources.THEMES`.
  - **"What's new since last visit"** — the page remembers which items you have
    already seen for a watchlist (per source, in `localStorage`) and, on your next
    visit, flags only the genuinely new ones: a `NEW` badge on each new card, a
    count badge on the agency tab, and a total in the watchlist bar. Deterministic,
    client-side, no backend — the free counterpart to a paid alert feed. Resets
    cleanly when you change the list; your own term is the baseline, so a brand-new
    watchlist flags nothing until something actually changes.

## [0.4.0]

### Added
- **LLM as a labelled interpretation layer** — with per-sentence citations now
  the factual body, an enabled LLM (Ollama / OpenAI-compatible) no longer writes
  the facts; it adds only a clearly-marked *"💡 Why it matters (AI analysis)"*
  note beneath the deterministic cited claims (turn on `output.why_it_matters`).
  The facts stay verbatim and cited — nothing to hallucinate — while the model
  supplies interpretation you can tell apart at a glance. A failed note is dropped
  with a warning; the cited body always renders. Runs across Markdown/HTML/text/RSS.
- **Change detection between runs** — OpenBioNews now remembers each item's
  salient state (by NCT id, recall number, EDGAR accession) and flags what
  *changed* on the next run: a trial moved to Terminated, results posted, a recall
  reclassified. Changed stories are boosted in ranking and badged (`🔔 Status:
  Recruiting → Terminated`). Deterministic — a literal state comparison, **no LLM**.
  New `openbionews/history.py`; state lives in `digest/state.json` (configurable).
- **Thematic groups** (`sources.THEMES`) — one-tap watch-list seeds that cut
  across diseases by *modality / approach / company cohort*: **AI in drug
  discovery**, **New Approach Methodologies (NAM)**, gene & cell therapy, CRISPR,
  mRNA, ADCs, radiopharmaceuticals, GLP-1/obesity, psychedelics, longevity. Each
  seeds search terms and a lead-sponsor cohort. Wizard multi-select + web chips.
- **Stackable web filters** — chips on the hosted page now *add* to a field
  instead of replacing it, and multi-value fields become a ClinicalTrials.gov
  `OR` query, so you can watch several conditions / companies / themes at once.
- **Per-sentence citations** — every sentence of a story's brief is bound to the
  primary-source record it was lifted from, rendered as a numbered `[n]` / `<sup>`
  marker with a keyed source list beneath. Fully deterministic: the text is
  verbatim from the cited record, so there is nothing to hallucinate and **no LLM
  is involved**. Applies across every output (Markdown, HTML, text, RSS) and the
  hosted web page. New `openbionews/cite.py`; a `Claim` model on each cluster.
- Continuous integration (GitHub Actions) running the test suite on Linux, macOS
  and Windows across Python 3.9–3.12, plus an install/CLI smoke test.
- Community health files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue and pull
  request templates.
- **Offline mixed demo**: `openbionews run --demo` now builds a digest from
  bundled samples covering trade-press RSS *and* all three primary sources
  (ClinicalTrials.gov, FDA recalls, SEC filings), each with a source citation —
  a network-free preview of the real output.
- **RSS feed output** (`--format rss`, or `output.format: rss`): writes a valid
  RSS 2.0 feed (`digest/latest.xml`) you can subscribe to in any reader, with a
  source citation in every item. Standard-library only. (Closes #2.)
- **openFDA drug-approvals connector** (`connectors.openfda_approvals`): recent
  Drugs@FDA approvals — original and supplemental (new indication) — cited to
  the Drugs@FDA page. Wizard toggle, doctor check, and demo coverage included.
  (Closes #1.)
- **Therapeutic-area presets** (oncology, cardiometabolic, rare disease,
  neurology, immunology, infectious disease): one-tap watch-list seeding in the
  setup wizard and matching chips on the hosted page. (Closes #4.)
- **openFDA drug-shortages connector** (`connectors.openfda_shortages`): current
  (or resolved) shortages by drug/company, cited to the FDA Drug Shortages
  database — completing the FDA trio (recalls + approvals + shortages).
- **Hosted page parity**: the web app now has five tabs — Clinical trials, FDA
  recalls, **FDA approvals**, **FDA shortages**, and SEC filings — matching the
  CLI's source coverage, all client-side with shareable links.

### Fixed
- Windows: the setup wizard and `doctor` could raise `UnicodeEncodeError` when
  invoked directly (bypassing the CLI entry point) because stdout defaulted to a
  legacy code page. The UTF-8 guard is now shared and applied at every entry
  point (`openbionews/termio.py`). Caught by the new cross-platform CI.
- De-duplication now keys on an item's stable id (NCT id, recall number, EDGAR
  accession) before its link. Previously, sources whose links differ only by a
  query string (e.g. openFDA recall records) could be wrongly collapsed into one.

## [0.3.0]

### Added
- **openFDA drug-recalls connector** — enforcement reports filtered by
  firm/product/reason, classification and report-date recency; cites the FDA
  record.
- **SEC EDGAR connector** — full-text search of filings by company/drug/term,
  form type and filed-within recency; cites the filing document and sets the
  contact `User-Agent` SEC requires. Runs server-side, avoiding browser CORS.
- Hosted web page gained an **SEC filings tab** (with a graceful fallback to
  SEC's own EDGAR search when a browser blocks the request) and an **FDA drug
  recalls tab**, plus shareable filter links.
- Useful filters based on how biopharma teams monitor: trial recency +
  industry-sponsored-only; recall report-date recency + voluntary/mandated.

## [0.2.0]

### Added
- **Primary-source model**: `connectors/` package and a **ClinicalTrials.gov**
  connector with a shared watch list and per-story source citations.
- Hosted, zero-install web page (`docs/`) for filtering ClinicalTrials.gov.

## [0.1.0]

### Added
- Initial release: RSS/Atom digest with cross-outlet de-dup, importance ranking
  and read-time; no-LLM / Ollama / OpenAI-compatible summaries; optional SMTP
  email; onboarding wizard; `doctor` diagnostics; Markdown/HTML/text output.
  Pure standard library, cross-platform, MIT-licensed.
