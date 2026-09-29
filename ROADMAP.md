# Roadmap

OpenBioNews aims to be the free, self-hosted way to turn official primary
sources and feeds into a clean, cited daily brief. This is a living list —
[open an issue](https://github.com/fedor-i/OpenBioNews/issues) to propose or
claim something.

## Primary sources (highest value)
- [ ] **openFDA drug approvals** (Drugs@FDA) — new approvals as developments.
- [ ] **openFDA drug shortages** — current/resolved shortages.
- [ ] **SEC EDGAR via `data.sec.gov`** submissions per company (CIK) as an
      alternative to full-text search, for precise per-company filing feeds.
- [ ] **EMA** and other non-US regulators.
- [ ] **bioRxiv / medRxiv** preprints as a first-class connector (today they are
      RSS bundles).

## Delivery & output
- [ ] **Private RSS/Atom output** — publish the digest as a feed file.
- [ ] **Slack / Teams** incoming-webhook output.
- [ ] A tiny **local web view** served from the latest digest.

## Curation
- [ ] **Therapeutic-area presets** (oncology, cardiometabolic, rare disease,
      neuro, immunology) as one-tap watch-list bundles.
- [ ] **Per-source trust weights** to bias ranking.
- [ ] **Semantic de-duplication** using local embeddings (optional extra).
- [ ] Optional **claim ↔ source verification** pass when an LLM is enabled.

## Project
- [x] Cross-platform CI (Linux/macOS/Windows).
- [x] PyPI release workflow (Trusted Publishing).
- [ ] First PyPI release so `pip install openbionews` works.
- [ ] More default feeds and periodic dead-feed sweeps.

## Non-goals
- No telemetry or analytics, ever.
- No required cloud service or account.
- No heavyweight dependencies in the core.
