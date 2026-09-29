"""Connector interface shared by all primary-source connectors."""

from __future__ import annotations

from ..models import Item


class Connector:
    """Read an official record and yield developments as Items.

    Subclasses implement ``fetch`` and, optionally, ``available``.
    """

    name = "base"
    topic = "primary"

    def __init__(self, cfg: dict | None = None, watchlist: dict | None = None) -> None:
        self.cfg = cfg or {}
        self.watchlist = watchlist or {}

    @property
    def label(self) -> str:
        return self.name

    def available(self) -> tuple[bool, str]:
        """Return (ok, message) for ``openbionews doctor``."""
        return True, "ready"

    def fetch(self) -> list[Item]:
        raise NotImplementedError
