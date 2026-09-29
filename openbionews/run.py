"""The end-to-end run: fetch → filter → cluster → compose → render → write."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from . import fetch, mailer, pipeline, render
from .compose import compose
from .connectors import get_connectors
from .llm import get_backend
from .models import Digest


class RunResult:
    def __init__(self) -> None:
        self.digest: Digest | None = None
        self.rendered: str = ""
        self.output_path: Path | None = None
        self.fetch_errors: list[tuple[str, str]] = []
        self.compose_warnings: list[str] = []
        self.item_count: int = 0
        self.story_count: int = 0
        self.email_status: str = ""


def build_digest(cfg: dict[str, Any], log: Callable[[str], None] | None = None) -> RunResult:
    """Run the pipeline and return a RunResult (does not write to disk)."""
    log = log or (lambda _msg: None)
    result = RunResult()

    feeds = cfg.get("feeds", [])
    filters = cfg.get("filters", {})
    output = cfg.get("output", {})
    profile = cfg.get("profile", {})

    log(f"Fetching {len(feeds)} feed(s)…")

    def _status(name, count, error):
        if error:
            log(f"  ! {name}: {error}")
        else:
            log(f"  · {name}: {count} items")

    items, result.fetch_errors = fetch.fetch_all(feeds, on_status=_status)

    # Primary-source connectors (trial registries, regulators, filings).
    connectors = get_connectors(cfg)
    if connectors:
        log(f"Querying {len(connectors)} primary source(s)…")
        for conn in connectors:
            try:
                citems = conn.fetch()
                items.extend(citems)
                _status(conn.label, len(citems), None)
            except Exception as exc:  # noqa: BLE001 — a dead source never sinks the run
                result.fetch_errors.append((conn.label, str(exc)))
                _status(conn.label, 0, str(exc))

    result.item_count = len(items)

    items = pipeline.filter_items(items, filters)
    log(f"{len(items)} items after filtering.")

    threshold = float(filters.get("similarity_threshold", 0.5))
    clusters = pipeline.cluster_items(items, threshold=threshold)
    clusters = pipeline.rank_clusters(clusters)
    clusters = pipeline.limit_clusters(
        clusters,
        max_items=int(filters.get("max_items", 40) or 0),
        max_per_topic=int(filters.get("max_per_topic", 0) or 0),
    )
    result.story_count = len(clusters)
    log(f"{len(clusters)} stories after clustering.")

    backend = get_backend(cfg)
    want_summaries = bool(output.get("summaries", True))
    want_significance = bool(output.get("why_it_matters", False))
    log(f"Summarizing with {backend.label}…")
    digest, result.compose_warnings = compose(
        clusters, backend, profile,
        want_summaries=want_summaries,
        want_significance=want_significance,
    )
    result.digest = digest

    fmt = output.get("format", "markdown")
    group_by = output.get("group_by", "topic")
    result.rendered = render.render(digest, fmt=fmt, group_by=group_by)
    return result


def _extension(fmt: str) -> str:
    return {"markdown": "md", "html": "html", "text": "txt", "rss": "xml"}.get(fmt, "txt")


def run(cfg: dict[str, Any], log: Callable[[str], None] | None = None,
        write: bool | None = None, email: bool | None = None) -> RunResult:
    """Build the digest and, when configured, write and/or email it."""
    log = log or (lambda _msg: None)
    result = build_digest(cfg, log=log)
    output = cfg.get("output", {})
    should_write = output.get("write_file", True) if write is None else write
    if should_write and result.rendered:
        out_dir = Path(output.get("path", "digest"))
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d")
        ext = _extension(output.get("format", "markdown"))
        path = out_dir / f"digest-{stamp}.{ext}"
        path.write_text(result.rendered, encoding="utf-8")
        # A stable "latest" copy for scripting / serving.
        (out_dir / f"latest.{ext}").write_text(result.rendered, encoding="utf-8")
        result.output_path = path

    email_cfg = cfg.get("email", {})
    want_email = mailer.is_configured(email_cfg) if email is None else email
    if want_email and result.digest is not None:
        group_by = output.get("group_by", "topic")
        html_body = render.render(result.digest, fmt="html", group_by=group_by)
        text_body = render.render(result.digest, fmt="text", group_by=group_by)
        try:
            result.email_status = mailer.send_digest(
                result.digest, html_body, text_body, email_cfg
            )
            log(f"Email: {result.email_status}")
        except mailer.EmailError as exc:
            result.email_status = f"failed: {exc}"
            log(f"Email failed: {exc}")
    return result
