# Architecture

OpenBioNews is a small, linear pipeline. Each stage is a plain function with no
hidden state, so it is easy to read, test, and extend.

## Data flow

```
config ─▶ fetch ─▶ filter ─▶ cluster ─▶ rank/limit ─▶ compose ─▶ render ─▶ write
```

## Modules

| Module | Responsibility |
| --- | --- |
| `openbionews/config.py` | Load/save/validate the JSON config; ship sensible defaults. |
| `openbionews/sources.py` | Curated topic bundles of RSS/Atom feeds. |
| `openbionews/fetch.py` | Download and parse feeds (stdlib RSS/Atom parser). Failures are collected, never fatal. |
| `openbionews/models.py` | `Item`, `Cluster`, `Digest` dataclasses. |
| `openbionews/pipeline.py` | Deterministic filtering, de-duplication, clustering, and importance ranking (`importance_score`). |
| `openbionews/llm/` | Pluggable summarizer backends (`none`, `openai`, `ollama`) behind one interface; optional "why it matters" prompt. |
| `openbionews/compose.py` | Ask the backend for a blurb per story; fall back to no-LLM on error. |
| `openbionews/render.py` | Render a `Digest` to Markdown / HTML / text (with read-time). |
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

## Adding an LLM backend

1. Create `openbionews/llm/mybackend.py` with a class extending
   `llm.base.Backend`, implementing `summarize(self, cluster) -> str` and
   (optionally) `available(self) -> tuple[bool, str]`.
2. Register it in `llm/__init__.py`'s `get_backend()`.
3. Offer it as a choice in `setup_wizard.py`.
