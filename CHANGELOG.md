# Changelog

All notable changes to OpenBioNews are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Continuous integration (GitHub Actions) running the test suite on Linux, macOS
  and Windows across Python 3.9–3.12, plus an install/CLI smoke test.
- Community health files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue and pull
  request templates.

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
