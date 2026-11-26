"""Offline tests for the weekly brief (tools/weekly_brief.py).

The brief is published to the site and drafted for LinkedIn, so its filters must
hold: generics and supplements stay out of "new approvals", routine paperwork stays
out of FDA notices, and a source that couldn't be reached reads as "unavailable",
never as "none this week". Runs on canned payloads, no network.

Runs with pytest (``pytest``) or directly (``python tests/test_brief.py``).
"""

from __future__ import annotations

import sys
import tempfile
import xml.dom.minidom
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import weekly_brief as wb  # noqa: E402
from openbionews.httputil import HTTPJSONError  # noqa: E402

START, END = date(2026, 11, 16), date(2026, 11, 22)


def _study(nct, title, sponsor="Acme", n=500, status="RECRUITING", why=None,
           drugs=("Semaglutide", "Placebo"), acronym=None):
    st = {"overallStatus": status}
    if why:
        st["whyStopped"] = why
    ident = {"nctId": nct, "briefTitle": title}
    if acronym:
        ident["acronym"] = acronym
    return {"protocolSection": {
        "identificationModule": ident,
        "armsInterventionsModule": {"interventions": [{"name": d} for d in drugs]},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor}},
        "designModule": {"enrollmentInfo": {"count": n}},
        "conditionsModule": {"conditions": ["Obesity"]},
        "statusModule": st}}


APPROVALS = {"results": [
    {"application_number": "NDA200001", "sponsor_name": "NUVALENT",
     "openfda": {"brand_name": ["NELKARMI"], "generic_name": ["NELADALKIB"]},
     "submissions": [{"submission_type": "ORIG", "submission_status": "AP",
                      "submission_status_date": "20261117", "review_priority": "PRIORITY"}]},
    {"application_number": "ANDA300001", "sponsor_name": "GENERICO",          # generic: out
     "openfda": {"brand_name": ["METFORMIN"]},
     "submissions": [{"submission_type": "ORIG", "submission_status": "AP",
                      "submission_status_date": "20261118"}]},
    {"application_number": "NDA200002", "sponsor_name": "OLDCO",              # matched only via
     "openfda": {"brand_name": ["OLDDRUG"]},                                  # a supplement: out
     "submissions": [{"submission_type": "ORIG", "submission_status": "AP",
                      "submission_status_date": "20190101"},
                     {"submission_type": "SUPPL", "submission_status": "AP",
                      "submission_status_date": "20261119"}]},
    {"application_number": "NDA200003", "sponsor_name": "NOBRAND",            # no brand name
     "products": [{"active_ingredients": [{"name": "EXAMPLINE"}]}],
     "submissions": [{"submission_type": "ORIG", "submission_status": "AP",
                      "submission_status_date": "20261120"}]},
]}
RECALLS = {"results": [{"recall_number": "D-0001-2027", "recalling_firm": "Firm <b>X</b>",
                        "product_description": "Injectable <script>alert(1)</script>",
                        "status": "Ongoing", "reason_for_recall": "Sterility."}]}
FEDREG = {"results": [
    {"title": "Agency Information Collection Activities; Submission for OMB Review",
     "type": "Notice", "publication_date": "2026-11-18", "document_number": "2026-1",
     "html_url": "https://www.federalregister.gov/d/2026-1"},
    {"title": "Oncology Drugs Advisory Committee; Notice of Meeting", "type": "Notice",
     "publication_date": "2026-11-19", "document_number": "2026-2",
     "html_url": "https://www.federalregister.gov/d/2026-2"}]}


def _router(fail_ct=False):
    def fake(url, params=None, **kw):
        if "clinicaltrials.gov" in url:
            if fail_ct:
                raise HTTPJSONError("HTTP 503 from clinicaltrials.gov")
            adv = (params or {}).get("filter.advanced", "")
            if "StudyFirstPostDate" in adv:
                return {"totalCount": 2, "studies": [_study("NCT1", "Big obesity trial", "Novo", 9000, acronym="STEP 9"),
                                                     _study("NCT2", "Small trial", "Lilly", 300)]}
            if "ResultsFirstPostDate" in adv:
                return {"totalCount": 0, "studies": []}
            return {"totalCount": 1, "studies": [_study("NCT3", "Stopped trial", "Pfizer",
                                                        status="TERMINATED", why="Futility")]}
        if "drugsfda" in url:
            return APPROVALS
        if "enforcement" in url:
            return RECALLS
        if "federalregister" in url:
            return FEDREG
        raise AssertionError(f"unexpected URL {url}")
    return fake


def _collect(**kw):
    orig = wb.get_json
    wb.get_json = _router(**kw)
    try:
        return wb.collect(START, END)
    finally:
        wb.get_json = orig


def test_key_words_pick_company_drug_and_condition():
    assert wb.short_org("Janssen Research & Development, LLC") == "Janssen"
    assert wb.short_org("Bellus Health Inc. - a GSK company") == "Bellus Health"
    assert wb.short_org("Genzyme Corp A Sanofi Co") == "Genzyme"
    assert wb.key_drug(["Azithromycin Oral Tablet", "Placebo"]) == "Azithromycin"
    assert wb.key_drug(["Intervention 1", "Control"]) == ""          # no real drug named
    assert wb.key_drug(["Pirtobrutinib", "Venetoclax", "Rituximab"]) == "Pirtobrutinib + Venetoclax"
    assert wb.key_cond("Depressive Disorder, Major") == "Major Depressive Disorder"
    item = _collect()["sections"]["new_trials"]["items"][0]
    assert wb.key_line(item) == "Novo: Semaglutide · Obesity (STEP 9)"


def test_last_full_week():
    assert wb.last_full_week(date(2026, 11, 25)) == (START, END)   # Wednesday
    assert wb.last_full_week(date(2026, 11, 23)) == (START, END)   # the Monday it runs
    assert wb.last_full_week(date(2026, 11, 22)) == (date(2026, 11, 9), date(2026, 11, 15))


def test_approvals_keep_only_original_branded_approvals_in_the_week():
    items = _collect()["sections"]["approvals"]["items"]
    cites = [i["cite"] for i in items]
    assert cites == ["NDA200001", "NDA200003"]              # priority first; no ANDA, no supplement
    assert items[0]["title"] == "Nelkarmi" and "priority review" in items[0]["facts"]
    assert items[1]["title"] == "NDA200003"                 # no brand: the number, not "Nda200003"


def test_trial_sections_and_stopped_reason():
    secs = _collect()["sections"]
    assert [i["cite"] for i in secs["new_trials"]["items"]] == ["NCT1", "NCT2"]
    assert secs["new_trials"]["items"][0]["note"] == ""     # notes only for stopped trials
    assert secs["results"]["total"] == 0
    assert secs["stopped"]["items"][0]["note"] == "Terminated: Futility"


def test_fda_notices_drop_routine_paperwork():
    titles = [i["title"] for i in _collect()["sections"]["fda_notices"]["items"]]
    assert titles == ["Oncology Drugs Advisory Committee; Notice of Meeting"]


def test_unreachable_source_reads_as_unavailable_not_none():
    brief = _collect(fail_ct=True)
    page = wb.render_week(brief)
    assert "couldn't be reached" in page and "new Phase 3 trials: unavailable" in page
    draft = wb.render_linkedin(brief)
    assert "Phase 3" not in draft.split("Every item")[0]    # no made-up counts in the draft
    assert "FDA approvals" in draft


def test_pages_escape_record_text_and_feed_is_valid_xml():
    brief = _collect()
    page = wb.render_week(brief)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        (out / "data").mkdir()
        import json
        (out / "data" / f"{END}.json").write_text(json.dumps(brief), "utf-8")
        briefs = wb.write_site(out)
        assert len(briefs) == 1 and (out / f"{END}.html").exists()
        xml.dom.minidom.parse(str(out / "feed.xml"))       # raises if malformed
        assert "1 Class I recall" in (out / "index.html").read_text("utf-8")
        latest = json.loads((out / "latest.json").read_text("utf-8"))   # the site's front tile
        assert latest["url"] == f"{END}.html" and latest["slides"][0] == {"text": "2 new Phase 3 trials"}
        assert {"lead": "Approved", "org": "Nuvalent", "what": "Nelkarmi", "cond": "neladalkib",
                "extra": "priority review"} in latest["slides"]
        assert {"lead": "New Phase 3", "org": "Novo", "what": "Semaglutide", "cond": "Obesity",
                "acr": "STEP 9"} in latest["slides"]


def test_linkedin_draft_is_plain_facts_with_correct_plurals():
    draft = wb.render_linkedin(_collect())
    assert "2 new industry Phase 3 trials" in draft and "1 industry Phase 3 trial marked" in draft
    assert "2 original FDA approvals (NDA/BLA), 1 with priority review" in draft
    assert "1 Class I drug recall\n" in draft
    assert f"brief/{END}.html" in draft


def test_sitemap_and_feed_carry_the_share_images():
    brief = _collect()
    import json
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "brief"
        (out / "data").mkdir(parents=True)
        (out / "data" / f"{END}.json").write_text(json.dumps(brief), "utf-8")
        wb.write_site(out, sitemap=Path(tmp) / "sitemap.xml")
        page = (out / f"{END}.html").read_text("utf-8")
        assert f'content="{wb.SITE}og.png"' in page            # no card yet: site-wide image
        assert f'rel="canonical" href="{wb.SITE}brief/{END}.html"' in page
        assert "<enclosure" not in (out / "feed.xml").read_text("utf-8")
        (out / "cards").mkdir()
        (out / "cards" / f"{END}.png").write_bytes(b"png")
        (out / "cards" / f"{END}-post.png").write_bytes(b"pngpng")
        wb.write_site(out, sitemap=Path(tmp) / "sitemap.xml")
        assert f'content="{wb.SITE}brief/cards/{END}.png"' in (out / f"{END}.html").read_text("utf-8")
        feed = (out / "feed.xml").read_text("utf-8")
        xml.dom.minidom.parseString(feed)
        assert f'brief/cards/{END}-post.png" type="image/png" length="6"' in feed
        assert "2 new industry Phase 3 trials" in feed           # the post text, ready to share
        sm = xml.dom.minidom.parse(str(Path(tmp) / "sitemap.xml"))
        locs = [n.firstChild.data for n in sm.getElementsByTagName("loc")]
        assert locs == [wb.SITE, f"{wb.SITE}brief/", f"{wb.SITE}brief/{END}.html"]


def test_share_card_shows_counts_names_and_unavailable_sources():
    import brief_card as bc
    brief = _collect()
    brief["sections"]["recalls"] = {"error": "HTTP 503"}
    for kind in ("card", "post"):
        page = bc.card_html(brief, kind)
        w, h = bc.SIZES[kind]
        assert f"width:{w}px;height:{h}px" in page
        assert "<b>2</b><span>New Phase 3 trials</span>" in page
        assert "Class I recalls: unavailable" in page              # never shown as zero
        assert "Nuvalent · Nelkarmi" in page and "priority review" in page
        assert "<script>alert(1)</script>" not in page             # record text is escaped
    assert bc.card_html(brief, "post").count("<li>") > bc.card_html(brief, "card").count("<li>")


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {name}")
            except AssertionError as exc:
                failed += 1
                print(f"  FAIL {name}: {exc}")
    print("all passed" if not failed else f"{failed} failed")
    sys.exit(1 if failed else 0)
