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



def _hit(adsh, doc, form, sics, items=None, name="Acme Therapeutics Inc  (ACME)  (CIK 0001234567)",
         date="2026-11-18"):
    src = {"ciks": ["0001234567"], "display_names": [name], "form": form, "root_form": form,
           "file_date": date, "sics": sics}
    if items is not None:
        src["items"] = items
    return {"_id": f"{adsh}:{doc}", "_source": src}


EFTS_DEALS = [
    _hit("0001234567-26-000001", "d8k.htm", "8-K", ["2834"], ["1.01", "9.01"]),
    _hit("0001234567-26-000001", "ex10-1.htm", "8-K", ["2834"], ["1.01", "9.01"]),   # its exhibit
    _hit("0009999999-26-000002", "d8k.htm", "8-K", ["7372"], ["1.01"],
         name="Software Co  (SOFT)  (CIK 0009999999)"),                                # not biopharma
    _hit("0001234567-26-000003", "d8k.htm", "8-K", ["2836"], ["5.02"]),               # exec change
    _hit("0001234567-26-000004", "d8ka.htm", "8-K/A", ["2836"], ["1.01"]),            # amendment
    _hit("0007777777-26-000005", "d8k.htm", "8-K", ["2834"], ["1.01"],
         name="Greenland Mines Ltd  (GRML)  (CIK 0007777777)"),                       # a miner
    _hit("0008888888-26-000006", "d8k.htm", "8-K", ["2834"], ["1.01"],
         name="Smallcap Bio Inc  (SCB)  (CIK 0008888888)", date="2026-11-21"),        # a financing
]
# The wording searches that tell what kind of agreement each 8-K is about.
EFTS_TYPES = {'"license agreement"': ["0001234567-26-000001"],
              '"securities purchase agreement"': ["0008888888-26-000006"]}
EFTS_IPOS = [
    _hit("0005555555-26-000010", "ds1.htm", "S-1", ["2836"], name="NewBio Inc  (CIK 0005555555)",
         date="2026-11-20"),
    _hit("0005555555-26-000011", "ds1a.htm", "S-1/A", ["2836"], name="OtherBio Inc  (CIK 0005555556)"),
]


EFTS_FAIL: dict = {}      # form -> how many more times EDGAR answers it with a 500


def _efts(params):
    form = params.get("forms", "")
    if EFTS_FAIL.get(form):
        EFTS_FAIL[form] -= 1
        raise HTTPJSONError(f"HTTP 500 from efts.sec.gov ({form})")
    if form in ("S-1", "F-1"):
        assert params.get("q") == '"initial public offering"'
        hits = [h for h in EFTS_IPOS if h["_source"]["form"].startswith(form)]
    elif params.get("q") in EFTS_TYPES:
        hits = [{"_id": f"{adsh}:ex.htm", "_source": {}} for adsh in EFTS_TYPES[params["q"]]]
    else:
        hits = EFTS_DEALS if "material definitive" in params.get("q", "") else []
    return {"hits": {"total": {"value": len(hits)}, "hits": hits}}


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
        if "efts.sec.gov" in url:
            assert "@" in kw.get("headers", {}).get("User-Agent", ""), "SEC needs a contact email"
            return _efts(params or {})
        raise AssertionError(f"unexpected URL {url}")
    return fake


def _collect(ua="OpenBioNews-test test@example.com", **kw):
    import os
    orig, orig_ua, orig_sleep = wb.get_json, os.environ.get("OPENBIONEWS_EDGAR_UA"), wb.time.sleep
    wb.get_json, wb.time.sleep = _router(**kw), (lambda s: None)
    if ua is None:
        os.environ.pop("OPENBIONEWS_EDGAR_UA", None)
    else:
        os.environ["OPENBIONEWS_EDGAR_UA"] = ua
    try:
        return wb.collect(START, END)
    finally:
        wb.get_json, wb.time.sleep = orig, orig_sleep
        if orig_ua is None:
            os.environ.pop("OPENBIONEWS_EDGAR_UA", None)
        else:
            os.environ["OPENBIONEWS_EDGAR_UA"] = orig_ua


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


def test_reel_picks_overviews_then_records_per_feed():
    import brief_reel as br
    slides = ([{"feed": "brief", "kind": "week"}] + [{"feed": "brief", "kind": "brief"}] * 4
              + [{"feed": "stopped", "kind": "sum"}] + [{"feed": "stopped", "kind": "rec"}] * 4
              + [{"feed": "recalls", "kind": "rec"}] * 2)
    assert br.pick_slides(slides, 3) == [0, 1, 5, 6, 7, 10, 11]   # at most 2 overviews
    frame = br.frame_html(b"png", "", "Nov 16–22, 2026", 1, 3, ["brief", "stopped"], "stopped")
    assert "<b>Stopped Phase 3 · 30 days</b>" in frame and frame.count('<i class="') == 3


def test_newsletter_edition_is_paste_ready_and_not_indexed():
    page = wb.render_edition(_collect())
    assert '<meta name="robots" content="noindex">' in page and "Copy article" in page
    assert "<h2>The week in numbers</h2>" in page and "<b>2</b> new Phase 3 trials" in page
    assert f"brief/{END}.html" in page and "<script>alert(1)</script>" not in page.split("<script>document")[0]
    titles = wb.edition_titles(_collect())
    assert titles[0].startswith("2 new Phase 3 trials, 1 stopped, 2 FDA approvals: the week of Nov 16")
    assert titles[-1] == "This week in biopharma records: Nov 16–22, 2026"
    assert all(t in page for t in titles[:1])


def test_sec_section_keeps_biopharma_deals_and_ipos_once_each():
    sec = _collect()["sections"]["sec"]
    assert sec["total"] == 3, sec                             # the miner is left out
    deal, ipo, fin = sec["items"]                             # licensing, then IPOs, then financings
    assert ipo["title"] == "NewBio Inc: filed to go public (S-1)" and ipo["facts"][-1] == "filed 2026-11-20"
    assert fin["title"] == "Smallcap Bio Inc: signed a financing agreement"
    assert deal["title"] == "Acme Therapeutics Inc: signed a licensing or collaboration agreement"
    assert deal["key"] == {"org": "Acme", "what": "Signed a licensing or collaboration agreement",
                           "acr": "ACME", "extra": "licensing"}
    assert "8-K Item 1.01" in deal["facts"] and deal["cite"] == "0001234567-26-000001"
    assert deal["url"] == ("https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/"
                           "0001234567-26-000001-index.htm")


def test_sec_retries_a_server_error_then_keeps_what_it_has():
    EFTS_FAIL.clear()
    EFTS_FAIL["S-1"] = 1                                  # one 500, then fine: retried
    sec = _collect()["sections"]["sec"]
    assert sec["total"] == 3 and "note" not in sec
    EFTS_FAIL["S-1"] = 9                                  # keeps failing: deals stay, note says so
    sec = _collect()["sections"]["sec"]
    EFTS_FAIL.clear()
    assert [i["title"] for i in sec["items"]] == ["Acme Therapeutics Inc: signed a licensing or collaboration agreement",
                                                  "Smallcap Bio Inc: signed a financing agreement"]
    assert "S-1 IPO filings" in sec["note"]
    brief = _collect()
    brief["sections"]["sec"] = sec
    assert "S-1 IPO filings; those may be missing." in wb.render_week(brief)
    EFTS_FAIL.update({"8-K": 9, "S-1": 9, "F-1": 9})       # nothing answers: unavailable
    sec = _collect()["sections"]["sec"]
    EFTS_FAIL.clear()
    assert "HTTP 500" in sec["error"]


def test_sec_without_a_contact_email_reads_as_unavailable():
    brief = _collect(ua=None)
    assert "contact email" in brief["sections"]["sec"]["error"]
    assert wb.stat(brief["sections"], "sec") == "SEC deals and IPO filings: unavailable"
    assert "biopharma SEC filing" not in wb.render_linkedin(brief)


def test_sec_format_change_is_an_error_not_an_empty_week():
    hits = [{"_id": "0001-26-1:a.htm", "_source": {"form": "8-K", "items": ["1.01"]}}]
    try:
        wb.parse_sec_hits(hits, "deal")
    except HTTPJSONError as exc:
        assert "industry codes" in str(exc)
    else:
        raise AssertionError("missing sics should raise, not return an empty week")


def test_weeks_before_the_sec_section_still_render():
    brief = _collect()
    del brief["sections"]["sec"]
    wb.with_all_sections(brief)
    page = wb.render_week(brief)
    assert "Not part of the brief yet that week." in page and "unavailable" not in page.split("<section")[0]


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
