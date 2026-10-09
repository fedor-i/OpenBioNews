# OpenBioNews

[![CI](https://github.com/fedor-i/OpenBioNews/actions/workflows/ci.yml/badge.svg)](https://github.com/fedor-i/OpenBioNews/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Zero dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](pyproject.toml)

**A free, self-hosted news digest you run on your own computer.**

OpenBioNews gathers stories from the sources you choose, groups the same story
reported by different outlets into one entry, ranks them by importance, and
writes a clean daily digest — as Markdown, a web page, or plain text, and
optionally straight to your inbox. It ships tuned for **biotech and life
sciences**, but you can point it at any topic.

- 🆓 **Free and open** (MIT). No account, no subscription, no server to rent.
- 🔬 **Primary sources, cited to the sentence.** Track **ClinicalTrials.gov**,
  **FDA** (recalls, approvals, shortages) and **SEC EDGAR** by company, drug or
  condition — and *every sentence* of every brief carries a numbered citation back
  to the exact source record. It's deterministic (verbatim from the record), so
  there's nothing to hallucinate — **no LLM required**. Plus any RSS/Atom feed.
- 🔔 **Tells you what *changed*.** Remembers each trial/filing/record between runs
  and surfaces the diff — a trial gone to *Terminated*, results posted, a recall
  reclassified — so you read the change, not the same snapshot twice.
- 🎯 **Watch by theme, not just disease.** One-tap groups seed your watch list:
  therapeutic areas *and* thematic cohorts like **AI in drug discovery**, **NAM**,
  gene/cell therapy, CRISPR, mRNA, ADCs, radiopharma, GLP-1/obesity. Stack several.
- 🖥️ **Runs everywhere.** Windows, macOS, and Linux — pure Python, no build step.
- 🔌 **Bring your own LLM — or none.** The cited facts are always deterministic;
  an optional local model (Ollama) or OpenAI-compatible API only adds a clearly
  labelled *"Why it matters"* interpretation on top — so the AI never touches the
  record, and there's nothing to hallucinate into it. Runs fully offline.
- 🧩 **Zero dependencies.** The core runs on the Python standard library. If you
  have Python, you can run it.
- 🥇 **Curated, not a firehose.** Stories are de-duplicated across outlets and
  ranked by importance, with a read-time estimate.
- 📬 **Optional email delivery.** Have it mail you the digest every morning via
  any SMTP server.
- 🔒 **Private.** Your feeds and reading habits stay on your machine. With the
  local or no-LLM modes, nothing is sent anywhere.
- 🪄 **One-minute onboarding.** `openbionews setup` walks you through it and
  writes a config customized to you.

> Gathering news into a post is deterministic — grouping and de-duplicating
> stories needs no AI. An LLM is optional and only used to polish the one-line
> summaries, so even a small local model is plenty.

---

## Quick start

You need **Python 3.9 or newer**. Check with `python3 --version` (on Windows,
`py --version`).

```bash
# 1. Get the code
git clone https://github.com/fedor-i/OpenBioNews.git
cd OpenBioNews

# 2. Try it right now, offline, with bundled sample data
python3 -m openbionews run --demo

# 3. Create your own personalized digest (interactive, ~1 minute)
python3 -m openbionews setup

# 4. Build today's digest
python3 -m openbionews run
```

That's it — your digest is written to the `digest/` folder as
`digest-YYYY-MM-DD.md` (plus a `latest.md` you can always point to).

### Works on Windows, macOS, and Linux

The tool is pure Python and platform-independent. Command names differ slightly:

| | macOS / Linux | Windows |
| --- | --- | --- |
| Run a module | `python3 -m openbionews …` | `py -m openbionews …` |
| Set an env var (this shell) | `export KEY=value` | `set KEY=value` (cmd) · `$env:KEY="value"` (PowerShell) |
| Schedule it | `cron` | Task Scheduler |

After `pip install .`, the `openbionews` command works the same on every
platform. Output is written as UTF-8 everywhere.

### Optional: install it as a command

```bash
pip install .
openbionews setup      # now available as a plain command
openbionews run
```

---

## Onboarding: `openbionews setup`

The setup wizard is the heart of OpenBioNews. It asks a handful of questions —
each with a sensible default you can accept by pressing **Enter** — and writes a
config file customized to you:

1. **Name your digest** (e.g. *"My Morning Bio Brief"*).
2. **Pick topics.** Choose from built-in bundles (Biotech & Pharma, Regulatory
   (FDA/EMA), Preprints (bioRxiv/medRxiv), Life Science & Research, Health,
   Science, Tech, World) or add your own RSS URLs.
3. **Track primary sources.** Optionally watch **ClinicalTrials.gov**, **FDA**
   recalls/approvals, and **SEC** filings by company, condition, or drug —
   official developments, cited to their source record. Start from a
   **therapeutic-area preset** (oncology, cardiometabolic, rare disease,
   neurology, immunology, infectious disease) to seed the watch list, then
   tweak (see below).
4. **Focus it.** Optionally keep only stories mentioning certain keywords, or
   always drop others.
5. **Choose how summaries are written** — no LLM, local Ollama, or an
   OpenAI-compatible API.
6. **Pick an output format** — Markdown, HTML, text, or an **RSS feed** you can
   subscribe to in any reader.

The result is `openbionews.config.json` in the current folder. Re-run `setup`
any time to change it, or edit the file directly (see
[`config.example.json`](config.example.json)).

---

## Choosing an LLM (or not)

OpenBioNews works three ways. You choose during setup; you can switch any time.

### 1. No LLM (default) — free, instant, offline
Summaries are the article's own opening sentences. No model, no network, no
setup. Great for a fast, private digest.

### 2. Local model via Ollama — free and private
Install [Ollama](https://ollama.com), pull a small model, and OpenBioNews talks
to it on your machine. Nothing leaves your computer.

```bash
ollama pull llama3.2        # or qwen2.5, phi3, gemma2 — small models are fine
# choose "Local model via Ollama" in `openbionews setup`
```

### 3. Any OpenAI-compatible API
Works with OpenAI, OpenRouter, Groq, Together, LM Studio, llama.cpp's server,
vLLM, and more. During setup, give the base URL, model name, and the **name of
an environment variable** that holds your API key. The key is read from the
environment and is **never written to the config file**.

```bash
export OPENAI_API_KEY=sk-...      # or whatever variable you named
openbionews run
```

If a summary call ever fails (rate limit, network blip), that story quietly
falls back to the no-LLM summary — the run never aborts.

---

## Primary sources — traced to the document

Beyond RSS (which is *secondary* trade press), OpenBioNews can read **official
primary records** and trace every development back to its source document.

Three connectors are built in. You keep **one watch list** (companies,
conditions, drugs, terms) and switch on whichever official sources you want:

- **ClinicalTrials.gov** — trial developments (registration, status, phase),
  cited to the NCT record.
- **openFDA drug recalls** — enforcement reports (reason, Class I/II/III,
  status), cited to the FDA record.
- **openFDA drug approvals** — Drugs@FDA approvals, original and supplemental
  (new indication), cited to the Drugs@FDA page.
- **openFDA drug shortages** — current/resolved shortages (reason, status,
  category), cited to the FDA Drug Shortages database.
- **SEC EDGAR** — filings (8-K, 10-K, S-1, 424B, 13D/G, DEF 14A, Form 4…), cited
  to the filing document. SEC asks for a contact User-Agent — set your email in
  `connectors.edgar.user_agent`.

```jsonc
"watchlist": {
  "sponsors": ["Moderna", "Vertex Pharmaceuticals"],
  "conditions": ["cystic fibrosis"],
  "interventions": ["mRNA-1345"],
  "terms": []
},
"connectors": {
  "clinicaltrials":    { "enabled": true, "recent_days": 30 },
  "openfda":           { "enabled": true, "recent_days": 30 },
  "openfda_approvals": { "enabled": true, "recent_days": 90 },
  "openfda_shortages": { "enabled": true, "recent_days": 60, "statuses": ["Current"] },
  "edgar":             { "enabled": true, "recent_days": 30, "forms": ["8-K"],
                         "user_agent": "Your Name your@email.com" }
}
```

The setup wizard builds this for you, and `openbionews doctor` verifies each
source. Every story renders with a tag and a source line:

```
### Study of DrugX in Advanced Solid Tumors
*Recruiting · Phase 2 · Acme Bio · ClinicalTrials.gov · 20 Sep*
A phase 2 study evaluating DrugX…
↳ Source: ClinicalTrials.gov NCT01234567
```

No API keys are required. Because the connectors run on your machine, they can
set the `User-Agent` SEC requires and are not subject to the browser CORS limits
that constrain the hosted web page — this is the reliable path for SEC data.

---

## Hosted web version — filter in your browser, no install

For people who just want to **click and filter**, there's a single-page web app
in [`docs/index.html`](docs/index.html) with two tabs:

- **Clinical trials** — filter ClinicalTrials.gov by company, condition, drug,
  status, phase, **recency** ("updated within N days"), and
  **industry-sponsored only**.
- **FDA drug recalls** — filter openFDA enforcement reports by firm, product,
  reason, classification (Class I/II/III), status, **report-date recency**, and
  **voluntary vs. FDA-mandated**.
- **FDA drug approvals** — Drugs@FDA approvals (original + supplemental) by
  company or drug, within a chosen window.
- **FDA drug shortages** — current/resolved shortages by drug or company.
- **SEC filings** — full-text search SEC EDGAR by company/ticker/keyword,
  **filing type** (8-K, 10-K, S-1, 424B, 13D/G, DEF 14A, Form 4…), and
  **filed-within** recency; each result links to the filing document. (SEC does
  not reliably allow in-browser cross-origin requests, so when a visitor's
  browser is blocked, this tab falls back to opening the same search on SEC's
  official EDGAR site with the filters applied.)

Both query the source **live in the browser**, show a link to each source
record, and support **shareable links** (copy a link that reproduces the exact
filtered view). No server, no backend, no tracking.

**Host it free on GitHub Pages:**

1. Repo → **Settings → Pages → Build and deployment**.
2. **Source: GitHub Actions** (the included workflow deploys `docs/`), *or*
   *Deploy from a branch* → **`main`** / **`/docs`**.
3. Your page goes live at `https://fedor-i.github.io/OpenBioNews/`.

Point a custom domain at it in the same settings page if you like. Because it's
static and calls the public APIs directly, it costs nothing to run and scales to
any number of visitors.

---

## Use it from an AI assistant (MCP)

The core has no LLM and invents nothing — but any assistant that speaks the
[Model Context Protocol](https://modelcontextprotocol.io) (Claude Desktop, Claude
Code, …) can call OpenBioNews as a tool to pull **primary-source** records, each
returned with the exact URL it traces to. The AI gets grounded, citable facts; it
never sees our prose.

```bash
pip install "openbionews[mcp]"   # the 'mcp' extra; the core stays dependency-free
openbionews mcp                  # speaks MCP over stdio
```

Tools exposed: `search_clinical_trials`, `search_fda_recalls`,
`search_fda_approvals`, `search_fda_shortages`, `search_sec_filings`, and
`watchlist_digest` (all five agencies at once). Each returns JSON records with a
`citation_url`.

Register it with Claude Desktop (or Claude Code) — add to your MCP config
(`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "openbionews": {
      "command": "openbionews",
      "args": ["mcp"],
      "env": { "OPENBIONEWS_EDGAR_UA": "Your Name your@email.com" }
    }
  }
}
```

`OPENBIONEWS_EDGAR_UA` is optional — SEC asks full-text-search callers to identify
themselves with a contact; set it to your email to keep EDGAR happy. Then ask your
assistant things like *"any Class I drug recalls for Moderna in the last 90 days?"*
and it will call the tool and answer from the cited records.

---

## Commands

| Command | What it does |
| --- | --- |
| `openbionews setup` | Interactive onboarding; writes your config. |
| `openbionews mcp` | Run the MCP server so an AI can call the primary-source connectors. |
| `openbionews run` | Build today's digest and write it to `digest/`. |
| `openbionews run --demo` | Build a digest offline from bundled sample data. |
| `openbionews run --stdout` | Print the digest instead of writing a file. |
| `openbionews run --format html` | Override the output format for one run. |
| `openbionews run --no-summaries` | Headlines and links only. |
| `openbionews run --email` | Also email the digest (uses your email config). |
| `openbionews doctor` | Check your config, feeds, LLM, and email. |
| `openbionews sources` | List the built-in topic bundles and their feeds. |

Use `-c path/to/config.json` to use a config file somewhere other than the
current directory (or set `OPENBIONEWS_CONFIG`).

---

## Run it every morning (automation)

OpenBioNews is a plain command, so any scheduler works.

**macOS / Linux (cron)** — build a digest every weekday at 7am:

```cron
0 7 * * 1-5  cd /path/to/OpenBioNews && /usr/bin/python3 -m openbionews run
```

**Windows (Task Scheduler)** — create a Basic Task that runs
`python -m openbionews run` in the project folder on your schedule.

Point your reader, a static-site folder, or an email script at
`digest/latest.<ext>`. With `format: rss` (or `openbionews run --format rss`),
that's `digest/latest.xml` — a standard RSS feed you can subscribe to in any
feed reader, so a scheduled run keeps your reader up to date automatically.

---

## Email delivery (optional)

Have OpenBioNews mail you the digest every morning. Enable it during
`openbionews setup`, or set the `email` block in your config. It works with any
SMTP server (your own, Gmail with an app password, Fastmail, a work relay…).

```jsonc
"email": {
  "enabled": true,
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "use_tls": true,
  "username": "you@gmail.com",
  "password_env": "OPENBIONEWS_SMTP_PASSWORD",  // password read from this env var
  "from_addr": "you@gmail.com",
  "to_addrs": ["you@gmail.com"]
}
```

Set the password in your environment (never in the file) and run:

```bash
export OPENBIONEWS_SMTP_PASSWORD=your-app-password   # Windows: set / $env:
openbionews run --email
```

The email is sent as both a formatted HTML version and a plain-text fallback.

---

## Curation & "why it matters"

OpenBioNews doesn't just dump every headline. Stories are:

1. **De-duplicated** across outlets (the same story from five sites becomes one
   entry that lists all five).
2. **Ranked by importance** — a transparent, deterministic score combining how
   many outlets carried a story, how fresh it is, and whether the headline
   contains high-signal words (approval, acquires, phase, recall…).
3. **Capped** to the top `max_items` (and `max_per_topic`), so you get a
   focused read with a **read-time estimate** in the header.

If you use an LLM backend, turn on **"why it matters"** in setup to add a short
significance note under each summary, generated locally or with your own key.

---

## How it works

```
feeds ─▶ fetch ─▶ filter ─▶ cluster ─▶ rank ─▶ summarize ─▶ render ─▶ digest
        (RSS/Atom) (age &   (group the  (biggest  (LLM or   (md/html/
                    keywords) same story  first)   no-LLM)   text)
                              across
                              outlets)
```

Everything except the optional summary step is **deterministic**: stories are
grouped by how much their headlines overlap (Jaccard similarity of title
tokens), so results are reproducible and need no AI. See
[`ARCHITECTURE.md`](ARCHITECTURE.md) for a module-by-module tour.

---

## Customizing sources

Run `openbionews sources` to see the built-in bundles. To add your own, either
choose *"Add your own RSS feed"* during setup, or edit the `feeds` list in your
config:

```json
{
  "feeds": [
    { "name": "My Favorite Blog", "url": "https://example.com/feed.xml", "topic": "biotech" }
  ]
}
```

Any RSS 2.0 or Atom feed works. Run `openbionews doctor` to confirm a new feed
is reachable.

---

## Privacy

- **No-LLM and Ollama modes send nothing off your machine.** OpenBioNews only
  fetches the feeds you list.
- **API mode** sends article titles and feed-provided descriptions to the
  endpoint you configured, only to write summaries. Your API key stays in your
  environment, never in the config file.
- No telemetry, ever.

---

## Requirements

- Python 3.9+ (standard library only for the core).
- Optional: [`feedparser`](https://pypi.org/project/feedparser/) for wider feed
  compatibility (`pip install .[feeds]`).
- Optional: [Ollama](https://ollama.com) for a free local model.

---

## Contributing

Contributions of every size are welcome — a typo fix, a new feed, or a whole new
primary-source connector. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md), see
where things are headed in [`ROADMAP.md`](ROADMAP.md), and check the
[good first issues](https://github.com/fedor-i/OpenBioNews/issues?q=is%3Aopen+label%3A%22good+first+issue%22).

The whole test suite runs with no dependencies:

```bash
python3 tests/test_pipeline.py
```

CI runs it on Linux, macOS and Windows across Python 3.9–3.12 on every pull
request. Releases publish to PyPI automatically ([`RELEASING.md`](RELEASING.md)).

## License

[MIT](LICENSE). Free to use, modify, and redistribute. This is an independent,
community-oriented, open-source tool.
