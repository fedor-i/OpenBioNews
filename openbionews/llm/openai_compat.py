"""Summarizer backed by any OpenAI-compatible /chat/completions endpoint.

Works with the OpenAI API, OpenRouter, Together, Groq, LM Studio, llama.cpp's
server, vLLM and anything else that speaks the same shape. Point ``base_url`` at
the endpoint and set the API key via an environment variable (``api_key_env``);
the key is never written to the config file.
"""

from __future__ import annotations

import os

from ..models import Cluster
from .base import Backend, build_prompt, system_prompt
from ._http import LLMError, post_json


class OpenAICompatBackend(Backend):
    name = "openai-compatible"

    def __init__(self, cfg: dict) -> None:
        super().__init__(cfg)
        self.base_url = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        self.model = cfg.get("model") or "gpt-4o-mini"
        self.api_key_env = cfg.get("api_key_env") or "OPENAI_API_KEY"
        self.temperature = float(cfg.get("temperature", 0.3))
        self.max_tokens = int(cfg.get("max_tokens", 220))
        self.timeout = int(cfg.get("timeout", 60))

    @property
    def label(self) -> str:
        return f"OpenAI-compatible ({self.model})"

    def _api_key(self) -> str:
        return os.environ.get(self.api_key_env, "")

    def available(self) -> tuple[bool, str]:
        if not self._api_key():
            return False, f"environment variable ${self.api_key_env} is not set"
        return True, f"endpoint {self.base_url}, model {self.model}"

    def summarize(self, cluster: Cluster, significance: bool = False) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {}
        key = self._api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt(significance)},
                {"role": "user", "content": build_prompt(cluster)},
            ],
        }
        data = post_json(url, payload, headers=headers, timeout=self.timeout)
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {exc}") from exc
