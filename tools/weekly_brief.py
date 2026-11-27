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
  ../sitemap.xml         the site's pages, for search engines
and prints a LinkedIn draft to review before posting. tools/brief_card.py adds each
week's share images (cards/); run --render-only afterwards to link them in.

Usage:
  python tools/weekly_brief.py                 # the last full Mon–Sun week
  python tools/weekly_brief.py --end 2026-11-22
  python tools/weekly_brief.py --render-only   # rebuild pages from data/*.json
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
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
EFTS_API = "https://efts.sec.gov/LATEST/search-index"
# SEC industry codes (SIC) counted as biopharma: pharmaceutical preparations, in vitro
# diagnostics, biological products.
BIOPHARMA_SICS = {"2834", "2835", "2836"}
# 8-K items worth a BD reader's attention, in plain words.
SEC_ITEMS = {"1.01": "entered a material agreement", "1.02": "ended a material agreement",
             "2.01": "completed an acquisition or sale"}
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
    ("sec", "SEC: deals and IPO filings",
     "Biopharma companies' 8-Ks reporting a material agreement entered or ended (licensing, "
     "collaborations, M&A) or a completed acquisition, and new IPO registrations (S-1, F-1), "
     "filed with the SEC this week. Biopharma means SEC industry codes 2834, 2835 and 2836."),
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


def _sec_name(display: str) -> tuple[str, str]:
    """("Vertex Pharmaceuticals Inc", "VRTX") from EDGAR's "Vertex Pharmaceuticals Inc
    (VRTX)  (CIK 0000875320)"."""
    name = re.sub(r"\s*\(CIK\s*\d+\)\s*$", "", display or "").strip()
    m = re.search(r"\s*\(([A-Z0-9.\-, ]{1,24})\)\s*$", name)
    return (name[: m.start()].strip(), m.group(1).split(",")[0].strip()) if m else (name, "")


def _efts_page(params: dict, ua: str, tries: int = 3) -> dict:
    """One page of EDGAR full-text search, retried on server errors and rate limits
    (EDGAR's search answers a heavy query with a 500 now and then)."""
    for attempt in range(tries):
        try:
            return get_json(EFTS_API, params=params, headers={"User-Agent": ua}, timeout=30)
        except HTTPJSONError as exc:
            m = re.search(r"HTTP (\d{3})", str(exc))
            transient = (m and (m.group(1).startswith("5") or m.group(1) == "429")) or \
                "timed out" in str(exc).lower() or "could not reach" in str(exc)
            if not transient or attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))
    raise AssertionError("unreachable")


def _efts(params: dict, ua: str, max_pages: int = 10) -> list[dict]:
    """Every hit for an EDGAR full-text search, following its pages."""
    hits: list[dict] = []
    while len(hits) < max_pages * 100:
        page = _efts_page({**params, "from": len(hits) or None}, ua)
        batch = (page.get("hits") or {}).get("hits") or []
        hits += batch
        total = ((page.get("hits") or {}).get("total") or {}).get("value", 0)
        if not batch or len(hits) >= total:
            break
        time.sleep(0.2)                   # SEC asks for at most 10 requests a second
    return hits


def parse_sec_hits(hits: list[dict], kind: str) -> list[dict]:
    """Brief items from EDGAR hits: biopharma filers only, one item per filing (EDGAR
    returns a hit per document, exhibits included). ``kind`` is "deal" (8-K) or "ipo"."""
    if hits and not any("sics" in (h.get("_source") or {}) for h in hits):
        raise HTTPJSONError("EDGAR results no longer carry industry codes (sics)")
    out, seen = [], set()
    for h in hits:
        src = h.get("_source") or {}
        accn = (h.get("_id") or "").partition(":")[0] or src.get("adsh", "")
        form = src.get("root_form") or src.get("form") or ""
        if not accn or accn in seen or not BIOPHARMA_SICS & set(map(str, src.get("sics") or [])):
            continue
        if kind == "deal":
            if form != "8-K":
                continue
            items = [i for i in (src.get("items") or []) if i in SEC_ITEMS]
            if not items:
                continue
            what = "; ".join(SEC_ITEMS[i] for i in items)
            detail = "8-K Item " + ", ".join(items)
        else:
            if form not in ("S-1", "F-1"):
                continue
            what, detail = f"filed to go public ({form})", form
        seen.add(accn)
        company, ticker = _sec_name((src.get("display_names") or [""])[0])
        cik = str(int((src.get("ciks") or ["0"])[0] or 0))
        url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{accn}-index.htm"
               if cik != "0" else f"https://efts.sec.gov/LATEST/search-index?q=%22{accn}%22")
        filed = src.get("file_date", "")
        out.append({"title": f"{company}: {what}",
                    "key": {"org": short_org(company), "what": what[0].upper() + what[1:], "acr": ticker},
                    "url": url, "cite": accn,
                    "facts": [f for f in (company, detail, f"filed {filed}" if filed else "") if f],
                    "note": ""})
    return out


def collect_sec(start: date, end: date) -> dict:
    """The week's biopharma deals (8-K Items 1.01, 1.02, 2.01) and IPO registrations
    (S-1, F-1) from EDGAR full-text search. SEC requires a contact email in the
    User-Agent: OPENBIONEWS_EDGAR_UA (the weekly workflow sets it from a secret)."""
    ua = os.environ.get("OPENBIONEWS_EDGAR_UA", "")
    if "@" not in ua:
        return {"error": "SEC needs a contact email: set OPENBIONEWS_EDGAR_UA"}
    week = {"dateRange": "custom", "startdt": str(start), "enddt": str(end)}
    # Each search on its own, so one failing (EDGAR sometimes answers a 500) leaves
    # the others' filings in the brief, with a note saying what's missing.
    searches = [("deal", "8-K", '"material definitive agreement"', "deal filings"),
                ("deal", "8-K", '"completion of acquisition"', "acquisition filings"),
                ("ipo", "S-1", '"initial public offering"', "S-1 IPO filings"),
                ("ipo", "F-1", '"initial public offering"', "F-1 IPO filings")]
    hits: dict[str, list] = {"deal": [], "ipo": []}
    failed, last_error = [], ""
    for kind, form, phrase, label in searches:
        try:
            hits[kind] += _efts({"q": phrase, "forms": form, **week}, ua)
        except HTTPJSONError as exc:
            failed.append(label)
            last_error = str(exc)[:200]
    if len(failed) == len(searches):
        return {"error": last_error}
    items = parse_sec_hits(hits["deal"], "deal")
    seen = {i["cite"] for i in items}
    items += [i for i in parse_sec_hits(hits["ipo"], "ipo") if i["cite"] not in seen]
    items.sort(key=lambda i: next((f for f in i["facts"] if f.startswith("filed ")), ""), reverse=True)
    if failed:
        return {"total": len(items), "items": items,
                "note": f"SEC's search didn't answer for {', '.join(failed)}; those may be missing."}
    return {"total": len(items), "items": items}


def collect(start: date, end: date) -> dict:
    sections = collect_trials(start, end)
    sections["approvals"] = collect_approvals(start, end)
    sections["sec"] = collect_sec(start, end)
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
    "sec": ("SEC deal or IPO filing", "SEC deals and IPO filings"),
    "recalls": ("Class I recall", "Class I recalls"),
    "fda_notices": ("FDA notice", "FDA notices"),
}


NOT_YET = "not part of the brief yet"


def with_all_sections(brief: dict) -> dict:
    """Weeks built before a section existed show it as "not part of the brief yet"
    rather than failing or reading as zero."""
    for key, _, _ in SECTIONS:
        brief["sections"].setdefault(key, {"error": NOT_YET})
    return brief


def stat(sections: dict, key: str, html_bold: bool = False) -> str:
    sec = sections.get(key) or {"error": NOT_YET}
    one, many = STAT_LABELS[key]
    if sec.get("error") == NOT_YET:
        return ""
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


def _page(title: str, body: str, description: str, url: str = "", image: str = "") -> str:
    """``url`` is the page's own address (canonical, og:url); ``image`` its share card,
    defaulting to the site-wide one."""
    image = image or f"{SITE}og.png"
    canon = (f'<link rel="canonical" href="{html.escape(url)}">'
             f'<meta property="og:url" content="{html.escape(url)}">') if url else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title>"
            f'<meta name="description" content="{html.escape(description)}">'
            f"{canon}"
            f'<meta property="og:type" content="article"><meta property="og:site_name" content="OpenBioNews">'
            f'<meta property="og:title" content="{html.escape(title)}">'
            f'<meta property="og:description" content="{html.escape(description)}">'
            f'<meta property="og:image" content="{html.escape(image)}">'
            '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
            '<meta name="twitter:card" content="summary_large_image">'
            f'<link rel="alternate" type="application/rss+xml" title="OpenBioNews weekly brief" href="feed.xml">'
            f"<style>{CSS}</style></head><body><main>{body}</main></body></html>\n")


def _week_body(brief: dict) -> list[str]:
    """The week's count chips, its sections and the footer, shared by the week's own
    page and the brief's front page."""
    secs = brief["sections"]
    stats = "".join(f"<li>{x}</li>" for x in (stat(secs, k, html_bold=True) for k, _, _ in SECTIONS) if x)
    parts = [f'<ul class="stats">{stats}</ul>']
    for key, name, what in SECTIONS:
        sec = secs[key]
        parts.append(f'<section id="{key}"><h2>{html.escape(name)}</h2><p class="what">{html.escape(what)}</p>')
        if sec.get("error") == NOT_YET:
            parts.append('<p class="empty">Not part of the brief yet that week.</p>')
        elif "error" in sec:
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
        if sec.get("note"):
            parts.append(f'<p class="err">{html.escape(sec["note"])}</p>')
        parts.append("</section>")
    return parts


def _footer(brief: dict) -> str:
    return (f"<footer>Built automatically from ClinicalTrials.gov, openFDA, the Federal "
            f"Register and SEC EDGAR on {html.escape(brief['generated_at'][:10])}. Nothing here is "
            f"editorialised; check the linked record before relying on an item. Not investment "
            f'or medical advice. · <a href="{SITE}">OpenBioNews</a> (free, open source)</footer>')


def _description(brief: dict) -> str:
    return (f"{week_label(brief)}: " + ", ".join(stat(brief["sections"], k) for k, _, _ in SECTIONS[:4])
            + ". Every item linked to its official record.")


def render_week(brief: dict, card: bool = False) -> str:
    """``card``: the week has its own share image in cards/ (tools/brief_card.py)."""
    label = week_label(brief)
    parts = [f'<a class="brand" href="{SITE}">OpenBioNews</a>',
             "<h1>This week in biopharma records</h1>",
             f'<p class="sub">{html.escape(label)} · every item links to its official record · '
             f'<a href="./">latest and all weeks</a> · <a href="feed.xml">RSS</a></p>',
             *_week_body(brief), _footer(brief)]
    return _page(f"This week in biopharma records — {label}", "".join(parts), _description(brief),
                 url=f"{SITE}brief/{brief['end']}.html",
                 image=f"{SITE}brief/cards/{brief['end']}.png" if card else "")


def render_index(briefs: list[dict], card: bool = False) -> str:
    """The brief's front page: the latest week in full, then every week. ``card``: the
    latest week has a share image."""
    rows = "".join(
        f'<li><a href="{b["end"]}.html">{html.escape(week_label(b))}</a>'
        f'<div class="facts">' + html.escape(" · ".join(x for x in (stat(b["sections"], k) for k, _, _ in SECTIONS) if x))
        + "</div></li>"
        for b in briefs)
    intro = ("New industry Phase 3 trials, Phase 3 results, stopped trials (with the stated reason), "
             "original FDA approvals, Class I recalls and FDA notices, every item linked to its "
             "official record. Published every Monday.")
    if not briefs:
        body = (f'<a class="brand" href="{SITE}">OpenBioNews</a><h1>This week in biopharma records</h1>'
                f'<p class="sub">{intro} <a href="feed.xml">RSS</a></p>')
        return _page("This week in biopharma records — OpenBioNews", body, intro, url=f"{SITE}brief/")
    latest = briefs[0]
    parts = [f'<a class="brand" href="{SITE}">OpenBioNews</a>',
             "<h1>This week in biopharma records</h1>",
             f'<p class="sub"><b>{html.escape(week_label(latest))}</b> · {intro} '
             f'<a href="feed.xml">RSS</a> · <a href="{latest["end"]}.html">link to this week</a></p>',
             *_week_body(latest),
             f'<section id="weeks"><h2>All weeks</h2><ol class="weeks">{rows}</ol></section>',
             _footer(latest)]
    return _page("This week in biopharma records — OpenBioNews", "".join(parts), _description(latest),
                 url=f"{SITE}brief/",
                 image=f"{SITE}brief/cards/{latest['end']}.png" if card else "")


def render_feed(briefs: list[dict], cards: dict | None = None) -> str:
    """RSS, newest first. Each item's description is the week's post text (the same as
    the LinkedIn draft), so an RSS-to-social tool can post it as is. ``cards`` maps a
    week's end date to the byte size of its portrait share image, attached as the
    item's enclosure."""
    cards = cards or {}

    def esc(s):
        return html.escape(s, quote=False)
    items = []
    for b in briefs[:20]:
        when = datetime.fromisoformat(b["generated_at"].replace("Z", "+00:00"))
        link = f"{SITE}brief/{b['end']}.html"
        image = (f'<enclosure url="{SITE}brief/cards/{b["end"]}-post.png" type="image/png" length="{cards[b["end"]]}"/>'
                 if b["end"] in cards else "")
        items.append(f"<item><title>{esc('This week in biopharma records — ' + week_label(b))}</title>"
                     f"<link>{link}</link><guid isPermaLink=\"true\">{link}</guid>"
                     f"<pubDate>{format_datetime(when)}</pubDate>"
                     f"<description>{esc(render_linkedin(b))}</description>{image}</item>")
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
        return "error" not in secs.get(key, {"error": NOT_YET})

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
    if ok("sec"):
        lines.append(f"• {_n(secs['sec']['total'], 'biopharma SEC filing', 'biopharma SEC filings')}"
                     f" on deals or IPOs{examples('sec')}")
    if ok("recalls"):
        lines.append(f"• {_n(secs['recalls']['total'], 'Class I drug recall', 'Class I drug recalls')}")
    lines += ["", f"Every item links to its official record: {SITE}brief/{brief['end']}.html", "",
              "Built automatically from ClinicalTrials.gov, openFDA, the Federal Register and SEC EDGAR "
              "with OpenBioNews (free, open source). Check the record before relying on an item.",
              "", "#biotech #pharma #clinicaltrials #FDA #competitiveintelligence"]
    return "\n".join(lines)


def edition_titles(brief: dict) -> list[str]:
    """Title options for the newsletter edition: the week's numbers first, then one led
    by the largest new Phase 3 trial, then the plain series title. Facts only."""
    secs, label = brief["sections"], week_label(brief)
    short = label.rsplit(",", 1)[0]                        # "Nov 16–22"
    out = []
    parts = []
    for key, one, many in (("new_trials", "new Phase 3 trial", "new Phase 3 trials"),
                           ("stopped", "stopped", "stopped"),
                           ("approvals", "FDA approval", "FDA approvals")):
        sec = secs[key]
        if "error" not in sec and sec.get("total"):
            parts.append(f"{sec['total']} {one if sec['total'] == 1 else many}")
    if parts:
        out.append(f"{', '.join(parts)}: the week of {short}")
    new = secs["new_trials"]
    if "error" not in new and new.get("items"):
        top = new["items"][0]
        k = top.get("key") or {}
        n = next((f.split()[0] for f in top.get("facts", []) if f.endswith("participants")), "")
        if k.get("org") and n:
            cond = k.get("cond", "")
            if cond and not any(w.isupper() and len(w) > 1 for w in cond.split()):
                cond = cond.lower()                        # "myocardial infarction", but "COPD"
            what = f"{cond} trial" if cond else "Phase 3 trial"
            more = new["total"] - 1
            tail = f", and {more} more new Phase 3s" if more > 0 else ""
            out.append(f"{k['org']} starts a {n}-patient {what}{tail}: {short}")
    out.append(f"This week in biopharma records: {label}")
    return out


def render_edition(brief: dict, per_section: int = 3) -> str:
    """The week as a LinkedIn newsletter edition: a page with the article (title,
    the week in numbers, the top records per section with links, and where to read
    the rest) and a button that copies it with its formatting, ready to paste into
    LinkedIn's article editor. Not indexed; it's a working page for the author."""
    secs, label = brief["sections"], week_label(brief)
    esc = html.escape
    page_url = f"{SITE}brief/{brief['end']}.html"
    nums = "".join(f"<li>{x}</li>" for x in (stat(secs, k, html_bold=True) for k, _, _ in SECTIONS) if x)
    art = [f"<p>The week of {esc(label)} in official records: what was registered, reported, "
           f"stopped, approved and recalled. Every item links to the record itself.</p>",
           f"<h2>The week in numbers</h2><ul>{nums}</ul>"]
    for key, name, what in SECTIONS:
        sec = secs[key]
        if key == "fda_notices" or "error" in sec or not sec["items"]:
            continue
        art.append(f"<h2>{esc(name)}</h2>")
        rows = []
        for it in sec["items"][:per_section]:
            head = key_line(it).lower()     # the bold line already names company, drug, condition
            facts = " · ".join(esc(f) for f in it["facts"][1:] if f.lower() not in head)
            facts = f"{facts} · {esc(it['cite'])}" if facts else esc(it["cite"])
            note = f"<br><em>{esc(_short(it['note'], 220))}</em>" if it.get("note") else ""
            rows.append(f'<li><a href="{esc(it["url"])}"><strong>{esc(key_line(it))}</strong></a>'
                        f"<br>{facts}{note}</li>")
        more = (f'<p>Plus {sec["total"] - per_section} more in <a href="{page_url}#{key}">the full brief</a>.</p>'
                if sec["total"] > per_section else "")
        art.append(f"<ul>{''.join(rows)}</ul>{more}")
    art.append(f'<h2>Read the full week</h2><p>All {sum(s.get("total", 0) for s in secs.values() if "error" not in s)} '
               f'items with their sources: <a href="{page_url}">{page_url}</a></p>'
               f'<p>Built automatically from ClinicalTrials.gov, openFDA, the Federal Register and SEC EDGAR with '
               f'<a href="{SITE}">OpenBioNews</a>, free and open source. It also works inside AI '
               f'assistants (MCP), so they cite these records instead of guessing. Nothing here is '
               f'made up; check the linked record before relying on an item. Not investment '
               f'or medical advice.</p>')
    title = f"This week in biopharma records: {label}"
    titles = edition_titles(brief)
    body = (f'<p class="sub"><b>For the author:</b> LinkedIn → your newsletter → <b>Create new edition</b>. '
            f'Upload the cover image, paste the title, then click <b>Copy article</b> and paste into the '
            f'body. Attach the video or PDF from the weekly run in the post that shares it.</p>'
            f'<p><b>Title</b> (pick one):</p><ol>' + "".join(f"<li>{esc(t)}</li>" for t in titles) + "</ol>"
            f'<p><b>Cover image:</b> <a href="cards/{brief["end"]}.png">cards/{brief["end"]}.png</a></p>'
            f'<p><button id="copy" type="button">Copy article</button> <span id="ok"></span></p>'
            f'<section id="article">{"".join(art)}</section>'
            "<script>document.getElementById('copy').onclick=async()=>{const a=document.getElementById('article');"
            "try{await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([a.innerHTML],{type:'text/html'}),"
            "'text/plain':new Blob([a.innerText],{type:'text/plain'})})]);document.getElementById('ok').textContent='Copied.'}"
            "catch(e){const r=document.createRange();r.selectNodeContents(a);const s=getSelection();s.removeAllRanges();"
            "s.addRange(r);document.getElementById('ok').textContent='Selected: press Ctrl/Cmd+C.'}}</script>")
    page = _page(title, body, _description(brief))
    return page.replace("<head>", '<head><meta name="robots" content="noindex">', 1)


def latest_summary(brief: dict) -> dict:
    """The newest week, as slides for the site's front tile. Counts are plain text;
    records carry key words ({lead, org, what, cond, acr, extra}) so the page can pick
    the longest version that fits the tile at the visitor's screen size."""
    secs = brief["sections"]

    def items(key, n):
        return [] if "error" in secs.get(key, {"error": NOT_YET}) else secs[key]["items"][:n]

    slides = [{"text": stat(secs, k)} for k in ("new_trials", "results", "approvals", "recalls")
              if "error" not in secs[k]]
    for lead, key, n in (("New Phase 3", "new_trials", 2), ("Results", "results", 2),
                         ("Approved", "approvals", 4), ("Stopped", "stopped", 2),
                         ("SEC", "sec", 2)):
        for i in items(key, n):
            k = i.get("key") or {"what": _short(i["title"], 60)}
            slides.append({"lead": lead, **{f: v for f, v in k.items() if v}})
    return {"end": brief["end"], "label": week_label(brief), "url": f"{brief['end']}.html",
            "slides": slides}


def render_sitemap(briefs: list[dict]) -> str:
    """The site's pages for search engines: the app, the brief index and every week."""
    urls = [(SITE, ""), (f"{SITE}brief/", briefs[0]["generated_at"][:10] if briefs else "")]
    urls += [(f"{SITE}brief/{b['end']}.html", b["generated_at"][:10]) for b in briefs]
    rows = "".join(f"<url><loc>{html.escape(u)}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>"
                   for u, d in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>\n')


def write_site(out: Path, sitemap: Path | None = None) -> list[dict]:
    """Rebuild every page from data/*.json. ``sitemap``: where to write sitemap.xml
    (the site root); main() passes docs/sitemap.xml for the published site."""
    briefs = sorted((with_all_sections(json.loads(p.read_text("utf-8"))) for p in (out / "data").glob("*.json")),
                    key=lambda b: b["end"], reverse=True)
    cards = {b["end"]: (out / "cards" / f"{b['end']}-post.png").stat().st_size for b in briefs
             if (out / "cards" / f"{b['end']}-post.png").exists()}
    for b in briefs:
        (out / f"{b['end']}.html").write_text(
            render_week(b, card=(out / "cards" / f"{b['end']}.png").exists()), "utf-8")
    (out / "index.html").write_text(
        render_index(briefs, card=bool(briefs) and (out / "cards" / f"{briefs[0]['end']}.png").exists()),
        "utf-8")
    (out / "feed.xml").write_text(render_feed(briefs, cards), "utf-8")
    if briefs:   # the newest week as a LinkedIn newsletter edition, ready to paste
        (out / f"{briefs[0]['end']}-edition.html").write_text(render_edition(briefs[0]), "utf-8")
    if sitemap:
        sitemap.write_text(render_sitemap(briefs), "utf-8")
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
    write_site(out, sitemap=out.parent / "sitemap.xml" if out == OUT else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
