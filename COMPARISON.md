# OpenBioNews vs. a hosted paid news digest

OpenBioNews is a free, self-hosted alternative to paid "AI reads the news and
sends you a digest" services (readthrough.news and peers such as Bio News Agent,
Summate, Readless, and Prism).

> **A note on accuracy:** this comparison describes the *category* of hosted,
> subscription bio-news digests. Exact features and pricing of any single paid
> product change over time and should be confirmed on that product's own site;
> the right-hand column is the typical paid-hosted model, not a verified
> feature list of one vendor.

## At a glance

| | **OpenBioNews** (this project) | **Hosted paid digest** (typical) |
|---|---|---|
| **Price** | Free, MIT-licensed | Monthly / annual subscription |
| **Where it runs** | Your computer or server | The vendor's cloud |
| **Account required** | None | Yes (email/login) |
| **Your data & reading habits** | Stay on your machine | Held by the vendor |
| **LLM** | Bring your own — local Ollama, any OpenAI-compatible API, or none | Vendor-chosen, included in price |
| **Works offline / no LLM** | Yes (deterministic mode) | No |
| **Sources** | Any RSS/Atom feed; curated bio/regulatory/preprint bundles included; fully editable | Vendor-curated list; usually fixed |
| **De-dup across outlets** | Yes (title-token clustering) | Yes (often "by meaning") |
| **Importance ranking** | Yes (transparent, deterministic score) | Yes (often an LLM pick) |
| **"Why it matters" context** | Optional, on any LLM backend | Usually included |
| **Read-time estimate** | Yes | Common |
| **Email delivery** | Optional, your own SMTP | Yes (core feature) |
| **Output formats** | Markdown, HTML, plain text | Email + web, usually fixed |
| **Customization** | Total — it's your code and config | Whatever the settings expose |
| **Automation** | cron / Task Scheduler | Managed, automatic |
| **Open source / self-host** | Yes | No |
| **Maintenance** | You (update feeds, run it) | The vendor |

## Where the paid product is genuinely better

Be honest about the trade-offs — a subscription buys real convenience:

- **Zero setup.** Sign up and it just works; no Python, no cron, no SMTP.
- **Managed infrastructure & deliverability.** Someone else keeps feeds alive,
  handles email reputation, and fixes breakage.
- **Editorial quality.** Human curation or a tuned, expensive model may pick and
  phrase stories better than a small local model.
- **Polished apps.** Mobile/web reading experience, search, archives, accounts.
- **Proprietary sources or analysis** you may not be able to replicate from
  public RSS.

## Where OpenBioNews wins

- **Free and open.** No subscription, MIT-licensed, fork it freely.
- **Private.** In no-LLM or local-model mode, nothing leaves your machine.
- **Bring your own LLM — or none.** Use a free local model, a free API tier, or
  pure deterministic summaries.
- **Fully customizable.** Any feed, any topic, any output; change the code.
- **No account, no lock-in.** Your config and digests are plain files you own.
- **Runs anywhere.** Windows, macOS, Linux; pure Python standard library.

## Who should use which

- **Use a paid hosted digest** if you want a finished product with zero upkeep
  and are happy to pay and share your reading data.
- **Use OpenBioNews** if you want it free, private, self-hosted, and yours to
  bend to any topic or workflow — the point of this project.
