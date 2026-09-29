"""Configuration model: defaults, load and save.

Config is plain JSON so no third-party YAML parser is needed. The onboarding
wizard writes it, ``openbionews doctor`` validates it, and it is small and
readable enough to hand-edit. A commented reference lives in
``config.example.json`` at the project root.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import sources

CONFIG_VERSION = 1
DEFAULT_CONFIG_NAME = "openbionews.config.json"


def default_config() -> dict[str, Any]:
    """A ready-to-run configuration for the OpenBioNews life-sciences profile."""
    return {
        "version": CONFIG_VERSION,
        "profile": {
            "title": "Daily Bio Brief",
            "intro": "Your automated life-sciences news digest.",
            "bundles": list(sources.DEFAULT_BUNDLES),
        },
        "feeds": sources.bundle_feeds(sources.DEFAULT_BUNDLES),
        "filters": {
            "max_age_hours": 48,
            "max_items": 40,
            "max_per_topic": 12,
            "include_keywords": [],
            "exclude_keywords": [],
            "similarity_threshold": 0.5,
        },
        "llm": {
            # backend: "none" | "openai" | "ollama"
            "backend": "none",
            "model": "",
            "base_url": "",
            "api_key_env": "OPENAI_API_KEY",
            "temperature": 0.3,
            "max_tokens": 220,
            "timeout": 60,
        },
        "output": {
            "format": "markdown",   # markdown | html | text | rss
            "group_by": "topic",     # topic | none
            "path": "digest",         # directory for written digests
            "write_file": True,
            "summaries": True,
            # Add a short "Why it matters:" note per story (LLM backends only).
            "why_it_matters": False,
        },
        "email": {
            # Set enabled: true and fill these to have `run` email the digest.
            # The SMTP password is read from an env var, never stored here.
            "enabled": False,
            "smtp_host": "",
            "smtp_port": 587,
            "use_tls": True,
            "username": "",
            "password_env": "OPENBIONEWS_SMTP_PASSWORD",
            "from_addr": "",
            "to_addrs": [],
        },
        # Entities to track for primary-source connectors (FDA/SEC/trials).
        "watchlist": {
            "sponsors": [],        # company / trial-sponsor names
            "conditions": [],       # diseases / indications
            "interventions": [],    # drugs / therapies
            "terms": [],            # free-text search terms
        },
        # Primary-source connectors read official records, not trade press.
        "connectors": {
            "clinicaltrials": {
                "enabled": False,
                "recent_days": 30,   # only developments updated within N days
                "max_per_query": 20,  # cap results per watch entry
                "max_total": 60,      # cap total studies across the connector
                "statuses": [],       # e.g. ["RECRUITING", "COMPLETED"]; empty = any
            },
            "openfda": {
                "enabled": False,
                "recent_days": 30,       # recalls reported within N days
                "max_per_query": 20,
                "max_total": 40,
                "classifications": [],    # e.g. ["Class I"]; empty = any severity
            },
            "openfda_approvals": {
                "enabled": False,
                "recent_days": 90,        # approvals are less frequent; wider window
                "max_per_query": 20,
                "max_total": 40,
                "include_supplements": True,  # also include new-indication supplements
            },
            "edgar": {
                "enabled": False,
                "recent_days": 30,       # filings filed within N days
                "forms": ["8-K"],         # SEC form types; [] = any
                "max_per_query": 20,
                "max_total": 40,
                # SEC asks for a descriptive User-Agent with contact info.
                # Set this to your own name/email, e.g. "Jane Doe jane@example.com".
                "user_agent": "",
            },
        },
    }


def default_config_path() -> Path:
    """Where the config lives by default (current directory)."""
    override = os.environ.get("OPENBIONEWS_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.cwd() / DEFAULT_CONFIG_NAME


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or default_config_path()
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return _merge_defaults(data)


def save_config(cfg: dict[str, Any], path: Path | None = None) -> Path:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def config_exists(path: Path | None = None) -> bool:
    return (path or default_config_path()).exists()


def _merge_defaults(data: dict[str, Any]) -> dict[str, Any]:
    """Fill any missing top-level sections/keys from defaults (forward-compat)."""
    base = default_config()
    for section, value in base.items():
        if section not in data:
            data[section] = value
        elif isinstance(value, dict) and isinstance(data.get(section), dict):
            for key, sub in value.items():
                data[section].setdefault(key, sub)
    return data


def validate_config(cfg: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems; empty means valid."""
    problems: list[str] = []
    feeds = cfg.get("feeds") or []
    if not feeds:
        problems.append("No feeds configured — run `openbionews setup`.")
    for i, feed in enumerate(feeds):
        if not feed.get("url"):
            problems.append(f"Feed #{i + 1} is missing a URL.")
    backend = cfg.get("llm", {}).get("backend", "none")
    if backend not in ("none", "openai", "ollama"):
        problems.append(f"Unknown llm.backend '{backend}' (use none/openai/ollama).")
    if backend == "openai":
        env = cfg["llm"].get("api_key_env", "")
        if env and not os.environ.get(env):
            problems.append(
                f"llm.backend is 'openai' but env var ${env} is not set."
            )
    fmt = cfg.get("output", {}).get("format", "markdown")
    if fmt not in ("markdown", "html", "text", "rss"):
        problems.append(f"Unknown output.format '{fmt}'.")
    return problems
