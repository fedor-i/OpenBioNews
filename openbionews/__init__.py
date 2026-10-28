"""OpenBioNews — a free, self-hosted news digest builder.

Reads official primary sources (ClinicalTrials.gov; openFDA recalls, approvals,
shortages, adverse events and labels; the Federal Register; PubMed; SEC EDGAR) —
plus optional trade-press RSS/Atom feeds — deduplicates and clusters developments,
ranks them, and composes a clean daily brief that cites its sources. Works with
no LLM at all, a local model via Ollama, or any OpenAI-compatible API. Pure
standard library — no third-party packages required for the core pipeline. The same
connectors are also served to AI assistants as an MCP server (``openbionews[mcp]``).
"""

__version__ = "0.8.6"
__all__ = ["__version__"]
