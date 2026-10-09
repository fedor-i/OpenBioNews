# Changelog

All notable changes to OpenBioNews are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
