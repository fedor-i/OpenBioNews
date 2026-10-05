"""Curated default feeds, grouped into topic bundles.

The onboarding wizard offers these bundles so a new user gets a working digest
without hunting for RSS URLs. OpenBioNews leads with life-sciences coverage,
but bundles for adjacent beats are included so the tool is useful to anyone.

Every feed here is a publicly advertised RSS/Atom endpoint. If a publisher
changes or removes a feed, ``openbionews doctor`` will flag it and the user can
edit their config. Nothing here is guaranteed to stay valid forever — feeds
move — so treat this as a sensible starting point, not a fixed catalogue.
"""

from __future__ import annotations

# Each bundle maps a key -> {label, description, feeds:[{name,url}]}.
BUNDLES: dict[str, dict] = {
    "biotech": {
        "label": "Biotech & Pharma",
        "description": "Drug development, biotech companies, deals and trials.",
        "feeds": [
            {"name": "STAT News", "url": "https://www.statnews.com/feed/"},
            {"name": "Fierce Biotech", "url": "https://www.fiercebiotech.com/rss/xml"},
            {"name": "Fierce Pharma", "url": "https://www.fiercepharma.com/rss/xml"},
            {"name": "Endpoints News", "url": "https://endpts.com/feed/"},
            {"name": "BioPharma Dive", "url": "https://www.biopharmadive.com/feeds/news/"},
            {"name": "BioSpace", "url": "https://www.biospace.com/rss/news/"},
        ],
    },
    "regulatory": {
        "label": "Regulatory (FDA / EMA)",
        "description": "Approvals, recalls and official agency announcements.",
        "feeds": [
            {"name": "FDA Press Releases",
             "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml"},
            {"name": "FDA Drug Approvals & Safety",
             "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/drugs/rss.xml"},
            {"name": "EMA News", "url": "https://www.ema.europa.eu/en/rss.xml"},
        ],
    },
    "preprints": {
        "label": "Preprints (bioRxiv / medRxiv)",
        "description": "Newest un-peer-reviewed life-science and medical research.",
        "feeds": [
            {"name": "bioRxiv (all subjects)",
             "url": "https://connect.biorxiv.org/biorxiv_xml.php?subject=all"},
            {"name": "medRxiv (all subjects)",
             "url": "https://connect.medrxiv.org/medrxiv_xml.php?subject=all"},
        ],
    },
    "life_science": {
        "label": "Life Science & Research",
        "description": "Genomics, molecular biology and academic research news.",
        "feeds": [
            {"name": "ScienceDaily Biotechnology",
             "url": "https://www.sciencedaily.com/rss/plants_animals/biotechnology.xml"},
            {"name": "ScienceDaily Genetics",
             "url": "https://www.sciencedaily.com/rss/plants_animals/genetics.xml"},
            {"name": "Phys.org Biology",
             "url": "https://phys.org/rss-feed/biology-news/"},
            {"name": "Nature — Latest",
             "url": "https://www.nature.com/nature.rss"},
        ],
    },
    "health": {
        "label": "Health & Medicine",
        "description": "Public health, clinical care and medical policy.",
        "feeds": [
            {"name": "MedicalXpress", "url": "https://medicalxpress.com/rss-feed/"},
            {"name": "NPR Health",
             "url": "https://feeds.npr.org/103537970/rss.xml"},
            {"name": "WHO News",
             "url": "https://www.who.int/rss-feeds/news-english.xml"},
        ],
    },
    "science": {
        "label": "General Science",
        "description": "Broad science and discovery coverage.",
        "feeds": [
            {"name": "ScienceDaily Top",
             "url": "https://www.sciencedaily.com/rss/top/science.xml"},
            {"name": "Phys.org", "url": "https://phys.org/rss-feed/"},
            {"name": "Quanta Magazine", "url": "https://www.quantamagazine.org/feed/"},
        ],
    },
    "tech": {
        "label": "Technology",
        "description": "Startups, software and the wider tech industry.",
        "feeds": [
            {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
            {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
            {"name": "Hacker News (front page)", "url": "https://hnrss.org/frontpage"},
        ],
    },
    "world": {
        "label": "World News",
        "description": "General world and headline news.",
        "feeds": [
            {"name": "NPR News", "url": "https://feeds.npr.org/1001/rss.xml"},
            {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
        ],
    },
}

# Bundles pre-selected for the OpenBioNews default profile.
DEFAULT_BUNDLES = ["biotech", "regulatory", "life_science"]


# Therapeutic-area presets: one-tap watch lists of conditions/indications for the
# primary-source connectors (trials, FDA, SEC). Each condition is a plain search
# term that ClinicalTrials.gov, openFDA and EDGAR all understand.
THERAPEUTIC_AREAS: dict[str, dict] = {
    "oncology": {
        "label": "Oncology",
        "conditions": ["cancer", "oncology", "lymphoma", "melanoma"],
    },
    "cardiometabolic": {
        "label": "Cardiometabolic",
        "conditions": ["type 2 diabetes", "obesity", "heart failure", "cardiovascular disease"],
    },
    "rare_disease": {
        "label": "Rare disease",
        "conditions": ["rare disease", "cystic fibrosis", "sickle cell disease", "muscular dystrophy"],
    },
    "neurology": {
        "label": "Neurology",
        "conditions": ["Alzheimer disease", "Parkinson disease", "multiple sclerosis", "epilepsy"],
    },
    "immunology": {
        "label": "Immunology & inflammation",
        "conditions": ["rheumatoid arthritis", "psoriasis", "inflammatory bowel disease", "lupus"],
    },
    "infectious": {
        "label": "Infectious disease",
        "conditions": ["HIV", "hepatitis", "influenza", "tuberculosis"],
    },
}


# Thematic groups: cut across therapeutic areas by *modality, approach or
# company cohort* rather than disease. Each seeds free-text search terms (and,
# where the theme is a recognisable company cohort, lead-sponsor names) that
# ClinicalTrials.gov, openFDA and EDGAR all understand. This is how a user says
# "track AI-in-drug-discovery" or "new approach methodologies", not a disease.
THEMES: dict[str, dict] = {
    "ai": {
        "label": "AI in drug discovery",
        "terms": ["artificial intelligence", "machine learning", "deep learning",
                  "AI drug discovery", "generative model"],
        "sponsors": ["Recursion Pharmaceuticals", "Exscientia", "Insilico Medicine",
                     "Schrodinger", "Absci", "BenevolentAI", "Isomorphic Labs",
                     "Relay Therapeutics"],
    },
    "nam": {
        "label": "New Approach Methodologies (NAM)",
        "terms": ["new approach methodologies", "organ-on-a-chip",
                  "microphysiological systems", "organoid", "in vitro model",
                  "non-animal testing"],
        "sponsors": ["Emulate", "CN Bio", "Hesperos"],
    },
    "gene_cell": {
        "label": "Gene & cell therapy",
        "terms": ["gene therapy", "cell therapy", "CAR-T", "AAV", "lentiviral"],
        "sponsors": ["CRISPR Therapeutics", "Intellia Therapeutics", "Beam Therapeutics",
                     "Sarepta Therapeutics", "bluebird bio"],
    },
    "crispr": {
        "label": "Gene editing (CRISPR)",
        "terms": ["CRISPR", "gene editing", "base editing", "prime editing"],
        "sponsors": ["CRISPR Therapeutics", "Intellia Therapeutics",
                     "Beam Therapeutics", "Editas Medicine", "Prime Medicine"],
    },
    "mrna": {
        "label": "mRNA & RNA therapeutics",
        "terms": ["mRNA", "messenger RNA", "siRNA", "antisense oligonucleotide", "RNA therapeutic"],
        "sponsors": ["Moderna", "BioNTech", "Alnylam Pharmaceuticals", "Ionis Pharmaceuticals"],
    },
    "adc": {
        "label": "Antibody-drug conjugates",
        "terms": ["antibody-drug conjugate", "ADC", "bispecific antibody"],
        "sponsors": ["Seagen", "ADC Therapeutics", "Daiichi Sankyo", "ImmunoGen"],
    },
    "radiopharma": {
        "label": "Radiopharmaceuticals",
        "terms": ["radiopharmaceutical", "radioligand therapy", "theranostic",
                  "targeted radionuclide"],
        "sponsors": ["Novartis", "Point Biopharma", "RayzeBio", "Lantheus"],
    },
    "obesity": {
        "label": "GLP-1 / obesity",
        "terms": ["GLP-1", "obesity", "semaglutide", "tirzepatide", "weight loss"],
        "sponsors": ["Novo Nordisk", "Eli Lilly", "Amgen", "Viking Therapeutics", "Structure Therapeutics"],
    },
    "psychedelics": {
        "label": "Psychedelic medicine",
        "terms": ["psilocybin", "MDMA", "psychedelic", "ketamine"],
        "sponsors": ["Compass Pathways", "atai Life Sciences", "MindMed"],
    },
    "longevity": {
        "label": "Longevity & aging",
        "terms": ["aging", "senescence", "senolytic", "longevity"],
        "sponsors": ["Altos Labs", "Unity Biotechnology", "BioAge Labs"],
    },
}


def theme_terms(keys: list[str]) -> list[str]:
    """Flatten the free-text search terms for the given theme keys (deduped)."""
    out: list[str] = []
    for key in keys:
        theme = THEMES.get(key)
        if not theme:
            continue
        for term in theme.get("terms", []):
            if term not in out:
                out.append(term)
    return out


def theme_sponsors(keys: list[str]) -> list[str]:
    """Flatten the lead-sponsor cohort for the given theme keys (deduped)."""
    out: list[str] = []
    for key in keys:
        theme = THEMES.get(key)
        if not theme:
            continue
        for sponsor in theme.get("sponsors", []):
            if sponsor not in out:
                out.append(sponsor)
    return out


def area_conditions(keys: list[str]) -> list[str]:
    """Flatten the conditions for the given therapeutic-area keys (deduped, ordered)."""
    out: list[str] = []
    for key in keys:
        area = THERAPEUTIC_AREAS.get(key)
        if not area:
            continue
        for cond in area["conditions"]:
            if cond not in out:
                out.append(cond)
    return out


def bundle_feeds(keys: list[str]) -> list[dict]:
    """Flatten the feeds of the given bundle keys, tagging each with its topic."""
    feeds: list[dict] = []
    seen: set[str] = set()
    for key in keys:
        bundle = BUNDLES.get(key)
        if not bundle:
            continue
        for feed in bundle["feeds"]:
            url = feed["url"]
            if url in seen:
                continue
            seen.add(url)
            feeds.append({"name": feed["name"], "url": url, "topic": key})
    return feeds
