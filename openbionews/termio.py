"""Terminal I/O helpers.

Making stdout/stderr UTF-8 so the box-drawing characters, check marks and arrows
the CLI prints never raise ``UnicodeEncodeError`` on Windows, where a redirected
or piped stream defaults to the locale code page (often cp1252).

This is safe to call more than once and from any entry point (the CLI, the setup
wizard, or ``doctor``), so output is correct however the code is invoked.
"""

from __future__ import annotations

import sys


def force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
