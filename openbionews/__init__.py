"""OpenBioNews — a free, self-hosted news digest builder.

Gathers developments from RSS/Atom feeds and from primary-source connectors
(ClinicalTrials.gov, openFDA recalls, SEC EDGAR), deduplicates and clusters stories,
ranks them, and composes a clean daily digest that cites its sources. Works with
no LLM at all, a local model via Ollama, or any OpenAI-compatible API. Pure
standard library — no third-party packages required for the core pipeline.
"""

__version__ = "0.3.0"
__all__ = ["__version__"]
