"""`openbionews doctor` — check that the config, feeds and LLM are healthy."""

from __future__ import annotations

import os

from . import config as config_mod
from . import fetch, mailer
from .connectors import get_connectors
from .llm import get_backend

OK = "✓"
BAD = "✗"


def run_doctor(cfg: dict, check_feeds: bool = True) -> int:
    """Print a diagnostic report. Returns an exit code (0 = healthy)."""
    problems = 0

    print("Configuration")
    issues = config_mod.validate_config(cfg)
    if issues:
        for issue in issues:
            print(f"  {BAD} {issue}")
            problems += 1
    else:
        print(f"  {OK} config looks valid")

    print("\nLLM backend")
    backend = get_backend(cfg)
    ok, message = backend.available()
    print(f"  {OK if ok else BAD} {backend.label}: {message}")
    if not ok:
        problems += 1
        if cfg.get("llm", {}).get("backend") != "none":
            print("     (the digest will still run; failed summaries fall back to no-LLM)")

    email_cfg = cfg.get("email", {})
    if email_cfg.get("enabled"):
        print("\nEmail delivery")
        if mailer.is_configured(email_cfg):
            env = email_cfg.get("password_env", "")
            has_pw = bool(os.environ.get(env)) if env else True
            print(f"  {OK} configured: {email_cfg['from_addr']} → "
                  f"{', '.join(email_cfg.get('to_addrs', []))} via {email_cfg.get('smtp_host')}")
            if env and not has_pw:
                print(f"  {BAD} SMTP password env var ${env} is not set")
                problems += 1
        else:
            print(f"  {BAD} email enabled but host/from/to are incomplete")
            problems += 1

    connectors = get_connectors(cfg)
    if connectors:
        print("\nPrimary sources")
        for conn in connectors:
            ok, message = conn.available()
            print(f"  {OK if ok else BAD} {conn.label}: {message}")
            if not ok:
                problems += 1

    if check_feeds:
        feeds = cfg.get("feeds", [])
        print(f"\nFeeds ({len(feeds)})")
        for feed in feeds:
            name = feed.get("name") or feed.get("url", "?")
            try:
                items = fetch.fetch_feed(feed, timeout=15)
                print(f"  {OK} {name}: {len(items)} items")
            except fetch.FetchError as exc:
                print(f"  {BAD} {name}: {exc}")
                problems += 1

    print()
    if problems == 0:
        print(f"{OK} All good — run `openbionews run` to build your digest.")
        return 0
    print(f"{BAD} {problems} issue(s) found. Fix them or run `openbionews setup` again.")
    return 1
