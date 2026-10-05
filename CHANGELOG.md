# Changelog

All notable changes to OpenBioNews are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
