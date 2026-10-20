"""Smoke test for the MCP *server* wiring (openbionews.mcp_server.build_server).

``tests/test_mcp.py`` covers the tool *logic* with the standard library only. This
module covers the other half — that the tools actually register against the real
``mcp`` SDK and can be invoked through the server — which is exactly where an SDK
API change slips past (e.g. the mcp 1.x ``FastMCP`` → 2.x ``MCPServer`` rename).

It needs the optional ``mcp`` package, so it SKIPS cleanly (exit 0) when ``mcp``
isn't installed — keeping the stdlib-only CI green — and a dedicated CI job installs
``.[mcp]`` so the guard actually executes somewhere.

Runs with pytest (skips) or directly (``python tests/test_mcp_server.py``).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import mcp  # noqa: F401
    HAVE_MCP = True
except ImportError:
    HAVE_MCP = False

from openbionews import mcp_server
from openbionews.connectors import clinicaltrials

# canned ClinicalTrials.gov payload so the round-trip touches no network
_CT = {"studies": [{"protocolSection": {
    "identificationModule": {"nctId": "NCT0001", "briefTitle": "CRISPR base editing study"},
    "statusModule": {"overallStatus": "RECRUITING",
                     "lastUpdatePostDateStruct": {"date": "2026-10-01"}},
    "designModule": {"phases": ["PHASE3"]}}}]}


def _list_tool_names(server) -> list[str]:
    res = server.list_tools()
    tools = asyncio.run(res) if asyncio.iscoroutine(res) else res
    return [getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
            for t in tools]


def test_build_server_registers_every_tool():
    if not HAVE_MCP:
        print("SKIP: the optional 'mcp' package is not installed")
        return
    server = mcp_server.build_server()
    names = set(_list_tool_names(server))
    expected = {fn.__name__ for fn in mcp_server.TOOLS}
    assert names == expected, f"registered tools {names} != TOOLS {expected}"
    assert len(expected) == 10, "expected 10 MCP tools"


def test_server_reports_its_version():
    if not HAVE_MCP:
        print("SKIP: the optional 'mcp' package is not installed")
        return
    server = mcp_server.build_server()
    # clients display serverInfo.version; it must not be blank
    assert getattr(server, "version", "") == mcp_server.__version__


def test_tool_call_round_trips_through_the_server():
    if not HAVE_MCP:
        print("SKIP: the optional 'mcp' package is not installed")
        return
    orig = clinicaltrials.get_json
    clinicaltrials.get_json = lambda *a, **k: _CT
    try:
        server = mcp_server.build_server()
        res = server.call_tool("search_clinical_trials", {"query": "crispr", "limit": 5})
        res = asyncio.run(res) if asyncio.iscoroutine(res) else res
    finally:
        clinicaltrials.get_json = orig
    blob = json.dumps(res, default=lambda o: getattr(o, "__dict__", str(o)))
    assert "NCT0001" in blob, "cited record did not survive the server round-trip"
    assert "ClinicalTrials.gov" in blob, "source label missing from server round-trip"


if __name__ == "__main__":
    if not HAVE_MCP:
        print("SKIP: optional 'mcp' package not installed — "
              "install with `pip install \".[mcp]\"` to exercise the server wiring")
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
