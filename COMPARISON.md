# OpenBioNews vs. readthrough.news

readthrough.news (by JAMN Ventures, LLC) is the paid product this project is a
free response to. This page compares them **honestly**, including where they
differ in kind — not just in price.

## What readthrough actually is

> "Every FDA, SEC, and trial development, traced to its source."

readthrough is a **primary-source** biotech intelligence feed. It reads **SEC
EDGAR, the FDA, and ClinicalTrials.gov** as they update, writes an original
summary of each development, and **links every sentence to the document it came
from**. It deliberately excludes secondary media:

> "No trade press. No wire copy. Just the record, on the companies you watch."
> "If a claim is not in a public document, it is not in a readthrough story."

Reported scale: ~2,208 listed biopharma companies · ~14,172 primary documents ·
3 regulators, polled around the clock.

**How it works:** (1) **Watch** companies, drugs, and targets (or start from
curated lists — big pharma, oncology, cardiometabolic, rare disease); (2)
**Read** — each new filing/approval/recall/trial change becomes a short original
story, every claim cited, each story auto-checked against its sources before
publishing; (3) **Get it where you work** — web feed, morning email digest,
private RSS, Slack/Teams, and full-text search.

**Sources:** SEC EDGAR (8-K, 10-K, 10-Q, S-1, 424B, Form D, 13D/G, DEF 14A);
FDA (Drugs@FDA approvals, enforcement/recalls, shortages, press releases,
What's New for drugs & biologics); ClinicalTrials.gov.
**Polling:** EDGAR every ~10 min in market hours (hourly otherwise); FDA press /
What's New every ~30 min; Drugs@FDA, recalls, shortages, trials daily.
**Writing:** an LLM writes each story from the source with a citation on every
factual sentence; an automated pass verifies each claim; unverifiable sentences
are dropped and unverifiable stories publish as a short notice linking to the
source; no human pre-review; corrections shown on the story.
**Delivery:** web, email digest, private RSS, Slack/Teams, search, a read API
(JSON) and an **MCP server** for AI assistants.
**Price:** $29 / seat / month or $300 / seat / year; 14-day free trial, no card;
enterprise domain sign-in available. Explicitly **not investment advice**.

## Honest positioning: they are different in kind

**OpenBioNews today is a trade-press RSS digest** — it aggregates STAT,
FierceBiotech, Endpoints, etc. That is precisely the "trade press / wire copy"
readthrough refuses. So OpenBioNews is **not currently a drop-in replacement**;
it's a free, general news-digest tool that happens to default to bio outlets.

To become a true free readthrough, OpenBioNews would need to switch from
secondary feeds to **primary sources with citations** (see roadmap below).

## Feature-by-feature

| Capability | readthrough.news | OpenBioNews today |
|---|---|---|
| Price | $29/seat/mo, $300/seat/yr | Free, MIT |
| Hosting / account | Vendor cloud, account required | Self-hosted, no account |
| Primary sources (FDA/SEC/trials) | ✅ core | ❌ (trade-press RSS instead) |
| Per-sentence source citations | ✅ | ❌ (links to the article) |
| Automated fact-check vs. source | ✅ | ❌ |
| Watch lists (company/drug/target) | ✅ | ❌ (topic bundles + keywords) |
| Company/drug entity profiles | ✅ | ❌ |
| De-dup across sources | ✅ | ✅ |
| Importance ranking / read-time | — / — | ✅ / ✅ |
| Original LLM summaries | ✅ (required) | ✅ (optional; or no-LLM) |
| "Why it matters" | implicit | ✅ optional |
| Email digest | ✅ | ✅ (your SMTP) |
| Private RSS output | ✅ | ⚠️ writes files; no RSS yet |
| Slack / Teams | ✅ | ❌ (roadmap) |
| Full-text search | ✅ | ❌ |
| Read API + MCP server | ✅ | ❌ (roadmap) |
| Bring-your-own / no LLM | ❌ | ✅ |
| Runs offline | ❌ | ✅ (no-LLM mode) |
| Open source | ❌ | ✅ |

## Where each wins

**readthrough** — authoritative primary-source provenance, per-claim citations
and verification, entity/watch-list model, managed infra, Slack/Teams/API/MCP,
zero setup. Worth the subscription for regulated/IR/investor workflows.

**OpenBioNews** — free, private, self-hosted, bring-your-own-LLM (or none),
fully customizable, open source, runs anywhere and offline.

## Roadmap to actually replace readthrough (free)

1. **Primary-source connectors** (the defining change):
   - **ClinicalTrials.gov** REST API (v2) — study changes by sponsor/condition.
   - **openFDA / Drugs@FDA / enforcement (recalls) / drug shortages** + FDA press RSS.
   - **SEC EDGAR** full-text search + company filings JSON (8-K, S-1, 424B, Form D…).
2. **Watch lists** of companies/drugs/tickers instead of (or alongside) topics.
3. **Citations** — link each summary sentence to its source document.
4. **A lightweight verification pass** (claim ↔ source) when an LLM is used.
5. **Private RSS output** and **Slack/Teams webhooks**.
6. Optional **read API / MCP server** so AI assistants can query the record.

Items 5–6 are small; items 1–4 are the real work and would make OpenBioNews a
genuine free alternative rather than a general news digest.

---

_Product facts above are from readthrough.news as viewed by the user in
Sep 2026 and may change; verify on the vendor's site._
