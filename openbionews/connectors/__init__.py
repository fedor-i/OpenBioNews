"""Primary-source connectors.

Unlike RSS feeds (secondary trade press), a connector reads an official record —
a trial registry, a regulator, a filing system — and turns each new development
into an ``Item`` that cites the source document. This is the primary-source
model that makes OpenBioNews a genuine alternative to paid biotech-intelligence
feeds rather than a general news digest.

Each connector implements ``base.Connector``. Register new ones in
``get_connectors``.
"""

from __future__ import annotations

from .base import Connector
from .clinicaltrials import ClinicalTrialsConnector
from .edgar import EdgarConnector
from .federalregister import FederalRegisterConnector
from .openfda import OpenFDAConnector
from .openfda_approvals import OpenFDAApprovalsConnector
from .openfda_events import OpenFDAEventsConnector
from .openfda_shortages import OpenFDAShortagesConnector

_REGISTRY = {
    "clinicaltrials": ClinicalTrialsConnector,
    "openfda": OpenFDAConnector,
    "openfda_approvals": OpenFDAApprovalsConnector,
    "openfda_shortages": OpenFDAShortagesConnector,
    "openfda_events": OpenFDAEventsConnector,
    "federalregister": FederalRegisterConnector,
    "edgar": EdgarConnector,
}


def get_connectors(cfg: dict) -> list[Connector]:
    """Instantiate every enabled connector from config."""
    connectors_cfg = cfg.get("connectors", {})
    watchlist = cfg.get("watchlist", {})
    out: list[Connector] = []
    for key, cls in _REGISTRY.items():
        conf = connectors_cfg.get(key, {})
        if conf.get("enabled"):
            out.append(cls(conf, watchlist))
    return out


__all__ = [
    "Connector",
    "ClinicalTrialsConnector",
    "OpenFDAConnector",
    "OpenFDAApprovalsConnector",
    "OpenFDAShortagesConnector",
    "OpenFDAEventsConnector",
    "FederalRegisterConnector",
    "EdgarConnector",
    "get_connectors",
]
