"""Tests for the optional semantic ranker (openbionews.mlrank).

Needs the optional ``[ml]`` extra (scikit-learn), so it SKIPS cleanly (exit 0) when
that isn't installed — keeping the stdlib-only CI green — and a dedicated CI job
installs ``.[ml]`` so this actually executes somewhere. The stdlib fallback (when the
extra is absent) is covered in tests/test_mcp.py.

Runs with pytest (skips) or directly (``python tests/test_mlrank.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from openbionews import mlrank
    HAVE_ML = True
except ImportError:
    HAVE_ML = False


def test_semantic_scores_rank_relevant_above_irrelevant():
    if not HAVE_ML:
        print("SKIP: the optional '[ml]' extra (scikit-learn) is not installed")
        return
    query = "aspirin cardiovascular outcomes trial"
    docs = [
        "A randomized trial of aspirin for cardiovascular outcomes in adults.",  # on-topic
        "Guidelines for stage lighting and theatrical set construction.",        # off-topic
    ]
    scores = mlrank.semantic_scores(query, docs)
    assert len(scores) == 2
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores[0] > scores[1], "the on-topic doc should score higher"


def test_semantic_scores_are_deterministic():
    if not HAVE_ML:
        print("SKIP: the optional '[ml]' extra (scikit-learn) is not installed")
        return
    query = "gene therapy for sickle cell disease"
    docs = ["Base editing therapy for sickle cell disease.",
            "Quarterly earnings and share buyback program.",
            "CRISPR gene editing clinical study in hemoglobinopathies."]
    assert mlrank.semantic_scores(query, docs) == mlrank.semantic_scores(query, docs)


def test_semantic_scores_empty_docs():
    if not HAVE_ML:
        print("SKIP: the optional '[ml]' extra (scikit-learn) is not installed")
        return
    assert mlrank.semantic_scores("anything", []) == []


if __name__ == "__main__":
    if not HAVE_ML:
        print("SKIP: optional '[ml]' extra not installed — "
              "install with `pip install \".[ml]\"` to exercise semantic ranking")
        sys.exit(0)
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
