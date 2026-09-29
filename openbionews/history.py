"""Deterministic change detection between runs.

The highest-value signal in biopharma monitoring is not *what exists* but *what
changed*: a trial that moved to Terminated, results that were posted, a recall
that was reclassified. OpenBioNews remembers the salient state of each item —
keyed by its stable id (NCT number, recall number, EDGAR accession) — from one
run to the next, and flags the differences on the following run.

Pure standard library, and deterministic: the "what changed" line is a literal
comparison of two recorded states, so there is nothing to hallucinate and no
model involved. A connector opts in by putting the fields worth watching in
``item.meta["track"]`` (a small ``{label: value}`` dict); everything else here
is generic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Item


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class StateStore:
    """A tiny JSON key→state store, resilient to a missing or corrupt file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.data: dict[str, dict] = {}
        self.started_empty = True

    def load(self) -> "StateStore":
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data = loaded
        except Exception:
            self.data = {}
        self.started_empty = not self.data
        return self

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.data, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        except Exception:
            # Losing the state file degrades to "no change detection", never a crash.
            pass


def _tracked_fields(item: Item) -> dict[str, str]:
    """The salient state a connector wants watched, as strings."""
    track = item.meta.get("track") if isinstance(item.meta, dict) else None
    if isinstance(track, dict) and track:
        return {str(k): str(v) for k, v in track.items() if v not in (None, "")}
    # Fall back to the human status line so any item still gets basic tracking.
    return {"State": item.tag} if item.tag else {}


def _key(item: Item) -> str | None:
    ident = (item.guid or "").strip()
    if not ident:
        return None
    return f"{item.topic}:{ident}"


def annotate(items: list[Item], store: StateStore) -> list[Item]:
    """Compare each item to its last-seen state, set ``meta['change']`` /
    ``meta['change_kind']``, and record the new state. Mutates and returns items.

    On the very first run (an empty store) nothing is flagged — otherwise every
    item would read as "new". Items are recorded so the *next* run has a baseline.
    """
    first_run = store.started_empty
    for item in items:
        key = _key(item)
        if key is None:
            continue
        current = _tracked_fields(item)
        prior = store.data.get(key)

        if prior is None:
            if not first_run:
                item.meta["change"] = "New"
                item.meta["change_kind"] = "new"
            first_seen = _now_iso()
        else:
            first_seen = prior.get("first_seen", _now_iso())
            prev_fields = prior.get("fields", {}) or {}
            diffs = [
                (label, prev_fields[label], value)
                for label, value in current.items()
                if label in prev_fields and prev_fields[label] != value
            ]
            if diffs:
                item.meta["change"] = " · ".join(
                    f"{label}: {old} → {new}" for label, old, new in diffs
                )
                item.meta["change_kind"] = "status"

        store.data[key] = {
            "fields": current,
            "first_seen": first_seen,
            "last_seen": _now_iso(),
        }
    return items
