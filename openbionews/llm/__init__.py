"""Pluggable summarizer backends.

A backend turns a cluster of related articles into a short, neutral blurb.
Three are shipped:

* ``none``   — deterministic, no network, no model (default).
* ``openai`` — any OpenAI-compatible ``/chat/completions`` endpoint.
* ``ollama`` — a local model served by Ollama.

All three implement the same tiny interface (see ``base.Backend``), so the rest
of the pipeline never cares which one is in use.
"""

from __future__ import annotations

from .base import Backend
from .nollm import NoLLMBackend
from .ollama import OllamaBackend
from .openai_compat import OpenAICompatBackend


def get_backend(cfg: dict) -> Backend:
    """Build the backend named by ``cfg['llm']['backend']``."""
    llm = cfg.get("llm", {})
    backend = (llm.get("backend") or "none").lower()
    if backend == "openai":
        return OpenAICompatBackend(llm)
    if backend == "ollama":
        return OllamaBackend(llm)
    return NoLLMBackend(llm)


__all__ = [
    "Backend",
    "NoLLMBackend",
    "OpenAICompatBackend",
    "OllamaBackend",
    "get_backend",
]
