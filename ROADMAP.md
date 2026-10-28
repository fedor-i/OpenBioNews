# Roadmap

OpenBioNews aims to be the free, self-hosted way to turn official primary
sources and feeds into a clean, cited daily brief. This is a living list —
[open an issue](https://github.com/fedor-i/OpenBioNews/issues) to propose or
claim something.

## Current focus: stabilise 0.8.x
Most 0.8.x patch releases fixed results that were quietly wrong rather than
adding features. Until the daily live checks and the landmark benchmark have been
green for a few weeks, releases are **correctness-only** — no new tools, sources
or ranking modes. Feature ideas are still welcome as issues.

- [x] Daily **live API contract checks** for every MCP tool (`tests/live/check_live.py`).
- [x] **Landmark-trial benchmark** in the repo — 20 drugs, 43 trials, 10 therapeutic areas;
      salience Recall@7 reported daily and on every release (`benchmarks/`).
- [x] **One ranking spec for Python and the website** — shared test cases both must pass
      (`tests/fixtures/ranking_vectors.json`).
- [ ] Set a recall floor in `benchmarks/landmarks.json` once a baseline is established.
- [ ] Align the two remaining differences: the approvals signal and Update-mode relevance.

## Primary sources (highest value)
- [x] **openFDA drug approvals** (Drugs@FDA) — new + supplemental approvals.
- [x] **openFDA drug shortages** — current/resolved shortages.
- [x] **SEC EDGAR via `data.sec.gov`** submissions per company (CIK) — the MCP
      `search_sec_filings` entity mode resolves a name/ticker to its CIK and returns
      only that registrant's own filings.
- [ ] **SEC fallback for ticker-less filers** (EDGAR entity search when a name isn't
      in the ticker directory) — [#11](https://github.com/fedor-i/OpenBioNews/issues/11).
- [ ] **EMA** and other non-US regulators.
- [ ] **bioRxiv / medRxiv** preprints as a first-class connector (today they are
      RSS bundles).

## Delivery & output
- [x] **Private RSS/Atom output** — publish the digest as a feed file (`format: rss` → `latest.xml`).
- [ ] **Slack / Teams** incoming-webhook output.
- [ ] A tiny **local web view** served from the latest digest.

## Curation
- [x] **Change detection between runs** — flag what changed (trial Terminated,
      results posted, recall reclassified), deterministically (no LLM).
- [x] **Per-sentence citations** — each sentence of a brief bound to the source
      record it was lifted from, deterministically (no LLM).
- [x] **Therapeutic-area presets** (oncology, cardiometabolic, rare disease,
      neuro, immunology, infectious) as one-tap watch-list seeds.
- [x] **Thematic groups** (AI, NAM, gene/cell, CRISPR, mRNA, ADC, radiopharma,
      GLP-1, psychedelics, longevity) seeding terms + company cohorts.
- [x] **Relevance & importance ranking** — every MCP search tool takes `rank_by`
      (`recency` / `relevance` / `salience` / `semantic`); `salience` ranks trials by
      enrollment · phase · results-posted · maturity, validated against landmark-trial
      recall. The website's Insights tab has a matching Update / Research toggle.
- [x] **Semantic ranking** via the optional `[ml]` extra (TF-IDF + LSA, local).
- [ ] **Per-source trust weights** to bias ranking.
- [ ] **Semantic de-duplication** using local embeddings (optional extra).
- [ ] Optional **claim ↔ source verification** pass when an LLM is enabled.

## MCP tools (open follow-ups)
- [ ] Per-item **`changed_fields`** deltas over a `since` cursor — [#8](https://github.com/fedor-i/OpenBioNews/issues/8).
- [ ] Optional **`fields=`** allowlist for minimal, still-cited payloads — [#9](https://github.com/fedor-i/OpenBioNews/issues/9).
- [ ] **Verbatim SEC filing excerpt** in `facts` (quote, never generated) — [#10](https://github.com/fedor-i/OpenBioNews/issues/10).

## Project
- [x] Cross-platform CI (Linux/macOS/Windows).
- [x] PyPI release workflow (Trusted Publishing).
- [x] Published on PyPI — `pip install openbionews` (MCP server: `openbionews[mcp]`).
- [ ] More default feeds and periodic dead-feed sweeps.

## Non-goals
- No telemetry or analytics, ever.
- No required cloud service or account.
- No heavyweight dependencies in the core.
