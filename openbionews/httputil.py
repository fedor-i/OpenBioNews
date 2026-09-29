"""Minimal JSON-over-HTTP GET helper (standard library only).

Shared by primary-source connectors. Keeps the zero-dependency promise.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "OpenBioNews/0.2 (+https://github.com/fedor-i/OpenBioNews)"


class HTTPJSONError(Exception):
    """Raised when a JSON endpoint cannot be reached or returns bad data."""


def get_json(url: str, params: dict | None = None, timeout: int = 30,
             headers: dict | None = None) -> dict:
    if params:
        # doseq keeps list-valued params usable; None values are dropped.
        clean = {k: v for k, v in params.items() if v not in (None, "", [])}
        url = f"{url}?{urllib.parse.urlencode(clean, doseq=True)}"
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise HTTPJSONError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise HTTPJSONError(f"could not reach {url}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPJSONError(f"invalid JSON from {url}: {exc}") from exc
