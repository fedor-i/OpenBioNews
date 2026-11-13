---
name: openbionews
description: Answer biopharma questions from official primary records — ClinicalTrials.gov, FDA (recalls, approvals, shortages, adverse events, labels), the Federal Register, PubMed and SEC EDGAR — using the OpenBioNews MCP tools, and cite every fact to its source record. Use when the user asks about a drug's or company's trials, FDA actions, safety signals, regulatory notices, recent literature or SEC filings, or wants a cross-agency briefing or watchlist update.
---

# OpenBioNews: cited answers from official biopharma records

The OpenBioNews MCP tools return official records, each with a `source.url` to the
record itself. Your job is to pick the right tool, call it well, and answer **only from
what comes back**, citing it. The tools invent nothing; don't add anything they didn't
return.

## Ground rules

1. **Cite every factual claim** with the record's `source.url` (and `source.id`, e.g. the
   NCT number, recall number, PMID or accession). No URL, no claim.
2. **Quote numbers from `facts`**, never from memory or inference: enrollment, dates,
   endpoints, reaction counts, classifications. If a number isn't in `facts`, say it
   isn't in the record.
3. **"No results" is an answer.** `status: "no_current_results"` comes with `query_used`
   and `as_of`, so report it as a dated finding: "No current FDA shortage for X as of
   2026-11-13 (openFDA)". Don't turn it into "there are none" without the date, and don't
   fill the gap from memory.
4. **Separate record from interpretation.** Give the cited facts first. Label any analysis
   of your own as such ("My read: …").
5. **Say what you didn't check.** Default windows are recent (often 90 days), and a page is
   capped. If `truncated` is true, say more exist, or page with `offset`.

## Pick the tool

| The user wants… | Tool | Key arguments |
|---|---|---|
| Trials for a drug, company or condition | `search_clinical_trials` | `query`, `status`, `phase`, `rank_by` |
| The trials that *matter* (pivotal, landmark) | `search_clinical_trials` | `rank_by="salience"` |
| Drug recalls | `search_fda_recalls` | `query` (product), `firm`, `classification` |
| New approvals / new indications | `search_fda_approvals` | `query`, `company`, `include_supplements` |
| Is X in shortage? | `search_fda_shortages` | `query`, `status="Current"` |
| Most-reported adverse reactions | `search_fda_adverse_events` | `query` (drug) |
| Approved indications, boxed warning | `search_fda_labeling` | `query` (drug) |
| FDA guidances, advisory committees, rules | `search_federal_register` | `query`, `recent_days` |
| Recent papers | `search_pubmed` | `query`, `recent_days` |
| A company's own SEC filings | `search_sec_filings` | `company` (name, ticker or CIK), `form` |
| Everything on a watchlist at once | `watchlist_digest` | `terms`, `sources`, `rank_by` |

For a broad "what's happening with X?" question, use `watchlist_digest` with `sources`
limited to what's relevant (e.g. `["trials", "approvals", "recalls"]`). It spends fewer
tokens than calling all nine sources.

## Call it well

- **One concept per query.** `query` is matched as one phrase, so `"semaglutide obesity"`
  only keeps records containing those words side by side. Search `"semaglutide"` and
  narrow with `status`, `phase` or a second call, or pass `require_match=false` and read
  each result's `match` yourself.
- **Choose the ranking for the question** (`rank_by`):
  - `"recency"` (default): what's new.
  - `"salience"`: what matters. For trials that means large, late-phase, completed trials
    with results, searched over about five years. Use it for "key trials", "landmark",
    "pivotal" or "most important" questions. For recalls it weights Class I highest.
  - `"relevance"`: best keyword match within a wider recent pool.
  - `"semantic"`: needs the optional `[ml]` extra; falls back to relevance with a
    `ranking_note` if it isn't installed.
- **Phases:** `phase="3"`, or `"2/3"` for both. Filtering happens in the registry query,
  so `limit` applies to matching trials.
- **Time windows:** widen `recent_days` for history (salience already widens trials).
  Use `since="YYYY-MM-DD"` for "what's new since …"; matching results get `is_new: true`.
- **Code names:** some landmark trials are registered under a development code
  (e.g. AZD9291 for osimertinib, MEDI8897 for nirsevimab). If an important trial seems
  missing, search the code name too.
- **Very common drugs** (e.g. pembrolizumab, with thousands of trials): add `phase`,
  `status` or a condition search, because the candidate pool may not reach every
  landmark trial.
- **SEC:** pass `company` to get only that registrant's own filings (`resolved_cik`
  confirms who). Pass `query` alone for full-text search across all filers.
- **Paging:** results are capped at `limit` (max 100). Use `offset` for the next page.
  `page_note` means you went past the end.

## Read the results

Each result has `title`, `date`, `status`, `facts`, `summary` and `source` (`id`, `name`,
`url`, `kind`, and sometimes `also` for e.g. a DOI). It may also carry:

- `match`: which query terms hit, and where. An empty `terms` list in PubMed results is
  normal, because PubMed matched on the abstract, which isn't returned.
- `relevance_score` (0–1) and the top-level `ranked_by`. If `ranking_note` is present,
  the ranking fell back to another mode; mention that if it matters.
- With `verbose=true`: `relevance_components` (why it ranked there), the full
  `citations` list and raw `meta`.

## Know the limits, and say them

- **FAERS counts are spontaneous reports**, not incidence, and don't show causation.
  Always say so when you quote them.
- **SEC results are filing pointers** (form, filer, date, accession), not extracted
  figures. For numbers, point to the filing; don't infer them.
- **Salience is a transparent heuristic**: an equal blend of enrollment, phase,
  results posted and maturity. It is not a judgement of clinical importance. Present it
  as "ranked by size, phase and maturity".
- **Coverage:** US agencies plus PubMed. There's no EMA, no conference abstracts and no
  press releases.

## Errors

- `error` containing `OPENBIONEWS_EDGAR_UA`: SEC needs a contact User-Agent. Tell the
  user to set that environment variable in the MCP server config (e.g.
  `"Their Name their@email.com"`). Don't report it as "no filings".
- `status: "entity_not_found"` (SEC): the name didn't resolve to a registrant. Try the
  ticker or the exact registered name. Private companies often have no SEC filings.
- `since must be YYYY-MM-DD`, or an unknown `sources` key: fix the argument and retry.
- Any other `error` from an agency: report the source as unavailable and answer from
  the sources that did respond. Never present a failed source as "no results".

## Example

**User:** "What are the key semaglutide trials, and is there a shortage right now?"

1. `search_clinical_trials(query="semaglutide", rank_by="salience", limit=7)`
2. `search_fda_shortages(query="semaglutide")`
3. Answer: list each trial with its name, phase, enrollment from `facts`, status, and its
   NCT link. Then give the shortage finding with its `as_of` date and source link, or the
   dated "no current shortage" result if that's what came back.
