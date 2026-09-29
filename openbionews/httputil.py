"""Minimal JSON-over-HTTP GET helper (standard library only).

Shared by primary-source connectors. Keeps the zero-dependency promise.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "OpenBioNews/0.3 (+https://github.com/fedor-i/OpenBioNews)"


class HTTPJSONError(Exception):
    """Raised when a JSON endpoint cannot be reached or returns bad data."""


def get_json(url: str, params: dict | None = None, timeout: int = 30,
             headers: dict | None = None, not_found_ok: bool = False,
             raw_query: str = "") -> dict:
    """GET a URL and parse JSON.

    ``not_found_ok`` returns ``{}`` on HTTP 404 instead of raising — openFDA
    signals "no matches" with a 404. ``raw_query`` appends an already-encoded
    query string (for APIs like openFDA whose ``+AND+`` operators must not be
    re-encoded); it is combined with ``params`` when both are given.
    """
    query_parts = []
    if params:
        clean = {k: v for k, v in params.items() if v not in (None, "", [])}
        if clean:
            query_parts.append(urllib.parse.urlencode(clean, doseq=True))
    if raw_query:
        query_parts.append(raw_query)
    if query_parts:
        url = f"{url}?{'&'.join(query_parts)}"
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and not_found_ok:
            return {}
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
