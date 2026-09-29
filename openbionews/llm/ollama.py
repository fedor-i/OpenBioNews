"""Summarizer backed by a local Ollama server.

Fully free and private: the model runs on the user's own machine. Install
Ollama, ``ollama pull llama3.2`` (or any small model), and OpenBioNews talks to
it at http://localhost:11434. Nothing leaves the computer.
"""

from __future__ import annotations

from ..models import Cluster
from .base import Backend, build_prompt, system_prompt
from ._http import LLMError, post_json


class OllamaBackend(Backend):
    supports_significance = True
    name = "ollama"

    def __init__(self, cfg: dict) -> None:
        super().__init__(cfg)
        self.base_url = (cfg.get("base_url") or "http://localhost:11434").rstrip("/")
        self.model = cfg.get("model") or "llama3.2"
        self.temperature = float(cfg.get("temperature", 0.3))
        self.max_tokens = int(cfg.get("max_tokens", 220))
        self.timeout = int(cfg.get("timeout", 120))

    @property
    def label(self) -> str:
        return f"Ollama ({self.model})"

    def available(self) -> tuple[bool, str]:
        # A lightweight reachability probe against the tags endpoint.
        import urllib.error
        import urllib.request

        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5):
                return True, f"Ollama reachable at {self.base_url}, model {self.model}"
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            return False, f"Ollama not reachable at {self.base_url}: {exc}"

    def summarize(self, cluster: Cluster, significance: bool = False) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
            "messages": [
                {"role": "system", "content": system_prompt(significance)},
                {"role": "user", "content": build_prompt(cluster)},
            ],
        }
        data = post_json(url, payload, timeout=self.timeout)
        try:
            return data["message"]["content"].strip()
        except (KeyError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {exc}") from exc
