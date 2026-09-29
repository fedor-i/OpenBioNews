"""Command-line entry point for OpenBioNews."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from . import config as config_mod
from . import sources
from .doctor import run_doctor
from .run import run as run_pipeline
from .setup_wizard import run_wizard
from .termio import force_utf8_output


def _load_or_hint(path: Path | None):
    """Load config, or print a friendly hint and exit if it's missing."""
    cfg_path = path or config_mod.default_config_path()
    if not config_mod.config_exists(cfg_path):
        print("No configuration found.")
        print("Run `openbionews setup` to create one (takes about a minute),")
        print("or `openbionews run --demo` to try it with bundled sample data.")
        raise SystemExit(2)
    return config_mod.load_config(cfg_path)


def cmd_setup(args) -> int:
    path = Path(args.config).expanduser() if args.config else None
    existing = None
    if path and config_mod.config_exists(path) or (not path and config_mod.config_exists()):
        if _confirm("A config already exists. Start from it?", default=True):
            existing = config_mod.load_config(path)
    run_wizard(path=path, existing=existing)
    return 0


def cmd_run(args) -> int:
    if args.demo:
        # Offline showcase: mixed RSS + primary-source digest from bundled data.
        from .demo import build_demo_digest
        rendered, _ = build_demo_digest(fmt=(args.format or "markdown"))
        sys.stdout.write(rendered)
        return 0

    cfg = _load_or_hint(Path(args.config).expanduser() if args.config else None)
    if args.no_summaries:
        cfg["output"]["summaries"] = False
    if args.format:
        cfg["output"]["format"] = args.format

    log = (lambda msg: print(msg, file=sys.stderr)) if not args.quiet else (lambda msg: None)
    email = True if args.email else (False if args.demo else None)
    result = run_pipeline(cfg, log=log, write=(False if args.stdout else None), email=email)

    if args.stdout or args.demo:
        sys.stdout.write(result.rendered)
    if result.output_path:
        print(f"\nWrote {result.story_count} stories to {result.output_path}", file=sys.stderr)
    if result.email_status:
        print(f"Email: {result.email_status}", file=sys.stderr)
    if result.fetch_errors and not args.quiet:
        print(f"({len(result.fetch_errors)} feed(s) failed — run `openbionews doctor`)", file=sys.stderr)
    return 0


def cmd_doctor(args) -> int:
    cfg = _load_or_hint(Path(args.config).expanduser() if args.config else None)
    return run_doctor(cfg, check_feeds=not args.no_feeds)


def cmd_sources(args) -> int:
    print("Available topic bundles:\n")
    for key, bundle in sources.BUNDLES.items():
        default = " (default)" if key in sources.DEFAULT_BUNDLES else ""
        print(f"  {key}{default}: {bundle['label']}")
        print(f"      {bundle['description']}")
        for feed in bundle["feeds"]:
            print(f"      - {feed['name']}  {feed['url']}")
        print()
    return 0


def _confirm(question: str, default: bool = True) -> bool:
    if not sys.stdin.isatty():
        return default
    hint = "Y/n" if default else "y/N"
    try:
        ans = input(f"{question} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default
    return default if not ans else ans.startswith("y")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openbionews",
        description="Gather news into a clean daily digest. Free and self-hosted.",
    )
    parser.add_argument("--version", action="version", version=f"OpenBioNews {__version__}")
    parser.add_argument("-c", "--config", help="path to config file")
    sub = parser.add_subparsers(dest="command")

    p_setup = sub.add_parser("setup", help="interactive onboarding (creates your config)")
    p_setup.set_defaults(func=cmd_setup)

    p_run = sub.add_parser("run", help="build your digest")
    p_run.add_argument("--demo", action="store_true", help="run offline with bundled sample data")
    p_run.add_argument("--stdout", action="store_true", help="print the digest instead of writing a file")
    p_run.add_argument("--no-summaries", action="store_true", help="headlines and links only")
    p_run.add_argument("--email", action="store_true", help="also email the digest (uses your email config)")
    p_run.add_argument("--format", choices=["markdown", "html", "text", "rss"], help="override output format")
    p_run.add_argument("-q", "--quiet", action="store_true", help="suppress progress output")
    p_run.set_defaults(func=cmd_run)

    p_doctor = sub.add_parser("doctor", help="check config, feeds and LLM connectivity")
    p_doctor.add_argument("--no-feeds", action="store_true", help="skip network feed checks")
    p_doctor.set_defaults(func=cmd_doctor)

    p_sources = sub.add_parser("sources", help="list the built-in topic bundles and feeds")
    p_sources.set_defaults(func=cmd_sources)

    return parser


def main(argv: list[str] | None = None) -> int:
    force_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except BrokenPipeError:
        # Downstream closed the pipe (e.g. `openbionews sources | head`).
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
