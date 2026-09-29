"""The backend interface plus a shared prompt builder."""

from __future__ import annotations

from ..models import Cluster

SYSTEM_PROMPT = (
    "You are a concise news editor. Write a neutral, factual one- or two-sentence "
    "summary of the story below for a daily digest. Use only the information "
    "provided; do not speculate, editorialize, or invent facts. No preamble, no "
    "headline — just the summary sentence(s)."
)

# Used when the user turns on "why it matters" (LLM backends only).
SYSTEM_PROMPT_SIGNIFICANCE = (
    "You are a concise news editor. From the story below, write exactly two short "
    "sentences for a daily digest: first a neutral factual summary, then a second "
    "sentence beginning 'Why it matters: ' explaining the significance in plain "
    "terms. Use only the information provided; do not speculate or invent facts. "
    "No preamble, no headline."
)


def system_prompt(significance: bool = False) -> str:
    return SYSTEM_PROMPT_SIGNIFICANCE if significance else SYSTEM_PROMPT


def build_prompt(cluster: Cluster) -> str:
    """Assemble the user prompt text from a cluster's articles."""
    canonical = cluster.canonical
    lines = [f"Headline: {canonical.title}"]
    if cluster.sources:
        lines.append("Reported by: " + ", ".join(cluster.sources))
    seen: set[str] = set()
    details: list[str] = []
    for item in cluster.items:
        snippet = item.summary.strip()
        if snippet and snippet not in seen:
            seen.add(snippet)
            details.append(snippet)
    if details:
        lines.append("Article text:")
        lines.extend(f"- {d}" for d in details[:4])
    return "\n".join(lines)


class Backend:
    """Common base. Subclasses implement ``summarize`` and ``available``."""

    name = "base"

    def __init__(self, cfg: dict | None = None) -> None:
        self.cfg = cfg or {}

    @property
    def label(self) -> str:
        return self.name

    def available(self) -> tuple[bool, str]:
        """Return (ok, message). Used by ``openbionews doctor``."""
        return True, "ready"

    def summarize(self, cluster: Cluster, significance: bool = False) -> str:
        raise NotImplementedError
