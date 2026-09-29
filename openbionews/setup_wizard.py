"""Interactive onboarding: turn defaults into a user's personalized config.

This is the ``openbionews setup`` command. It walks a new user through picking
topics, focus keywords, an LLM backend and an output format, then writes a
ready-to-run config file. Everything has a sensible default, so pressing Enter
through the whole thing produces a working life-sciences digest.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import config as config_mod
from . import sources
from .termio import force_utf8_output

# ---- small prompt helpers ---------------------------------------------------

RULE = "─" * 60


def _in(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled.")
        raise SystemExit(1)


def ask_text(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = _in(f"{question}{suffix}: ").strip()
    return answer or default


def _csv(text: str) -> list[str]:
    """Split a comma-separated answer into a clean list."""
    return [part.strip() for part in text.split(",") if part.strip()]


def ask_yes_no(question: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    answer = _in(f"{question} [{hint}]: ").strip().lower()
    if not answer:
        return default
    return answer.startswith("y")


def ask_choice(question: str, options: list[tuple[str, str]], default_key: str) -> str:
    """Single choice. ``options`` is a list of (key, label)."""
    print(f"\n{question}")
    for i, (key, label) in enumerate(options, 1):
        marker = " (default)" if key == default_key else ""
        print(f"  {i}. {label}{marker}")
    raw = _in("Choose a number: ").strip()
    if not raw:
        return default_key
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx][0]
    except ValueError:
        pass
    print("  (not recognized — using default)")
    return default_key


def ask_multi(question: str, options: list[tuple[str, str]], default_keys: list[str]) -> list[str]:
    """Multiple choice by comma-separated numbers."""
    print(f"\n{question}")
    for i, (key, label) in enumerate(options, 1):
        marker = " *" if key in default_keys else ""
        print(f"  {i}. {label}{marker}")
    print("  (* = pre-selected. Enter numbers separated by commas, or press Enter to keep the defaults.)")
    raw = _in("Your picks: ").strip()
    if not raw:
        return list(default_keys)
    chosen: list[str] = []
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        try:
            idx = int(part) - 1
            if 0 <= idx < len(options):
                key = options[idx][0]
                if key not in chosen:
                    chosen.append(key)
        except ValueError:
            continue
    return chosen or list(default_keys)


# ---- the wizard -------------------------------------------------------------

def run_wizard(path: Path | None = None, existing: dict | None = None) -> dict:
    """Run the interactive wizard and return the assembled config dict."""
    force_utf8_output()  # safe Unicode output even when called directly (Windows)
    if not sys.stdin.isatty():
        cfg = existing or config_mod.default_config()
        saved_path = config_mod.save_config(cfg, path)
        print("No interactive terminal detected — wrote the default configuration.")
        print(f"Config written to: {saved_path}")
        print("Edit it directly, or run `openbionews setup` in a real terminal to customize.")
        return cfg

    cfg = existing or config_mod.default_config()

    print(RULE)
    print("  OpenBioNews — setup")
    print("  A free, self-hosted news digest, customized to you.")
    print(RULE)
    print("Press Enter to accept the default shown in [brackets] at any step.\n")

    # 1. Identity
    cfg["profile"]["title"] = ask_text(
        "What should your digest be called?",
        cfg["profile"].get("title", "Daily Bio Brief"),
    )
    cfg["profile"]["intro"] = ask_text(
        "A one-line subtitle (optional)",
        cfg["profile"].get("intro", ""),
    )

    # 2. Topics / sources
    bundle_options = [(k, f"{v['label']} — {v['description']}") for k, v in sources.BUNDLES.items()]
    chosen_bundles = ask_multi(
        "Which topics should your digest cover?",
        bundle_options,
        cfg["profile"].get("bundles", sources.DEFAULT_BUNDLES),
    )
    cfg["profile"]["bundles"] = chosen_bundles
    cfg["feeds"] = sources.bundle_feeds(chosen_bundles)
    total_feeds = len(cfg["feeds"])
    print(f"  → {total_feeds} source feed(s) selected.")

    if ask_yes_no("Add your own RSS/Atom feed URL now?", default=False):
        while True:
            url = ask_text("Feed URL (blank to finish)", "")
            if not url:
                break
            name = ask_text("A short name for it", url.split("/")[2] if "//" in url else url)
            cfg["feeds"].append({"name": name, "url": url, "topic": chosen_bundles[0] if chosen_bundles else "custom"})
            print(f"  → added {name}")

    # 2b. Primary sources (official records, traced to their documents)
    print("\nPrimary sources read official records — trial registries, regulators, "
          "SEC filings — instead of trade press, and cite the source document.")
    conns = cfg.setdefault("connectors", {})
    ct = conns.setdefault("clinicaltrials", {})
    fda = conns.setdefault("openfda", {})
    edg = conns.setdefault("edgar", {})
    already = any(c.get("enabled") for c in (ct, fda, edg))
    if ask_yes_no("Track official primary sources (trials, FDA recalls, SEC filings)?",
                  default=already):
        wl = cfg.setdefault("watchlist", {})
        print("Build a watch list (comma-separated; leave blank to skip a line):")
        wl["sponsors"] = _csv(ask_text("  Companies / sponsors",
                                        ", ".join(wl.get("sponsors", []))))
        wl["conditions"] = _csv(ask_text("  Conditions / indications",
                                         ", ".join(wl.get("conditions", []))))
        wl["interventions"] = _csv(ask_text("  Drugs / interventions",
                                            ", ".join(wl.get("interventions", []))))
        wl["terms"] = _csv(ask_text("  Other search terms",
                                    ", ".join(wl.get("terms", []))))
        days = ask_text("  Only developments within how many days?",
                        str(ct.get("recent_days", 30)))
        recent = int(days) if days.isdigit() else 30

        ct["enabled"] = ask_yes_no("  Include ClinicalTrials.gov (trial developments)?",
                                   default=ct.get("enabled", True))
        fda["enabled"] = ask_yes_no("  Include FDA drug recalls (openFDA)?",
                                    default=fda.get("enabled", False))
        edg["enabled"] = ask_yes_no("  Include SEC filings (EDGAR)?",
                                    default=edg.get("enabled", False))
        for c in (ct, fda, edg):
            c["recent_days"] = recent
        if edg["enabled"]:
            edg["user_agent"] = ask_text(
                "  SEC asks for a contact — your name and email",
                edg.get("user_agent") or "")
            edg["forms"] = _csv(ask_text("  SEC form types (comma-separated)",
                                         ", ".join(edg.get("forms", ["8-K"]))))
        enabled = [n for n, c in (("ClinicalTrials.gov", ct), ("FDA recalls", fda),
                                  ("SEC EDGAR", edg)) if c.get("enabled")]
        print(f"  → primary sources: {', '.join(enabled) or 'none selected'}")
    else:
        for c in (ct, fda, edg):
            c["enabled"] = False

    # 3. Focus
    focus = ask_text(
        "Only keep stories mentioning these keywords (comma-separated, optional)", ""
    )
    cfg["filters"]["include_keywords"] = [k.strip() for k in focus.split(",") if k.strip()]
    mute = ask_text("Always drop stories mentioning these keywords (optional)", "")
    cfg["filters"]["exclude_keywords"] = [k.strip() for k in mute.split(",") if k.strip()]

    age = ask_text("How many hours back should stories be considered?", str(cfg["filters"].get("max_age_hours", 48)))
    try:
        cfg["filters"]["max_age_hours"] = int(age)
    except ValueError:
        pass

    # 4. LLM backend
    backend = ask_choice(
        "How should story summaries be written?",
        [
            ("none", "No LLM — use the article's own lead sentences (instant, offline, free)"),
            ("ollama", "Local model via Ollama (private, free, runs on your machine)"),
            ("openai", "An OpenAI-compatible API (OpenAI, OpenRouter, Groq, LM Studio…)"),
        ],
        cfg["llm"].get("backend", "none"),
    )
    cfg["llm"]["backend"] = backend
    if backend == "ollama":
        cfg["llm"]["base_url"] = ask_text("Ollama URL", cfg["llm"].get("base_url") or "http://localhost:11434")
        cfg["llm"]["model"] = ask_text("Model name (e.g. llama3.2, qwen2.5, phi3)", cfg["llm"].get("model") or "llama3.2")
    elif backend == "openai":
        cfg["llm"]["base_url"] = ask_text("API base URL", cfg["llm"].get("base_url") or "https://api.openai.com/v1")
        cfg["llm"]["model"] = ask_text("Model name", cfg["llm"].get("model") or "gpt-4o-mini")
        cfg["llm"]["api_key_env"] = ask_text(
            "Name of the environment variable holding your API key",
            cfg["llm"].get("api_key_env") or "OPENAI_API_KEY",
        )
        print(f"  → Set it before running, e.g.  export {cfg['llm']['api_key_env']}=sk-...")

    if backend != "none":
        cfg["output"]["why_it_matters"] = ask_yes_no(
            "Add a short 'Why it matters' note to each story?",
            default=cfg["output"].get("why_it_matters", False),
        )
    else:
        cfg["output"]["why_it_matters"] = False

    # 5. Output
    fmt = ask_choice(
        "Output format for the digest file?",
        [("markdown", "Markdown (.md)"), ("html", "HTML web page (.html)"), ("text", "Plain text (.txt)")],
        cfg["output"].get("format", "markdown"),
    )
    cfg["output"]["format"] = fmt
    cfg["output"]["path"] = ask_text("Folder to write digests into", cfg["output"].get("path", "digest"))

    # 6. Email delivery (optional)
    email = cfg.setdefault("email", {})
    if ask_yes_no("Email the digest to yourself when it runs?", default=email.get("enabled", False)):
        email["enabled"] = True
        email["smtp_host"] = ask_text("SMTP server host (e.g. smtp.gmail.com)", email.get("smtp_host", ""))
        port = ask_text("SMTP port", str(email.get("smtp_port", 587)))
        try:
            email["smtp_port"] = int(port)
        except ValueError:
            email["smtp_port"] = 587
        email["use_tls"] = ask_yes_no("Use STARTTLS?", default=email.get("use_tls", True))
        email["username"] = ask_text("SMTP username (often your email address)", email.get("username", ""))
        email["password_env"] = ask_text(
            "Env var holding the SMTP password",
            email.get("password_env") or "OPENBIONEWS_SMTP_PASSWORD",
        )
        email["from_addr"] = ask_text("From address", email.get("from_addr") or email.get("username", ""))
        to = ask_text("Send to (comma-separated addresses)", ", ".join(email.get("to_addrs", [])))
        email["to_addrs"] = [a.strip() for a in to.split(",") if a.strip()]
        print(f"  → Set the password before running:  export {email['password_env']}=...")
    else:
        email["enabled"] = False

    # 7. Save
    saved_path = config_mod.save_config(cfg, path)
    print()
    print(RULE)
    print("  Setup complete.")
    print(f"  Config written to: {saved_path}")
    print(RULE)
    _print_summary(cfg)
    return cfg


def _print_summary(cfg: dict) -> None:
    print("\nYour digest:")
    print(f"  Title    : {cfg['profile']['title']}")
    print(f"  Topics   : {', '.join(cfg['profile'].get('bundles', [])) or '(custom feeds)'}")
    print(f"  Feeds    : {len(cfg['feeds'])}")
    conns = cfg.get("connectors", {})
    labels = {"clinicaltrials": "ClinicalTrials.gov", "openfda": "FDA recalls", "edgar": "SEC EDGAR"}
    enabled = [labels[k] for k in labels if conns.get(k, {}).get("enabled")]
    if enabled:
        wl = cfg.get("watchlist", {})
        watched = sum(len(wl.get(k, [])) for k in ("sponsors", "conditions", "interventions", "terms"))
        print(f"  Primary  : {', '.join(enabled)} ({watched} watched)")
    summaries = cfg["llm"]["backend"]
    if cfg["output"].get("why_it_matters"):
        summaries += " + why-it-matters"
    print(f"  Summaries: {summaries}")
    print(f"  Output   : {cfg['output']['format']} → {cfg['output']['path']}/")
    if cfg.get("email", {}).get("enabled"):
        print(f"  Email    : → {', '.join(cfg['email'].get('to_addrs', []))}")
    print("\nNext:")
    print("  openbionews run          # build your digest now")
    print("  openbionews doctor       # check feeds and LLM connectivity")
    print("  openbionews run --demo   # try it offline with bundled sample data")
