# Architecture

OpenBioNews is a small, linear pipeline. Each stage is a plain function with no
hidden state, so it is easy to read, test, and extend.

## Data flow

```
        ┌─ connectors (primary sources) ──┐
config ─┤                                 ├─▶ filter ─▶ cluster ─▶ rank/limit ─▶ compose ─▶ render ─▶ write / email
        └─ fetch (optional RSS/Atom) ─────┘
```

**Connectors** are the core: they read official primary records — trial
registries, regulators, filings, the literature — and attach a `Citation` to each
development, tracing it to its source document. The default config enables the
FDA connectors that need no watch list. Trade-press RSS/Atom feeds are secondary
and opt-in (off by default); when enabled, both streams merge into the same pipeline.

## Modules

| Module | Responsibility |
| --- | --- |
| `openbionews/config.py` | Load/save/validate the JSON config; ship sensible defaults. |
| `openbionews/sources.py` | Optional news-feed bundles (off by default), plus the therapeutic-area and thematic watch-list presets. |
| `openbionews/fetch.py` | Download and parse optional RSS/Atom feeds (stdlib parser). Failures are collected, never fatal. |
| `openbionews/connectors/` | Primary-source connectors (ClinicalTrials.gov; openFDA recalls / approvals / shortages / adverse events / labeling; Federal Register; PubMed; SEC EDGAR) that emit cited `Item`s from a watch list. |
| `openbionews/httputil.py` | Shared stdlib JSON-over-HTTP GET used by connectors. |
| `openbionews/cite.py` | Per-sentence source citation of digest text. |
| `openbionews/history.py` | Track seen items across runs → "what changed since last time". |
| `openbionews/mcp_server.py` | Model Context Protocol server exposing the connectors as ten tools (optional `mcp` extra): lean cited records with a `facts` block, provenance, `no_current_results` negatives, and deterministic `rank_by` ranking (`recency` / `relevance` / `salience` / `semantic`). |
| `openbionews/mlrank.py` | Optional semantic ranking (TF-IDF + LSA via scikit-learn, the `[ml]` extra), imported lazily; ranking falls back to lexical relevance without it. |
| `openbionews/models.py` | `Item`, `Cluster`, `Digest`, `Citation` dataclasses. |
| `openbionews/pipeline.py` | Deterministic filtering, de-duplication, clustering, and importance ranking (`importance_score`). |
| `openbionews/llm/` | Pluggable summarizer backends (`none`, `openai`, `ollama`) behind one interface; optional "why it matters" prompt. |
| `openbionews/compose.py` | Ask the backend for a blurb per story; fall back to no-LLM on error. |
| `openbionews/render.py` | Render a `Digest` to Markdown / HTML / text / RSS (with read-time). |
| `openbionews/mailer.py` | Optional SMTP email delivery (stdlib `smtplib`). |
| `openbionews/run.py` | Wire the stages together; write the file and/or email it. |
| `openbionews/setup_wizard.py` | Interactive onboarding → personalized config. |
| `openbionews/doctor.py` | Diagnose config, feed reachability, LLM connectivity. |
| `openbionews/cli.py` | Argument parsing and command dispatch. |

## Design choices

- **Deterministic core.** Grouping stories is done by title-token Jaccard
  similarity — no model required. The LLM is optional and only writes prose.
- **Zero required dependencies.** The whole core is standard library, so the
  tool installs and runs anywhere Python does. `feedparser` is an optional
  upgrade, not a requirement.
- **Graceful degradation.** A dead feed is skipped; a failed summary call falls
  back to the deterministic summary. A run always produces a digest.
- **One backend interface.** Adding a new LLM provider means writing one class
  with a `summarize(cluster)` method and registering it in `llm/__init__.py`.

## How correctness is checked

Three layers, because the failures that matter here are quiet ones — a search that
returns fewer or worse results without raising an error:

1. **Unit tests on saved payloads** (`tests/`) — fast, offline, run on every push
   across Linux/macOS/Windows. They pin parsing, filtering, paging and scoring.
2. **Ranking parity** (`tests/test_ranking_parity.py`) — the MCP server and the
   website each implement salience scoring; one set of expected values in
   `tests/fixtures/ranking_vectors.json` is checked against both, so they can't drift.
3. **Live checks** (`.github/workflows/live.yml`, daily and on release) — the
   contract checks (`tests/live/check_live.py`) call every tool against the real
   APIs and verify the fields we depend on are still filled in; the landmark
   benchmark (`benchmarks/run_landmarks.py`) measures salience Recall@7 over 43
   landmark trials in 10 therapeutic areas. A failed scheduled run opens an issue.

## Adding an LLM backend

1. Create `openbionews/llm/mybackend.py` with a class extending
   `llm.base.Backend`, implementing `summarize(self, cluster) -> str` and
   (optionally) `available(self) -> tuple[bool, str]`.
2. Register it in `llm/__init__.py`'s `get_backend()`.
3. Offer it as a choice in `setup_wizard.py`.

## Adding a primary-source connector

1. Create `openbionews/connectors/mysource.py` with a class extending
   `connectors.base.Connector`, implementing `fetch(self) -> list[Item]`
   (use `httputil.get_json`) and `available(self) -> tuple[bool, str]`. Set
   `age_exempt=True` and attach `Citation`s to each `Item`.
2. Register it in `connectors/__init__.py`'s `get_connectors()`.
3. Add its config block in `config.py` and a wizard step in `setup_wizard.py`.
4. Split parsing from fetching (a `parse_*` function) so it can be unit-tested
   with a fixture and no network.
5. If the upstream API takes a field allowlist (ClinicalTrials.gov's `fields`),
   request **every** leaf your parser reads — the API prunes the rest, and fixture
   tests won't notice (they ignore the allowlist). Add a test that pins the list.

Shipped connectors: `clinicaltrials`, `openfda` (drug recalls),
`openfda_approvals`, `openfda_shortages`, `openfda_events` (FAERS),
`openfda_labels`, `federalregister`, `pubmed` and `edgar` (SEC full-text search,
plus per-company filings via `data.sec.gov` submissions once a name/ticker is
resolved to its CIK). Running server-side, they set the `User-Agent` SEC requires and avoid
the browser CORS limits that constrain the hosted page.
