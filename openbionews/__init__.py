"""OpenBioNews — a free, self-hosted news digest builder.

Gathers developments from RSS/Atom feeds and from primary-source connectors
(ClinicalTrials.gov; openFDA recalls, approvals, shortages, adverse events and
labels; the Federal Register; PubMed; SEC EDGAR), deduplicates and clusters stories,
ranks them, and composes a clean daily digest that cites its sources. Works with
no LLM at all, a local model via Ollama, or any OpenAI-compatible API. Pure
standard library — no third-party packages required for the core pipeline. The same
connectors are also served to AI assistants as an MCP server (``openbionews[mcp]``).
"""

__version__ = "0.8.6"
__all__ = ["__version__"]
