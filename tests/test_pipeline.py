"""Tests for the OpenBioNews pipeline.

Runs with pytest (`pytest`) or directly (`python tests/test_pipeline.py`) — the
bottom of the file executes every test_* function without pytest installed.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openbionews import compose, config, fetch, pipeline, render, textutil
from openbionews.llm.base import Backend
from openbionews.llm.nollm import NoLLMBackend
from openbionews.models import Item

RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>T</title>
<item><title>Alpha drug approved by regulators</title>
<link>https://ex.com/a</link><description>&lt;p&gt;First sentence. Second one here.&lt;/p&gt;</description>
<pubDate>Mon, 29 Sep 2025 13:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM_SAMPLE = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>T</title>
<entry><title>Beta trial results published</title>
<link rel="alternate" href="https://ex.com/b"/>
<summary>Some summary text.</summary>
<published>2025-09-29T10:00:00Z</published></entry></feed>"""


def test_strip_html():
    assert textutil.strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert textutil.strip_html("a &amp; b") == "a & b"
    assert textutil.strip_html(None) == ""


def test_first_sentences():
    text = "One. Two. Three. Four."
    assert textutil.first_sentences(text, count=2) == "One. Two."


def test_jaccard():
    a = textutil.token_set("FDA approves CRISPR gene therapy")
    b = textutil.token_set("FDA clears CRISPR gene therapy today")
    assert textutil.jaccard(a, b) > 0.5
    assert textutil.jaccard(a, textutil.token_set("")) == 0.0


def test_parse_rss():
    items = fetch.parse_feed(RSS_SAMPLE, "Src", "biotech")
    assert len(items) == 1
    it = items[0]
    assert it.title == "Alpha drug approved by regulators"
    assert it.link == "https://ex.com/a"
    assert "First sentence." in it.summary
    assert it.published is not None and it.published.year == 2025
    assert it.topic == "biotech"


def test_parse_atom():
    items = fetch.parse_feed(ATOM_SAMPLE, "Src", "science")
    assert len(items) == 1
    assert items[0].link == "https://ex.com/b"
    assert items[0].published.hour == 10


def _item(title, link, hours_ago=1, summary="", source="S", topic="t"):
    return Item(
        title=title, link=link, summary=summary, source=source, topic=topic,
        published=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )


def test_filter_age_and_dedup():
    items = [
        _item("Fresh story", "https://ex.com/1", hours_ago=1),
        _item("Old story", "https://ex.com/2", hours_ago=100),
        _item("Fresh story dup", "https://ex.com/1?utm=x", hours_ago=1),  # same link
    ]
    kept = pipeline.filter_items(items, {"max_age_hours": 48})
    links = [i.link for i in kept]
    assert "https://ex.com/1" in links
    assert "https://ex.com/2" not in links       # too old
    assert len(kept) == 1                          # dup collapsed


def test_filter_keywords():
    items = [
        _item("Cancer breakthrough", "https://ex.com/1"),
        _item("Sports result", "https://ex.com/2"),
    ]
    inc = pipeline.filter_items(items, {"include_keywords": ["cancer"]})
    assert len(inc) == 1 and inc[0].link == "https://ex.com/1"
    exc = pipeline.filter_items(items, {"exclude_keywords": ["sports"]})
    assert len(exc) == 1 and exc[0].link == "https://ex.com/1"


def test_clustering_merges_similar():
    items = [
        _item("FDA approves CRISPR gene therapy for sickle cell", "https://ex.com/1", source="A"),
        _item("FDA clears CRISPR gene therapy for sickle cell disease", "https://ex.com/2", source="B"),
        _item("Completely unrelated wearable sensor news", "https://ex.com/3", source="C"),
    ]
    clusters = pipeline.cluster_items(items, threshold=0.5)
    sizes = sorted(len(c.items) for c in clusters)
    assert sizes == [1, 2]
    big = max(clusters, key=lambda c: len(c.items))
    assert set(big.sources) == {"A", "B"}


def test_rank_and_limit():
    titles = [
        "Regulators approve novel diabetes medication",
        "Volcano erupts near coastal fishing village",
        "Telescope captures distant spiral galaxy image",
        "Startup unveils battery recycling breakthrough",
        "Marathon runner sets unexpected world record",
    ]
    items = [_item(t, f"https://ex.com/{i}") for i, t in enumerate(titles)]
    clusters = pipeline.cluster_items(items, threshold=0.5)
    assert len(clusters) == 5  # all distinct stories
    ranked = pipeline.rank_clusters(clusters)
    limited = pipeline.limit_clusters(ranked, max_items=3, max_per_topic=0)
    assert len(limited) == 3


def test_nollm_summary():
    c = pipeline.cluster_items(
        [_item("Headline", "https://ex.com/1", summary="Lead sentence here. More detail after.")],
        threshold=0.5,
    )[0]
    blurb = NoLLMBackend().summarize(c)
    assert "Lead sentence here." in blurb


class _BoomBackend(Backend):
    name = "boom"
    supports_significance = True

    def summarize(self, cluster, significance=False):
        raise RuntimeError("simulated failure")


def test_compose_falls_back_on_error():
    # An LLM only adds the "why it matters" note; if that call fails, the run
    # still yields the deterministic cited body and records a warning.
    clusters = pipeline.cluster_items(
        [_item("H", "https://ex.com/1", summary="Fallback works. Yes.")], threshold=0.5
    )
    digest, warnings = compose.compose(
        clusters, _BoomBackend(), {"title": "T"}, want_significance=True
    )
    cluster = digest.clusters[0]
    assert cluster.significance == ""            # the failed note is dropped
    assert any("Fallback works." in c.text for c in cluster.claims)  # facts survive
    assert len(warnings) == 1


def test_llm_significance_note():
    """An LLM adds a labelled 'why it matters' note on top of the cited facts."""
    class _WhyBackend(Backend):
        name = "why"
        supports_significance = True
        def summarize(self, cluster, significance=False):
            return "A trial. Why it matters: it could change standard of care."

    clusters = pipeline.cluster_items(
        [_item("Big Story", "https://ex.com/1", summary="A big development happened.")],
        threshold=0.5,
    )
    digest, warnings = compose.compose(
        clusters, _WhyBackend(), {"title": "T"}, want_significance=True
    )
    c = digest.clusters[0]
    assert c.significance == "it could change standard of care."
    assert warnings == []
    md = render.render(digest, "markdown")
    assert "Why it matters" in md and "AI analysis" in md
    html = render.render(digest, "html")
    assert 'class="sig"' in html
    # No-LLM backend produces no note.
    d2, _ = compose.compose(clusters, NoLLMBackend(), {"title": "T"}, want_significance=True)
    assert d2.clusters[0].significance == ""


def test_render_formats():
    clusters = pipeline.cluster_items(
        [_item("Big Story", "https://ex.com/1", summary="Summary text.")], threshold=0.5
    )
    digest, _ = compose.compose(clusters, NoLLMBackend(), {"title": "My Digest"})
    md = render.render(digest, "markdown")
    assert "# My Digest" in md and "Big Story" in md
    html = render.render(digest, "html")
    assert "<!doctype html>" in html and "Big Story" in html
    txt = render.render(digest, "text")
    assert "Big Story" in txt


def test_therapeutic_area_presets():
    from openbionews import sources
    assert "oncology" in sources.THERAPEUTIC_AREAS
    conds = sources.area_conditions(["oncology", "rare_disease", "nope"])
    assert "cancer" in conds and "cystic fibrosis" in conds
    # Deduped and order-preserving; unknown keys ignored.
    assert len(conds) == len(set(conds))
    assert sources.area_conditions([]) == []


def test_render_rss():
    from xml.etree import ElementTree as ET
    from openbionews.connectors.clinicaltrials import parse_studies
    from openbionews.compose import compose as compose_fn
    clusters = pipeline.cluster_items(parse_studies(CT_FIXTURE), threshold=0.5)
    digest, _ = compose_fn(clusters, NoLLMBackend(), {"title": "My Feed", "intro": "hi"})
    xml = render.render(digest, "rss")
    root = ET.fromstring(xml)                    # must be well-formed
    assert root.tag == "rss" and root.get("version") == "2.0"
    channel = root.find("channel")
    assert channel.findtext("title") == "My Feed"
    items = channel.findall("item")
    assert items, "feed should contain items"
    assert items[0].findtext("link") == "https://clinicaltrials.gov/study/NCT01234567"
    desc = items[0].findtext("description") or ""
    assert "Sources:" in desc and "[1]" in desc   # numbered per-sentence citations
    assert items[0].findtext("category") == "Clinical Trials"


def test_config_roundtrip(tmp_path=None):
    import tempfile
    d = tmp_path or Path(tempfile.mkdtemp())
    p = d / "c.json"
    cfg = config.default_config()
    config.save_config(cfg, p)
    loaded = config.load_config(p)
    assert loaded["profile"]["title"] == cfg["profile"]["title"]
    assert config.validate_config(loaded) == []


def test_wizard_writes_config(tmp_path=None):
    """Drive the interactive wizard with scripted answers."""
    import builtins
    import tempfile
    from openbionews import setup_wizard

    d = tmp_path or Path(tempfile.mkdtemp())
    p = d / "wiz.json"

    answers = iter([
        "My Test Brief",   # title
        "A subtitle",       # intro
        "1",                # bundles -> biotech
        "n",                # add own feed?
        "n",                # track ClinicalTrials.gov? -> no
        "cancer",           # include keywords
        "",                 # exclude keywords
        "24",               # max age
        "1",                # summaries -> none (no why-it-matters prompt follows)
        "1",                # output format -> markdown
        "digest",           # output folder
        "n",                # email the digest? -> no
    ])

    orig_input = builtins.input
    orig_isatty = sys.stdin.isatty
    builtins.input = lambda *a: next(answers)
    sys.stdin.isatty = lambda: True
    try:
        cfg = setup_wizard.run_wizard(path=p)
    finally:
        builtins.input = orig_input
        sys.stdin.isatty = orig_isatty

    assert p.exists()
    assert cfg["profile"]["title"] == "My Test Brief"
    assert cfg["filters"]["include_keywords"] == ["cancer"]
    assert cfg["filters"]["max_age_hours"] == 24
    assert cfg["llm"]["backend"] == "none"


def test_importance_ranking():
    """A multi-source story with fresh, salient headline outranks a lone old one."""
    now = datetime.now(timezone.utc)
    big_a = _item("FDA approves new therapy", "https://ex.com/1", hours_ago=1, source="A")
    big_b = _item("FDA approves new therapy today", "https://ex.com/2", hours_ago=1, source="B")
    small = _item("Local gardening club meets weekly", "https://ex.com/3", hours_ago=1, source="C")
    clusters = pipeline.cluster_items([big_a, big_b, small], threshold=0.5)
    ranked = pipeline.rank_clusters(clusters)
    assert len(ranked[0].sources) == 2  # the corroborated FDA story is first
    assert pipeline.importance_score(ranked[0], now) > pipeline.importance_score(ranked[-1], now)


def test_read_minutes():
    from openbionews.compose import compose as compose_fn
    clusters = pipeline.cluster_items(
        [_item("A headline here", "https://ex.com/1", summary="Word " * 400)], threshold=0.5
    )
    digest, _ = compose_fn(clusters, NoLLMBackend(), {"title": "T"})
    assert digest.read_minutes >= 1


def test_significance_prompt_selection():
    from openbionews.llm import base
    assert "Why it matters" in base.system_prompt(True)
    assert "Why it matters" not in base.system_prompt(False)


def test_mailer_configured_and_message():
    from openbionews import mailer
    from openbionews.compose import compose as compose_fn
    assert not mailer.is_configured({"enabled": True, "smtp_host": ""})
    cfg = {
        "enabled": True, "smtp_host": "smtp.example.com", "from_addr": "me@example.com",
        "to_addrs": ["you@example.com"], "smtp_port": 587,
    }
    assert mailer.is_configured(cfg)
    clusters = pipeline.cluster_items([_item("H", "https://ex.com/1", summary="Body.")], threshold=0.5)
    digest, _ = compose_fn(clusters, NoLLMBackend(), {"title": "My Digest"})
    msg = mailer.build_message(digest, "<p>hi</p>", "hi", cfg)
    assert msg["To"] == "you@example.com"
    assert "My Digest" in msg["Subject"]
    assert msg.get_content_type() == "multipart/alternative"


CT_FIXTURE = {
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT01234567",
                                          "briefTitle": "Study of DrugX in Advanced Solid Tumors"},
                "statusModule": {"overallStatus": "RECRUITING",
                                  "lastUpdatePostDateStruct": {"date": "2026-09-20"}},
                "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Acme Bio"}},
                "conditionsModule": {"conditions": ["Melanoma"]},
                "armsInterventionsModule": {"interventions": [{"name": "DrugX"}]},
                "designModule": {"phases": ["PHASE2"]},
                "descriptionModule": {"briefSummary": "A phase 2 study. It evaluates DrugX. Safety measured."},
            }
        },
        {  # missing NCT id -> should be skipped
            "protocolSection": {"identificationModule": {"briefTitle": "No id"}}
        },
    ]
}


def test_clinicaltrials_parse():
    from openbionews.connectors.clinicaltrials import parse_studies
    items = parse_studies(CT_FIXTURE)
    assert len(items) == 1  # the id-less study is skipped
    it = items[0]
    assert it.link == "https://clinicaltrials.gov/study/NCT01234567"
    assert it.source == "ClinicalTrials.gov"
    assert it.age_exempt is True
    assert it.tag == "Recruiting · Phase 2 · Acme Bio"
    assert it.citations and it.citations[0].url == it.link
    assert it.meta["conditions"] == ["Melanoma"]


def test_clinicaltrials_query_building():
    from openbionews.connectors.clinicaltrials import ClinicalTrialsConnector
    conn = ClinicalTrialsConnector(
        {"recent_days": 30},
        {"sponsors": ["Acme Bio"], "conditions": ["Melanoma"], "interventions": [], "terms": [""]},
    )
    pairs = conn._queries()
    assert ("query.spons", "Acme Bio") in pairs
    assert ("query.cond", "Melanoma") in pairs
    assert all(v.strip() for _, v in pairs)  # blank term dropped
    ok, _ = conn.available()
    assert ok is True
    # No watch list -> unavailable
    empty = ClinicalTrialsConnector({}, {})
    assert empty.available()[0] is False


def test_connector_registry_and_age_exempt():
    from openbionews.connectors import get_connectors
    cfg = config.default_config()
    assert get_connectors(cfg) == []  # disabled by default
    cfg["connectors"]["clinicaltrials"]["enabled"] = True
    cfg["watchlist"]["sponsors"] = ["Acme Bio"]
    assert len(get_connectors(cfg)) == 1
    # An age-exempt item survives an aggressive age filter.
    from openbionews.connectors.clinicaltrials import parse_studies
    old = parse_studies(CT_FIXTURE)  # dated 2026-09-20, likely older than 1h
    kept = pipeline.filter_items(old, {"max_age_hours": 1})
    assert len(kept) == 1


FDA_FIXTURE = {"results": [{
    "recalling_firm": "Acme Pharma", "product_description": "Metformin 500mg tablets",
    "reason_for_recall": "Nitrosamine impurity above limit.", "classification": "Class II",
    "status": "Ongoing", "report_date": "20260910", "recall_number": "D-1234-2026",
    "openfda": {"brand_name": ["Glucophage"]},
}]}

SEC_FIXTURE = {"hits": {"total": {"value": 2}, "hits": [{
    "_id": "0001682852-26-000045:mrna-8k.htm",
    "_source": {"ciks": ["0001682852"], "root_form": "8-K", "file_date": "2026-09-20",
                "display_names": ["Moderna, Inc. (MRNA) (CIK 0001682852)"],
                "file_description": "Current report"},
}]}}


def test_openfda_parse():
    from openbionews.connectors.openfda import parse_enforcement
    items = parse_enforcement(FDA_FIXTURE)
    assert len(items) == 1
    it = items[0]
    assert it.title == "Glucophage"
    assert it.tag == "Class II · Ongoing · Acme Pharma"
    assert it.source == "openFDA (Drug Recalls)"
    assert it.age_exempt and it.published.year == 2026
    assert it.citations and "D-1234-2026" in it.citations[0].url


def test_openfda_query():
    from openbionews.connectors.openfda import OpenFDAConnector
    c = OpenFDAConnector({"recent_days": 30, "classifications": ["Class I", "Class II"]},
                         {"sponsors": ["Acme Pharma"]})
    raw = c._build_raw_query("recalling_firm", "Acme Pharma")
    assert 'recalling_firm:"Acme%20Pharma"' in raw
    assert "report_date:[" in raw and "+AND+" in raw
    assert "OR classification" in raw.replace("%20", " ")
    assert c.available()[0] is True


APPROVAL_FIXTURE = {"results": [{
    "application_number": "BLA761399", "sponsor_name": "HELIX THERAPEUTICS",
    "openfda": {"brand_name": ["HELYXA"], "generic_name": ["hlx-car19"]},
    "products": [{"brand_name": "HELYXA", "dosage_form": "SUSPENSION", "route": "INTRAVENOUS"}],
    "submissions": [
        {"submission_type": "ORIG", "submission_number": "1", "submission_status": "AP",
         "submission_status_date": "20260926", "review_priority": "PRIORITY"},
        {"submission_type": "SUPPL", "submission_number": "2", "submission_status": "AP",
         "submission_status_date": "20200101"},   # too old — filtered by cutoff
        {"submission_type": "ORIG", "submission_number": "0", "submission_status": "TENT",
         "submission_status_date": "20260926"},    # not approved — skipped
    ],
}]}


def test_openfda_approvals_parse():
    from datetime import timedelta
    from openbionews.connectors.openfda_approvals import parse_approvals
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    items = parse_approvals(APPROVAL_FIXTURE, cutoff=cutoff)
    assert len(items) == 1                      # only the recent approved ORIG
    it = items[0]
    assert it.title == "Helyxa — FDA approval"  # brand title-cased
    assert "New approval" in it.tag and "Priority review" in it.tag
    assert it.source == "openFDA (Drug Approvals)" and it.topic == "fda_approvals"
    assert it.age_exempt and it.published.day == 26
    assert "accessdata.fda.gov" in it.citations[0].url and "761399" in it.citations[0].url


def test_openfda_approvals_query_and_registry():
    from openbionews.connectors.openfda_approvals import OpenFDAApprovalsConnector
    from openbionews.connectors import get_connectors
    c = OpenFDAApprovalsConnector({"recent_days": 90},
                                  {"sponsors": ["Helix"], "interventions": ["car-t"]})
    exprs = c._entity_exprs()
    assert any(e.startswith('sponsor_name:') for e in exprs)
    raw = c._raw_query(exprs[0])
    assert 'submissions.submission_status:"AP"' in raw and "submission_status_date:[" in raw
    assert c.available()[0] is True
    cfg = config.default_config()
    cfg["connectors"]["openfda_approvals"]["enabled"] = True
    cfg["watchlist"]["sponsors"] = ["Helix"]
    assert any(x.name == "openFDA (Drug Approvals)" for x in get_connectors(cfg))


SHORTAGE_FIXTURE = {"results": [{
    "generic_name": "Amoxicillin", "company_name": "Generic Pharma Co",
    "status": "Current", "reason_for_shortage": "Demand increase.",
    "therapeutic_category": ["Anti-Infective"], "update_date": "2026-09-18",
}]}


def test_openfda_shortages_parse_and_query():
    from openbionews.connectors.openfda_shortages import parse_shortages, OpenFDAShortagesConnector
    from openbionews.connectors import get_connectors
    it = parse_shortages(SHORTAGE_FIXTURE)[0]
    assert it.title == "Amoxicillin — shortage (Current)"
    assert it.tag == "Current · Anti-Infective · Generic Pharma Co"
    assert it.source == "openFDA (Drug Shortages)" and it.topic == "fda_shortages" and it.age_exempt
    assert "dps.fda.gov/drugshortages" in it.citations[0].url
    c = OpenFDAShortagesConnector({"statuses": ["Current"]}, {"interventions": ["amoxicillin"]})
    raw = c._raw_query(c._entity_exprs()[0])
    assert 'status:"Current"' in raw and "generic_name" in raw
    assert c.available()[0] is True
    cfg = config.default_config()
    cfg["connectors"]["openfda_shortages"]["enabled"] = True
    assert any(x.name == "openFDA (Drug Shortages)" for x in get_connectors(cfg))


def test_edgar_parse():
    from openbionews.connectors.edgar import parse_hits
    items = parse_hits(SEC_FIXTURE)
    assert len(items) == 1
    it = items[0]
    assert it.title == "Moderna, Inc. (MRNA) — 8-K"   # "(CIK …)" stripped
    assert it.link == "https://www.sec.gov/Archives/edgar/data/1682852/000168285226000045/mrna-8k.htm"
    assert it.source == "SEC EDGAR" and it.age_exempt
    assert it.citations[0].label.startswith("EDGAR ")


def test_edgar_params_and_ua():
    from openbionews.connectors.edgar import EdgarConnector, DEFAULT_UA
    e = EdgarConnector({"recent_days": 30, "forms": ["8-K", "S-1"]}, {"sponsors": ["Moderna"]})
    params = e._params("Moderna", 0)
    assert params["forms"] == "8-K,S-1" and params["dateRange"] == "custom"
    ok, msg = e.available()
    assert ok and "user_agent" in msg  # nudges to set a contact UA
    e2 = EdgarConnector({"user_agent": "Jane jane@x.com"}, {"terms": ["gene therapy"]})
    assert e2.user_agent != DEFAULT_UA


def test_registry_three_connectors():
    from openbionews.connectors import get_connectors
    cfg = config.default_config()
    for key in ("clinicaltrials", "openfda", "edgar"):
        cfg["connectors"][key]["enabled"] = True
    cfg["watchlist"]["sponsors"] = ["Moderna"]
    assert len(get_connectors(cfg)) == 3


def test_citation_render():
    from openbionews.connectors.clinicaltrials import parse_studies
    from openbionews.compose import compose as compose_fn
    clusters = pipeline.cluster_items(parse_studies(CT_FIXTURE), threshold=0.5)
    digest, _ = compose_fn(clusters, NoLLMBackend(), {"title": "Trials"})
    md = render.render(digest, "markdown")
    # Per-sentence citations: a numbered <sup> marker in the body and a keyed
    # source list underneath, both traced to the registry record.
    assert "↳ Sources:" in md and "NCT01234567" in md
    assert "<sup>1</sup>" in md
    html = render.render(digest, "html")
    assert "clinicaltrials.gov/study/NCT01234567" in html
    assert 'sup class="cite"' in html


def test_per_sentence_attribution():
    """Each brief sentence binds to the source it was lifted from — no LLM."""
    from openbionews import cite
    from openbionews.connectors.clinicaltrials import parse_studies
    from openbionews.compose import compose as compose_fn
    clusters = pipeline.cluster_items(parse_studies(CT_FIXTURE), threshold=0.5)
    digest, _ = compose_fn(clusters, NoLLMBackend(), {"title": "Trials"})
    cluster = digest.clusters[0]
    assert cluster.claims, "primary-source cluster should have cited claims"
    # Every claim is a verbatim sentence of a source item, and every claim with
    # a citation points at a URL that exists on one of the cluster's items.
    source_urls = {c.url for item in cluster.items for c in item.citations}
    for claim in cluster.claims:
        if claim.citation is not None:
            assert claim.citation.url in source_urls
    markers, ordered = cite.number_citations(cluster.claims)
    assert ordered and ordered[0][0] == 1   # numbering starts at 1


def test_change_detection():
    """State is remembered between runs and the diff is surfaced — no LLM."""
    import os
    import tempfile
    from openbionews import history
    from openbionews.connectors.clinicaltrials import parse_studies

    def study(status):
        return {"protocolSection": {
            "identificationModule": {"nctId": "NCT09999999", "briefTitle": "Test Study"},
            "statusModule": {"overallStatus": status,
                             "lastUpdatePostDateStruct": {"date": "2026-09-20"}},
            "descriptionModule": {"briefSummary": "A study. It has an endpoint."},
            "designModule": {"phases": ["PHASE2"]},
        }}

    sp = os.path.join(tempfile.mkdtemp(), "state.json")

    # First run: empty store, so nothing is flagged (avoids flagging everything).
    store = history.StateStore(sp).load()
    assert store.started_empty
    run1 = parse_studies({"studies": [study("RECRUITING")]})
    history.annotate(run1, store); store.save()
    assert not run1[0].meta.get("change")

    # Second run: the status moved — the diff is reported.
    store = history.StateStore(sp).load()
    assert not store.started_empty
    run2 = parse_studies({"studies": [study("TERMINATED")]})
    history.annotate(run2, store); store.save()
    assert run2[0].meta.get("change") == "Status: Recruiting → Terminated"
    assert run2[0].meta.get("change_kind") == "status"

    # Third run: unchanged — no noise.
    store = history.StateStore(sp).load()
    run3 = parse_studies({"studies": [study("TERMINATED")]})
    history.annotate(run3, store)
    assert not run3[0].meta.get("change")


def test_end_to_end_demo():
    from openbionews.demo import build_demo_digest

    rendered, digest = build_demo_digest("markdown")
    assert digest.clusters, "demo should produce stories"
    # The two sample wires share one CRISPR story; it should cluster.
    multi = [c for c in digest.clusters if len(c.sources) > 1]
    assert multi, "expected at least one multi-source cluster"
    assert "OpenBioNews" in rendered


def test_demo_covers_all_primary_sources():
    """The offline demo must showcase trials, FDA recalls and SEC filings, cited."""
    from openbionews.demo import build_demo_digest

    rendered, digest = build_demo_digest("markdown")
    topics = {c.topic for c in digest.clusters}
    assert {"clinical_trials", "fda_recalls", "fda_approvals", "fda_shortages", "sec_filings"} <= topics
    # Each primary source contributes a citation line to the output.
    assert "NCT05012345" in rendered            # ClinicalTrials.gov record
    assert "FDA recall D-0456-2026" in rendered  # openFDA recall record (Class I)
    assert "D-0461-2026" in rendered             # both recalls survive dedup
    assert "Drugs@FDA BLA761399" in rendered     # openFDA approval record
    assert "FDA Drug Shortages: Cisplatin Injection" in rendered  # shortage record
    assert "EDGAR 0001683168-26-006789" in rendered  # SEC filing
    # HTML variant renders too.
    html, _ = build_demo_digest("html")
    assert "<!doctype html>" in html


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{'all passed' if not failures else str(failures) + ' failed'}")
    sys.exit(1 if failures else 0)
