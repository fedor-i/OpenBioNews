"""Optional semantic relevance ranking (classical ML — no LLM).

Scores how semantically close each record is to a query using TF-IDF + Latent
Semantic Analysis (TruncatedSVD), a deterministic, local, CPU-only technique. This
is the only part of OpenBioNews that uses a third-party package, so it lives behind
the optional ``[ml]`` extra and is imported lazily — ``import`` fails cleanly with a
helpful message when scikit-learn isn't installed, and the caller falls back to the
built-in lexical relevance.

Like every ranking here, it only *orders records that already exist and cite
themselves* — it generates no text and asserts no new facts.
"""

from __future__ import annotations

try:  # pragma: no cover - the ImportError path is exercised via the fallback
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError as exc:  # re-raise with an actionable message
    raise ImportError(
        "Semantic ranking needs the optional 'scikit-learn' package. Install it with:\n"
        "    pip install \"openbionews[ml]\""
    ) from exc


def semantic_scores(query: str, docs: list[str]) -> list[float]:
    """Cosine similarity (0–1) of each doc to ``query`` in LSA space.

    Deterministic: the randomized SVD is pinned with ``random_state=0``. On a corpus
    too small for a meaningful low-rank projection it falls back to raw TF-IDF cosine.
    """
    if not docs:
        return []
    corpus = [query] + list(docs)
    tfidf = TfidfVectorizer(stop_words="english", max_features=4096)
    matrix = tfidf.fit_transform(corpus)
    # LSA only helps once there are enough docs/terms to project; otherwise use TF-IDF.
    n_components = min(128, matrix.shape[1] - 1, matrix.shape[0] - 1)
    if n_components >= 2:
        reduced = TruncatedSVD(n_components=n_components, random_state=0).fit_transform(matrix)
        sims = cosine_similarity(reduced[0:1], reduced[1:])[0]
    else:
        sims = cosine_similarity(matrix[0:1], matrix[1:])[0]
    return [max(0.0, min(1.0, float(s))) for s in sims]
