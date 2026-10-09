"""Render a Digest to markdown, HTML, plain text or an RSS feed."""

from __future__ import annotations

import html
from collections import OrderedDict
from email.utils import format_datetime
from xml.etree import ElementTree as ET

from . import cite, sources
from .models import Cluster, Digest

PROJECT_URL = "https://github.com/fedor-i/OpenBioNews"


_TOPIC_LABELS = {
    "clinical_trials": "Clinical Trials",
    "fda_recalls": "FDA Drug Recalls",
    "fda_approvals": "FDA Drug Approvals",
    "fda_shortages": "FDA Drug Shortages",
    "fda_events": "FDA Adverse Events (FAERS)",
    "fda_labels": "FDA Drug Labeling",
    "federal_register": "Federal Register",
    "sec_filings": "SEC Filings",
}


def _topic_label(topic: str) -> str:
    bundle = sources.BUNDLES.get(topic)
    if bundle:
        return bundle["label"]
    if topic in _TOPIC_LABELS:
        return _TOPIC_LABELS[topic]
    return topic.replace("_", " ").title() if topic else "Other"


def _group(digest: Digest, group_by: str) -> "OrderedDict[str, list[Cluster]]":
    groups: "OrderedDict[str, list[Cluster]]" = OrderedDict()
    if group_by == "topic":
        for cluster in digest.clusters:
            groups.setdefault(cluster.topic, []).append(cluster)
    else:
        groups[""] = list(digest.clusters)
    return groups


def _sources_note(cluster: Cluster) -> str:
    srcs = cluster.sources
    if len(srcs) > 1:
        return f"{srcs[0]} + {len(srcs) - 1} more"
    return srcs[0] if srcs else ""


def _dedup_citations(cluster: Cluster):
    """Unique citations across a cluster's items, preserving order."""
    seen: set[str] = set()
    out = []
    for item in cluster.items:
        for cite in item.citations:
            if cite.url and cite.url not in seen:
                seen.add(cite.url)
                out.append(cite)
    return out


def _citation_links_md(cluster: Cluster) -> str:
    cites = _dedup_citations(cluster)
    return ", ".join(f"[{c.label}]({c.url})" for c in cites)


def _change_text(cluster: Cluster) -> str:
    """The 'what changed since last run' line for the canonical item, if any."""
    meta = cluster.canonical.meta or {}
    change = meta.get("change") or ""
    if not change:
        return ""
    return "🆕 New" if meta.get("change_kind") == "new" else f"🔔 {change}"


def _cited_body_md(cluster: Cluster) -> tuple[str, str]:
    """(brief, source-key) with a ``<sup>n</sup>`` marker after each sentence.

    GitHub-flavoured markdown renders ``<sup>`` inline, so the numbered markers
    read as academic-style citations and the key below resolves each to its
    primary source.
    """
    markers, ordered = cite.number_citations(cluster.claims)
    sentences = []
    for i, claim in enumerate(cluster.claims):
        n = markers.get(i)
        sentences.append(f"{claim.text}<sup>{n}</sup>" if n else claim.text)
    body = " ".join(sentences)
    key = " · ".join(f"<sup>{n}</sup> [{c.label}]({c.url})" for n, c in ordered)
    return body, key


def render(digest: Digest, fmt: str = "markdown", group_by: str = "topic") -> str:
    if fmt == "html":
        return render_html(digest, group_by)
    if fmt == "text":
        return render_text(digest, group_by)
    if fmt == "rss":
        return render_rss(digest)
    return render_markdown(digest, group_by)


def render_markdown(digest: Digest, group_by: str = "topic") -> str:
    date = digest.generated_at.strftime("%A, %d %B %Y")
    out: list[str] = [f"# {digest.title}", "", f"*{date}*"]
    if digest.intro:
        out += ["", digest.intro]
    total = len(digest.clusters)
    out += ["", f"> {total} stories · ~{digest.read_minutes} min read · "
            f"summaries by {digest.backend_label}", ""]

    for topic, clusters in _group(digest, group_by).items():
        if group_by == "topic":
            out.append(f"## {_topic_label(topic)}")
            out.append("")
        for cluster in clusters:
            c = cluster.canonical
            out.append(f"### [{c.title}]({c.link})")
            note = _sources_note(cluster)
            when = cluster.latest.strftime("%d %b %H:%M UTC") if cluster.latest else ""
            meta = " · ".join(x for x in (c.tag, note, when) if x)
            if meta:
                out.append(f"*{meta}*")
            change = _change_text(cluster)
            if change:
                out.append(f"**{change}**")
            if cluster.claims:
                body, key = _cited_body_md(cluster)
                out += ["", body]
                if key:
                    out += ["", f"↳ Sources: {key}"]
            elif cluster.blurb:
                out += ["", cluster.blurb]
                cites = _citation_links_md(cluster)
                if cites:
                    out += ["", f"↳ Source: {cites}"]
            if cluster.significance:
                out += ["", f"> 💡 **Why it matters** *(AI analysis)*: {cluster.significance}"]
            if len(cluster.sources) > 1:
                links = ", ".join(
                    f"[{item.source}]({item.link})"
                    for item in cluster.items
                    if item.source
                )
                out += ["", f"Also: {links}"]
            out.append("")
    out.append("---")
    out.append("*Generated by OpenBioNews.*")
    return "\n".join(out).rstrip() + "\n"


def render_text(digest: Digest, group_by: str = "topic") -> str:
    date = digest.generated_at.strftime("%A, %d %B %Y")
    out: list[str] = [digest.title, date, ""]
    if digest.intro:
        out += [digest.intro, ""]
    out += [
        f"{len(digest.clusters)} stories · ~{digest.read_minutes} min read · "
        f"summaries by {digest.backend_label}",
        "",
    ]
    for topic, clusters in _group(digest, group_by).items():
        if group_by == "topic":
            label = _topic_label(topic)
            out += [label.upper(), "=" * len(label), ""]
        for cluster in clusters:
            c = cluster.canonical
            out.append(f"* {c.title}")
            if c.tag:
                out.append(f"  [{c.tag}]")
            change = _change_text(cluster)
            if change:
                out.append(f"  {change}")
            if cluster.claims:
                markers, ordered = cite.number_citations(cluster.claims)
                sentences = []
                for i, claim in enumerate(cluster.claims):
                    n = markers.get(i)
                    sentences.append(f"{claim.text} [{n}]" if n else claim.text)
                out.append("  " + " ".join(sentences))
                note = _sources_note(cluster)
                out.append(f"  {note} — {c.link}" if note else f"  {c.link}")
                for n, citation in ordered:
                    out.append(f"  [{n}] {citation.label} — {citation.url}")
            else:
                if cluster.blurb:
                    out.append(f"  {cluster.blurb}")
                note = _sources_note(cluster)
                out.append(f"  {note} — {c.link}" if note else f"  {c.link}")
                for citation in _dedup_citations(cluster):
                    out.append(f"  Source: {citation.label} — {citation.url}")
            if cluster.significance:
                out.append(f"  Why it matters (AI): {cluster.significance}")
            out.append("")
    out.append("-- Generated by OpenBioNews")
    return "\n".join(out).rstrip() + "\n"


def render_html(digest: Digest, group_by: str = "topic") -> str:
    def esc(s: str) -> str:
        return html.escape(s, quote=True)

    date = digest.generated_at.strftime("%A, %d %B %Y")
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(digest.title)}</title>",
        "<style>",
        ":root{color-scheme:light dark}",
        "body{font:16px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "max-width:44rem;margin:2rem auto;padding:0 1rem;color:#1a1a1a;background:#fff}",
        "@media (prefers-color-scheme:dark){body{background:#0b1a18;color:#e6efec}"
        "a{color:#2dd4bf}.meta{color:#8aa39e}.card{border-color:#22403b}}",
        "h1{font-size:1.7rem;margin-bottom:.2rem}h2{margin-top:2rem;border-bottom:2px solid #d6e6e2;padding-bottom:.3rem}",
        "h3{font-size:1.1rem;margin:.2rem 0}a{color:#0d9488;text-decoration:none}a:hover{text-decoration:underline}",
        ".meta{color:#6b7280;font-size:.85rem;margin:.1rem 0 .4rem}",
        ".card{border:1px solid #eee;border-radius:10px;padding:1rem;margin:.8rem 0}",
        ".sub{font-size:.8rem;color:#6b7280}.count{color:#6b7280;font-size:.9rem}",
        "sup.cite{font-size:.7em;line-height:0}sup.cite a{text-decoration:none;font-weight:600}",
        ".change{display:inline-block;font-size:.8rem;font-weight:600;color:#9a3412;"
        "background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;padding:.05rem .4rem;margin:.1rem 0 .3rem}",
        "@media (prefers-color-scheme:dark){.change{color:#fdba74;background:#2a1a0d;border-color:#7c2d12}}",
        ".sig{font-size:.9rem;color:#5b21b6;background:#f5f0ff;border-left:3px solid #7c3aed;"
        "border-radius:0 6px 6px 0;padding:.4rem .7rem;margin:.5rem 0 .2rem}.sig b{color:#6d28d9}",
        "@media (prefers-color-scheme:dark){.sig{color:#ddd0ff;background:#1e1830;border-color:#a78bfa}.sig b{color:#c4b5fd}}",
        ".srckey{font-size:.8rem;color:#6b7280;margin-top:.3rem}.srckey a{margin-right:.1rem}",
        "footer{margin-top:2rem;color:#9aa0a6;font-size:.85rem;border-top:1px solid #eee;padding-top:1rem}",
        "</style></head><body>",
        f"<h1>{esc(digest.title)}</h1>",
        f'<div class="meta">{esc(date)}</div>',
    ]
    if digest.intro:
        parts.append(f"<p>{esc(digest.intro)}</p>")
    parts.append(
        f'<p class="count">{len(digest.clusters)} stories · '
        f"~{digest.read_minutes} min read · "
        f"summaries by {esc(digest.backend_label)}</p>"
    )

    for topic, clusters in _group(digest, group_by).items():
        if group_by == "topic":
            parts.append(f"<h2>{esc(_topic_label(topic))}</h2>")
        for cluster in clusters:
            c = cluster.canonical
            parts.append('<div class="card">')
            parts.append(f'<h3><a href="{esc(c.link)}">{esc(c.title)}</a></h3>')
            note = _sources_note(cluster)
            when = cluster.latest.strftime("%d %b %H:%M UTC") if cluster.latest else ""
            meta = " · ".join(x for x in (c.tag, note, when) if x)
            if meta:
                parts.append(f'<div class="meta">{esc(meta)}</div>')
            change = _change_text(cluster)
            if change:
                parts.append(f'<div class="change">{esc(change)}</div>')
            if cluster.claims:
                markers, ordered = cite.number_citations(cluster.claims)
                spans = []
                for i, claim in enumerate(cluster.claims):
                    n = markers.get(i)
                    sup = ""
                    if n:
                        url = esc(next(c.url for k, c in ordered if k == n))
                        sup = f'<sup class="cite"><a href="{url}">{n}</a></sup>'
                    spans.append(f"{esc(claim.text)}{sup}")
                parts.append(f"<p>{' '.join(spans)}</p>")
                if ordered:
                    key = " · ".join(
                        f'<sup class="cite">{n}</sup> <a href="{esc(c.url)}">{esc(c.label)}</a>'
                        for n, c in ordered
                    )
                    parts.append(f'<div class="srckey">↳ Sources: {key}</div>')
            elif cluster.blurb:
                parts.append(f"<p>{esc(cluster.blurb)}</p>")
                cites = _dedup_citations(cluster)
                if cites:
                    links = ", ".join(f'<a href="{esc(x.url)}">{esc(x.label)}</a>' for x in cites)
                    parts.append(f'<div class="sub">↳ Source: {links}</div>')
            if cluster.significance:
                parts.append(
                    f'<div class="sig"><b>💡 Why it matters</b> (AI analysis): '
                    f'{esc(cluster.significance)}</div>'
                )
            if len(cluster.sources) > 1:
                links = ", ".join(
                    f'<a href="{esc(item.link)}">{esc(item.source)}</a>'
                    for item in cluster.items
                    if item.source
                )
                parts.append(f'<div class="sub">Also: {links}</div>')
            parts.append("</div>")

    parts.append("<footer>Generated by OpenBioNews.</footer>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def render_rss(digest: Digest) -> str:
    """Render the digest as an RSS 2.0 feed you can subscribe to in any reader."""
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = digest.title
    ET.SubElement(channel, "link").text = PROJECT_URL
    ET.SubElement(channel, "description").text = digest.intro or "OpenBioNews digest"
    ET.SubElement(channel, "generator").text = "OpenBioNews"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(digest.generated_at)

    for cluster in digest.clusters:
        c = cluster.canonical
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = c.title
        if c.link:
            ET.SubElement(item, "link").text = c.link
        # guid is an opaque unique id, not a URL to dereference.
        ET.SubElement(item, "guid", isPermaLink="false").text = c.guid or c.link or c.title
        if cluster.latest is not None:
            ET.SubElement(item, "pubDate").text = format_datetime(cluster.latest)
        if c.topic:
            ET.SubElement(item, "category").text = _topic_label(c.topic)
        body = []
        if c.tag:
            body.append(c.tag)
        change = _change_text(cluster)
        if change:
            body.append(change)
        if cluster.claims:
            markers, ordered = cite.number_citations(cluster.claims)
            sentences = []
            for i, claim in enumerate(cluster.claims):
                n = markers.get(i)
                sentences.append(f"{claim.text} [{n}]" if n else claim.text)
            body.append(" ".join(sentences))
            if ordered:
                body.append("Sources: " + "; ".join(
                    f"[{n}] {c2.label} ({c2.url})" for n, c2 in ordered))
        else:
            if cluster.blurb:
                body.append(cluster.blurb)
            cites = _dedup_citations(cluster)
            if cites:
                body.append("Source: " + "; ".join(f"{x.label} ({x.url})" for x in cites))
        if cluster.significance:
            body.append(f"Why it matters (AI): {cluster.significance}")
        ET.SubElement(item, "description").text = "\n\n".join(body)

    xml = ET.tostring(rss, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"
