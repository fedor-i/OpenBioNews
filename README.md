# OpenBioNews

**A free, self-hosted news digest you run on your own computer.**

OpenBioNews gathers stories from the sources you choose, groups the same story
reported by different outlets into one entry, ranks them by importance, and
writes a clean daily digest — as Markdown, a web page, or plain text, and
optionally straight to your inbox. It ships tuned for **biotech and life
sciences**, but you can point it at any topic.

- 🆓 **Free and open** (MIT). No account, no subscription, no server to rent.
- 🖥️ **Runs everywhere.** Windows, macOS, and Linux — pure Python, no build step.
- 🔌 **Bring your own LLM — or none.** Works with a local model (Ollama), any
  OpenAI-compatible API, or with *no LLM at all* (it uses each article's own
  lead sentences).
- 🧩 **Zero dependencies.** The core runs on the Python standard library. If you
  have Python, you can run it.
- 🥇 **Curated, not a firehose.** Stories are de-duplicated across outlets and
  ranked by importance, with a read-time estimate — like the paid digests, but
  yours.
- 📬 **Optional email delivery.** Have it mail you the digest every morning via
  any SMTP server.
- 🔒 **Private.** Your feeds and reading habits stay on your machine. With the
  local or no-LLM modes, nothing is sent anywhere.
- 🪄 **One-minute onboarding.** `openbionews setup` walks you through it and
  writes a config customized to you.

> Gathering news into a post is deterministic — grouping and de-duplicating
> stories needs no AI. An LLM is optional and only used to polish the one-line
> summaries, so even a small local model is plenty.

**New here?** See [COMPARISON.md](COMPARISON.md) for how this free tool stacks
up against paid hosted digests.

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
3. **Focus it.** Optionally keep only stories mentioning certain keywords, or
   always drop others.
4. **Choose how summaries are written** — no LLM, local Ollama, or an
   OpenAI-compatible API.
5. **Pick an output format** — Markdown, HTML, or text.

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

## Commands

| Command | What it does |
| --- | --- |
| `openbionews setup` | Interactive onboarding; writes your config. |
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
`digest/latest.<ext>`.

---

## Email delivery (optional)

Have OpenBioNews mail you the digest — the self-hosted equivalent of a paid
newsletter landing in your inbox. Enable it during `openbionews setup`, or set
the `email` block in your config. It works with any SMTP server (your own,
Gmail with an app password, Fastmail, a work relay…).

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
significance note under each summary — the kind of editorial context paid
digests charge for, generated locally or with your own key.

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

## Ideas borrowed from paid digests (and what's next)

Paid news-digest services (readthrough.news and peers like Bio News Agent,
Summate, Readless, Prism) share a common playbook. OpenBioNews already brings
the core of it to a free, self-hosted tool — see **[COMPARISON.md](COMPARISON.md)**
for the full free-vs-paid breakdown:

| Paid-tier idea | In OpenBioNews |
| --- | --- |
| Curated "top N" instead of a firehose | ✅ importance ranking + `max_items` cap |
| "5-minute read" framing | ✅ read-time estimate in the header |
| De-dup the same story across outlets | ✅ cross-outlet clustering |
| "Why it matters" context | ✅ optional, on any LLM backend |
| Delivered to your inbox | ✅ optional SMTP email |
| Broad curated bio sources | ✅ outlets + FDA/EMA + bioRxiv/medRxiv bundles |
| Daily automation | ✅ cron / Task Scheduler |

Natural next steps a contributor could add:

- **Semantic de-dup** (group by meaning, not just shared title words) using
  local embeddings.
- **Per-source trust weights** to bias ranking toward outlets you trust.
- **A tiny local web view / static site** built from `latest.html`.
- **More input types** (YouTube channels, podcasts, preprint categories).
- **LLM-picked "editor's top 5"** as an optional ranking pass.

PRs welcome.

## License

[MIT](LICENSE). Free to use, modify, and redistribute. This is an independent,
community-oriented tool, not affiliated with any paid service.
