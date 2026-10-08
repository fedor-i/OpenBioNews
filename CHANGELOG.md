# Changelog

All notable changes to OpenBioNews are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
    coherent corpus. Farthest-point seeding breaks ties by *total* distance to the
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
    150 by relevance to keep the page light. "New since your last visit" is still
    highlighted via the per-watchlist seen-state.
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
