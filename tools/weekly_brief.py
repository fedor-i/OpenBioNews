"""Weekly public brief: "This week in biopharma records".

Builds a one-page summary of the past Monday–Sunday week from official records,
written for business-development and competitive-intelligence analysts:

- new industry Phase 3 trials registered on ClinicalTrials.gov
- industry Phase 3 trials that posted results
- industry Phase 3 trials marked terminated, suspended or withdrawn
- original FDA approvals (NDA/BLA; generics left out)
- Class I drug recalls
- FDA notices in the Federal Register (routine paperwork notices left out)

Every item links to its official record, and nothing is editorialised. If a source
can't be reached, the page says that section is unavailable, never that nothing
happened.

Writes into docs/brief/ (served by GitHub Pages):
  data/<week-end>.json   the collected records, the source of truth for rendering
  <week-end>.html        the week's page
  index.html, feed.xml   all weeks, newest first, and an RSS feed of them
and prints a LinkedIn draft to review before posting.

Usage:
  python tools/weekly_brief.py                 # the last full Mon–Sun week
  python tools/weekly_brief.py --end 2026-11-22
  python tools/weekly_brief.py --render-only   # rebuild pages from data/*.json
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openbionews.connectors.openfda_approvals import _appl_url  # noqa: E402
from openbionews.httputil import HTTPJSONError, get_json  # noqa: E402

OUT = ROOT / "docs" / "brief"
SITE = "https://fedor-i.github.io/OpenBioNews/"
CT_API = "https://clinicaltrials.gov/api/v2/studies"
APPROVALS_API = "https://api.fda.gov/drug/drugsfda.json"
RECALLS_API = "https://api.fda.gov/drug/enforcement.json"
FEDREG_API = "https://www.federalregister.gov/api/v1/documents.json"
MAX_ITEMS = 50
CT_FIELDS = ("NCTId,BriefTitle,LeadSponsorName,EnrollmentCount,OverallStatus,Condition,"
             "WhyStopped,Phase,Acronym,InterventionName")
INDUSTRY_P3 = "AREA[Phase]PHASE3 AND AREA[LeadSponsorClass]INDUSTRY"
# Routine Paperwork Reduction Act notices: real records, but noise for this reader.
FEDREG_SKIP = ("Agency Information Collection Activities",)

SECTIONS = [
    ("new_trials", "New Phase 3 trials",
     "Industry-sponsored Phase 3 trials first posted on ClinicalTrials.gov this week, largest first."),
    ("results", "Phase 3 results posted",
     "Industry-sponsored Phase 3 trials that posted results on ClinicalTrials.gov this week."),
    ("stopped", "Phase 3 trials stopped",
     "Industry-sponsored Phase 3 trials marked terminated, suspended or withdrawn whose "
     "record was updated this week. The status may have changed earlier; see the record."),
    ("approvals", "New FDA approvals",
     "Original NDA and BLA approvals dated this week in Drugs@FDA. Generics (ANDAs) "
     "and supplements are left out. Drugs@FDA can lag by a few days."),
    ("recalls", "Class I recalls",
     "The most serious class of drug recall, reported to FDA's enforcement database this week."),
    ("fda_notices", "FDA notices",
     "FDA documents published in the Federal Register this week: guidances, meetings, "
     "approval withdrawals and rules. Routine paperwork notices are left out."),
]


def last_full_week(today: date) -> tuple[date, date]:
    """The most recent Monday–Sunday week that has fully ended before ``today``."""
    end = today - timedelta(days=today.weekday() + 1)      # last Sunday
    return end - timedelta(days=6), end


# --------------------------------------------------------------------------- #
# Collect
# --------------------------------------------------------------------------- #
# ---- key words -------------------------------------------------------------
# Registry titles are long ("A Study of Aticaprant 10 mg as Adjunctive Therapy in
# Adult Participants With…"), so short displays use the record's own fields instead:
# company, drug, condition, acronym. docs/index.html builds the same key words for
# its live tiles; keep the two in step.
_ORG_NOISE = re.compile(
    r"\b(Inc|LLC|L\.L\.C|Ltd|Limited|Co|Corp|Corporation|GmbH|AG|SA|S\.A|plc|Pharmaceuticals?|"
    r"Pharma|Biosciences|Biotherapeutics|Therapeutics|Biopharma(ceuticals)?|"
    r"Research (&|and) Development)\b\.?", re.I)
_NOT_A_DRUG = re.compile(r"placebo|sham|vehicle|standard of care|usual care|best supportive|"
                         r"\bcontrol\b|^intervention\s*\d|^arm\b", re.I)
_DOSE_FORM = re.compile(r"\s+(oral|tablets?|capsules?|injection|injectable|solution|"
                        r"suspension|usp|for)$", re.I)


def short_org(name: str) -> str:
    """"Janssen Research & Development, LLC" -> "Janssen"."""
    full = (name or "").strip()
    head = re.split(r",| - |\s+[Aa]n?\s+(?=[A-Z])", full)[0]     # "…, LLC", "… - a GSK company", "… A Sanofi Co"
    short = re.sub(r"[\s&-]+$", "", re.sub(r"\s+", " ", _ORG_NOISE.sub("", head))).strip()
    return short or full


def key_drug(names) -> str:
    """The investigational products, without placebo/control arms or dosage-form words."""
    out = []
    for n in names or []:
        if not n or _NOT_A_DRUG.search(n):
            continue
        n = re.sub(r"\([^)]*\)", "", n).strip()
        while _DOSE_FORM.search(n):
            n = _DOSE_FORM.sub("", n).strip()
        if n and n.lower() not in (o.lower() for o in out):
            out.append(n)
    return " + ".join(out[:2])


def key_cond(cond: str) -> str:
    """Index-style "Depressive Disorder, Major" -> "Major Depressive Disorder"."""
    m = re.fullmatch(r"([^,()]+), ([^,()]+)", (cond or "").strip())
    if m and len(m.group(2).split()) <= 2:
        return f"{m.group(2)} {m.group(1)}"
    return (cond or "").strip()


def _ct(adv: str) -> tuple[int, list[dict]]:
    payload = get_json(CT_API, params={
        "filter.advanced": adv, "fields": CT_FIELDS, "pageSize": 100,
        "countTotal": "true", "sort": "EnrollmentCount:desc"})
    items = []
    for study in payload.get("studies", []):
        ps = study.get("protocolSection", {})
        ident = ps.get("identificationModule", {})
        nct = ident.get("nctId", "")
        enroll = ps.get("designModule", {}).get("enrollmentInfo", {}).get("count")
        conditions = ps.get("conditionsModule", {}).get("conditions", []) or []
        facts = [ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name", "")]
        if enroll:
            facts.append(f"{enroll:,} participants")
        if conditions:
            facts.append(", ".join(conditions[:2]))
        status = ps.get("statusModule", {})
        why = status.get("whyStopped")
        overall = (status.get("overallStatus") or "").replace("_", " ").capitalize()
        drugs = [i.get("name", "") for i in
                 ps.get("armsInterventionsModule", {}).get("interventions", []) or []]
        items.append({
            "title": ident.get("briefTitle", nct),
            "key": {"org": short_org(facts[0]), "what": key_drug(drugs) or ident.get("acronym", ""),
                    "cond": key_cond(conditions[0]) if conditions else "",
                    "acr": ident.get("acronym", "")},
            "url": f"https://clinicaltrials.gov/study/{nct}",
            "cite": nct,
            "facts": [f for f in facts if f],
            "note": f"{overall}: {why}" if why else overall,
        })
    return int(payload.get("totalCount") or len(items)), items


def collect_trials(start: date, end: date) -> dict:
    rng = f"RANGE[{start},{end}]"
    out = {}
    for key, adv in [
        ("new_trials", f"{INDUSTRY_P3} AND AREA[StudyFirstPostDate]{rng}"),
        ("results", f"{INDUSTRY_P3} AND AREA[ResultsFirstPostDate]{rng}"),
        ("stopped", f"{INDUSTRY_P3} AND AREA[OverallStatus](TERMINATED OR SUSPENDED OR "
                    f"WITHDRAWN) AND AREA[LastUpdatePostDate]{rng}"),
    ]:
        try:
            total, items = _ct(adv)
            for it in items:                 # the "stopped" note only matters there
                if key != "stopped":
                    it["note"] = ""
            out[key] = {"total": total, "items": items}
        except HTTPJSONError as exc:
            out[key] = {"error": str(exc)[:200]}
    return out


def collect_approvals(start: date, end: date) -> dict:
    s8, e8 = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    search = (f'submissions.submission_type:"ORIG"+AND+submissions.submission_status:"AP"'
              f"+AND+submissions.submission_status_date:[{s8}+TO+{e8}]")
    try:
        payload = get_json(APPROVALS_API, raw_query=f"search={search}&limit=1000",
                           not_found_ok=True)
    except HTTPJSONError as exc:
        return {"error": str(exc)[:200]}
    items, seen = [], set()
    for app in payload.get("results", []) or []:
        appno = app.get("application_number", "")
        if appno.startswith("ANDA") or appno in seen:
            continue
        # The search matches an application if ANY submission meets each clause, so
        # confirm the original approval itself falls in this week.
        orig = [s for s in app.get("submissions", []) or []
                if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP"
                and s8 <= s.get("submission_status_date", "") <= e8]
        if not orig:
            continue
        seen.add(appno)
        of = app.get("openfda", {}) or {}
        products = app.get("products", []) or [{}]
        brand = (of.get("brand_name") or [products[0].get("brand_name") or ""])[0]
        generic = (of.get("generic_name") or [""])[0]
        if not generic:
            generic = ", ".join(a.get("name", "") for a in products[0].get("active_ingredients", []) or [])
        sub = orig[0]
        facts = [app.get("sponsor_name", "").title(),
                 generic.lower() if generic else "",
                 "priority review" if (sub.get("review_priority") or "").upper() == "PRIORITY" else "",
                 f"approved {sub['submission_status_date'][:4]}-{sub['submission_status_date'][4:6]}-"
                 f"{sub['submission_status_date'][6:]}"]
        # Title-case real brand names only (Drugs@FDA shouts them); with no brand, fall
        # back to the application number as-is, so "NDA217062" isn't mangled.
        title = (brand.title() if brand.isupper() else brand) if brand else appno
        items.append({"title": title, "key": {"org": short_org(app.get("sponsor_name", "").title()),
                                              "what": title, "cond": generic.lower() if generic else "",
                                              "extra": "priority review" if "priority review" in facts else ""},
                      "url": _appl_url(appno),
                      "cite": appno, "facts": [f for f in facts if f], "note": ""})
    items.sort(key=lambda i: ("priority review" not in i["facts"], i["title"]))
    return {"total": len(items), "items": items}


def collect_recalls(start: date, end: date) -> dict:
    s8, e8 = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    search = f'classification:"Class+I"+AND+report_date:[{s8}+TO+{e8}]'
    try:
        payload = get_json(RECALLS_API, raw_query=f"search={search}&limit=100", not_found_ok=True)
    except HTTPJSONError as exc:
        return {"error": str(exc)[:200]}
    items = []
    for r in payload.get("results", []) or []:
        number = r.get("recall_number", "")
        product = r.get("product_description", "") or "Drug product"
        items.append({
            "title": product if len(product) <= 120 else product[:117] + "…",
            "url": f"{RECALLS_API}?search=recall_number:%22{urllib.parse.quote(number)}%22",
            "cite": number,
            "facts": [r.get("recalling_firm", ""), r.get("status", "")],
            "note": (r.get("reason_for_recall") or "")[:240],
        })
    return {"total": len(items), "items": items}


def collect_fda_notices(start: date, end: date) -> dict:
    params = [("per_page", "100"), ("order", "newest"),
              ("conditions[agencies][]", "food-and-drug-administration"),
              ("conditions[publication_date][gte]", str(start)),
              ("conditions[publication_date][lte]", str(end))]
    params += [("fields[]", f) for f in ("title", "type", "publication_date", "document_number", "html_url")]
    try:
        payload = get_json(f"{FEDREG_API}?{urllib.parse.urlencode(params)}")
    except HTTPJSONError as exc:
        return {"error": str(exc)[:200]}
    items = []
    for r in payload.get("results", []) or []:
        title = r.get("title", "")
        if title.startswith(FEDREG_SKIP):
            continue
        items.append({"title": title, "url": r.get("html_url", ""),
                      "cite": f"FR Doc. {r.get('document_number', '')}",
                      "facts": [r.get("type", ""), r.get("publication_date", "")], "note": ""})
    return {"total": len(items), "items": items}


def collect(start: date, end: date) -> dict:
    sections = collect_trials(start, end)
    sections["approvals"] = collect_approvals(start, end)
    sections["recalls"] = collect_recalls(start, end)
    sections["fda_notices"] = collect_fda_notices(start, end)
    for sec in sections.values():
        if "items" in sec:
            sec["items"] = sec["items"][:MAX_ITEMS]
    return {"start": str(start), "end": str(end),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sections": sections}


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
# How each section's count reads in the summary chips, index and feed (one, many).
STAT_LABELS = {
    "new_trials": ("new Phase 3 trial", "new Phase 3 trials"),
    "results": ("Phase 3 trial with results", "Phase 3 trials with results"),
    "stopped": ("Phase 3 trial stopped", "Phase 3 trials stopped"),
    "approvals": ("FDA approval", "FDA approvals"),
    "recalls": ("Class I recall", "Class I recalls"),
    "fda_notices": ("FDA notice", "FDA notices"),
}


def stat(sections: dict, key: str, html_bold: bool = False) -> str:
    sec = sections[key]
    one, many = STAT_LABELS[key]
    if "error" in sec:
        return f"{many}: unavailable"
    n = sec.get("total", 0)
    num = f"<b>{n}</b>" if html_bold else str(n)
    return f"{num} {html.escape(one if n == 1 else many) if html_bold else (one if n == 1 else many)}"


def week_label(brief: dict) -> str:
    s, e = date.fromisoformat(brief["start"]), date.fromisoformat(brief["end"])
    left = f"{s:%b} {s.day}" if s.year == e.year else f"{s:%b} {s.day}, {s.year}"
    right = f"{e.day}" if s.month == e.month else f"{e:%b} {e.day}"
    return f"{left}–{right}, {e.year}"


CSS = """
:root{--bg:#eef6f4;--panel:#fff;--ink:#132321;--muted:#5b726e;--line:#d6e6e2;--accent:#0d9488}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0b1a18;--panel:#122320;
--ink:#e6efec;--muted:#8aa39e;--line:#22403b;--accent:#2dd4bf}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:820px;margin:0 auto;padding:24px 16px 48px}
a{color:var(--accent)}
.brand{font:700 1.05rem Georgia,serif;text-decoration:none;color:var(--ink)}
h1{font-size:1.6rem;margin:.6rem 0 .2rem}
.sub{color:var(--muted);margin:0 0 1.2rem;font-size:.92rem}
.stats{display:flex;flex-wrap:wrap;gap:.5rem;margin:0 0 1.4rem;padding:0;list-style:none}
.stats li{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.35rem .7rem;font-size:.85rem}
.stats b{font-size:1rem}
section{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:.9rem 1rem;margin:0 0 1rem}
h2{font-size:1.15rem;margin:0 0 .15rem}
.what{color:var(--muted);font-size:.85rem;margin:0 0 .6rem}
ol{margin:0;padding-left:1.3rem}
li{margin:.45rem 0}
ol a{text-decoration:none}
ol a:hover{text-decoration:underline}
.facts{color:var(--muted);font-size:.85rem}
.note{font-size:.85rem;margin-top:.1rem}
.empty,.err{color:var(--muted);font-size:.9rem;margin:0}
.err{color:#b45309}
footer{color:var(--muted);font-size:.82rem;margin-top:1.6rem}
.weeks li{margin:.5rem 0}
"""


def _page(title: str, body: str, description: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title>"
            f'<meta name="description" content="{html.escape(description)}">'
            f'<meta property="og:title" content="{html.escape(title)}">'
            f'<meta property="og:description" content="{html.escape(description)}">'
            f'<meta property="og:image" content="{SITE}og.png">'
            '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
            '<meta name="twitter:card" content="summary_large_image">'
            f'<link rel="alternate" type="application/rss+xml" title="OpenBioNews weekly brief" href="feed.xml">'
            f"<style>{CSS}</style></head><body><main>{body}</main></body></html>\n")


def render_week(brief: dict) -> str:
    label = week_label(brief)
    secs = brief["sections"]
    stats = "".join(f"<li>{stat(secs, k, html_bold=True)}</li>" for k, _, _ in SECTIONS)
    parts = [f'<a class="brand" href="{SITE}">OpenBioNews</a>',
             "<h1>This week in biopharma records</h1>",
             f'<p class="sub">{html.escape(label)} · every item links to its official record · '
             f'<a href="index.html">all weeks</a> · <a href="feed.xml">RSS</a></p>',
             f'<ul class="stats">{stats}</ul>']
    for key, name, what in SECTIONS:
        sec = secs[key]
        parts.append(f'<section id="{key}"><h2>{html.escape(name)}</h2><p class="what">{html.escape(what)}</p>')
        if "error" in sec:
            parts.append('<p class="err">This source couldn\'t be reached when the brief was built, '
                         "so this section is missing, not empty.</p>")
        elif not sec["items"]:
            parts.append('<p class="empty">None this week.</p>')
        else:
            parts.append("<ol>")
            for it in sec["items"]:
                facts = " · ".join(html.escape(f) for f in it["facts"])
                note = f'<div class="note">{html.escape(it["note"])}</div>' if it.get("note") else ""
                parts.append(f'<li><a href="{html.escape(it["url"])}">{html.escape(it["title"])}</a>'
                             f'<div class="facts">{facts} · {html.escape(it["cite"])}</div>{note}</li>')
            parts.append("</ol>")
            if sec["total"] > len(sec["items"]):
                parts.append(f'<p class="what">Showing {len(sec["items"])} of {sec["total"]}.</p>')
        parts.append("</section>")
    parts.append(f"<footer>Built automatically from ClinicalTrials.gov, openFDA and the Federal "
                 f"Register on {html.escape(brief['generated_at'][:10])}. Nothing here is "
                 f"editorialised; check the linked record before relying on an item. Not investment "
                 f'or medical advice. · <a href="{SITE}">OpenBioNews</a> (free, open source)</footer>')
    desc = (f"{label}: " + ", ".join(stat(secs, k) for k, _, _ in SECTIONS[:4])
            + ". Every item linked to its official record.")
    return _page(f"This week in biopharma records — {label}", "".join(parts), desc)


def render_index(briefs: list[dict]) -> str:
    rows = "".join(
        f'<li><a href="{b["end"]}.html">{html.escape(week_label(b))}</a>'
        f'<div class="facts">' + html.escape(" · ".join(stat(b["sections"], k) for k, _, _ in SECTIONS))
        + "</div></li>"
        for b in briefs)
    body = (f'<a class="brand" href="{SITE}">OpenBioNews</a><h1>Weekly brief</h1>'
            f'<p class="sub">This week in biopharma records: new Phase 3 trials, results, stopped '
            f'trials, FDA approvals, Class I recalls and FDA notices, every item linked to its '
            f'official record. Published every Monday. <a href="feed.xml">RSS</a></p>'
            f'<ol class="weeks">{rows}</ol>')
    return _page("OpenBioNews weekly brief", body,
                 "A weekly, fully cited summary of biopharma records for BD and competitive-intelligence analysts.")


def render_feed(briefs: list[dict]) -> str:
    def esc(s):
        return html.escape(s, quote=False)
    items = []
    for b in briefs[:20]:
        when = datetime.fromisoformat(b["generated_at"].replace("Z", "+00:00"))
        summary = ", ".join(stat(b["sections"], k) for k, _, _ in SECTIONS)
        link = f"{SITE}brief/{b['end']}.html"
        items.append(f"<item><title>{esc('This week in biopharma records — ' + week_label(b))}</title>"
                     f"<link>{link}</link><guid isPermaLink=\"true\">{link}</guid>"
                     f"<pubDate>{format_datetime(when)}</pubDate>"
                     f"<description>{esc(summary + '. Every item linked to its official record.')}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            "<title>OpenBioNews weekly brief</title>"
            f"<link>{SITE}brief/</link>"
            "<description>This week in biopharma records, fully cited.</description>"
            + "".join(items) + "</channel></rss>\n")


def key_line(item: dict) -> str:
    """"Janssen: Aticaprant · Major Depressive Disorder (VENTURA-7)", falling back to
    the sponsor and a shortened title when a record has no usable key words."""
    k = item.get("key") or {}
    if not k.get("what"):
        return f"{item['facts'][0]}: {_short(item['title'])}"
    line = f"{k['org']}: {k['what']}" if k.get("org") else k["what"]
    if k.get("cond"):
        line += f" · {k['cond']}"
    if k.get("acr") and k["acr"] != k["what"]:
        line += f" ({k['acr']})"
    return line


def _short(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _n(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def render_linkedin(brief: dict) -> str:
    """A plain-text draft to review and edit before posting. Facts only, no claims."""
    secs, label = brief["sections"], week_label(brief)

    def ok(key):
        return "error" not in secs[key]

    def examples(key, n=2):
        return "".join(f"\n   – {key_line(i)}" for i in secs[key]["items"][:n])

    lines = [f"This week in biopharma records ({label})", ""]
    if ok("new_trials"):
        t = secs["new_trials"]
        lines.append(f"• {_n(t['total'], 'new industry Phase 3 trial', 'new industry Phase 3 trials')}"
                     + (f", largest first:{examples('new_trials')}" if t["items"] else ""))
    if ok("results"):
        lines.append(f"• {_n(secs['results']['total'], 'industry Phase 3 trial', 'industry Phase 3 trials')}"
                     f" posted results{examples('results')}")
    if ok("stopped"):
        lines.append(f"• {_n(secs['stopped']['total'], 'industry Phase 3 trial', 'industry Phase 3 trials')}"
                     f" marked terminated, suspended or withdrawn{examples('stopped')}")
    if ok("approvals"):
        a = secs["approvals"]
        prio = [i for i in a["items"] if "priority review" in i["facts"]]
        named = "".join(f"\n   – {i['title']} ({i['facts'][1]}, {i['facts'][0]})" if len(i["facts"]) > 2
                        else f"\n   – {i['title']} ({i['facts'][0]})" for i in prio)
        lines.append(f"• {_n(a['total'], 'original FDA approval', 'original FDA approvals')} (NDA/BLA)"
                     + (f", {len(prio)} with priority review:{named}" if prio else ""))
    if ok("recalls"):
        lines.append(f"• {_n(secs['recalls']['total'], 'Class I drug recall', 'Class I drug recalls')}")
    lines += ["", f"Every item links to its official record: {SITE}brief/{brief['end']}.html", "",
              "Built automatically from ClinicalTrials.gov, openFDA and the Federal Register "
              "with OpenBioNews (free, open source). Check the record before relying on an item.",
              "", "#biotech #pharma #clinicaltrials #FDA #competitiveintelligence"]
    return "\n".join(lines)


def latest_summary(brief: dict) -> dict:
    """The newest week, as slides for the site's front tile. Counts are plain text;
    records carry key words ({lead, org, what, cond, acr, extra}) so the page can pick
    the longest version that fits the tile at the visitor's screen size."""
    secs = brief["sections"]

    def items(key, n):
        return [] if "error" in secs[key] else secs[key]["items"][:n]

    slides = [{"text": stat(secs, k)} for k in ("new_trials", "results", "approvals", "recalls")
              if "error" not in secs[k]]
    for lead, key, n in (("New Phase 3", "new_trials", 2), ("Results", "results", 2),
                         ("Approved", "approvals", 4), ("Stopped", "stopped", 2)):
        for i in items(key, n):
            k = i.get("key") or {"what": _short(i["title"], 60)}
            slides.append({"lead": lead, **{f: v for f, v in k.items() if v}})
    return {"end": brief["end"], "label": week_label(brief), "url": f"{brief['end']}.html",
            "slides": slides}


def write_site(out: Path) -> list[dict]:
    briefs = sorted((json.loads(p.read_text("utf-8")) for p in (out / "data").glob("*.json")),
                    key=lambda b: b["end"], reverse=True)
    for b in briefs:
        (out / f"{b['end']}.html").write_text(render_week(b), "utf-8")
    (out / "index.html").write_text(render_index(briefs), "utf-8")
    (out / "feed.xml").write_text(render_feed(briefs), "utf-8")
    if briefs:
        (out / "latest.json").write_text(json.dumps(latest_summary(briefs[0]), indent=1,
                                                    ensure_ascii=False), "utf-8")
    return briefs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--end", help="the Sunday the week ends on (YYYY-MM-DD)")
    ap.add_argument("--render-only", action="store_true", help="rebuild pages from data/*.json")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    out = Path(args.out)
    (out / "data").mkdir(parents=True, exist_ok=True)

    if not args.render_only:
        if args.end:
            end = date.fromisoformat(args.end)
            start = end - timedelta(days=6)
        else:
            start, end = last_full_week(datetime.now(timezone.utc).date())
        brief = collect(start, end)
        (out / "data" / f"{end}.json").write_text(json.dumps(brief, indent=1, ensure_ascii=False), "utf-8")
        failed = [k for k, s in brief["sections"].items() if "error" in s]
        for k in failed:
            print(f"::warning title=Weekly brief::{k} unavailable: {brief['sections'][k]['error']}",
                  file=sys.stderr)
        print(render_linkedin(brief))
    write_site(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
