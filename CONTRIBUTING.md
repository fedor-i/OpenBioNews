# Contributing to OpenBioNews

Thanks for helping build a free, self-hosted news tool. Contributions of every
size are welcome — a typo fix, a new feed, a whole new connector.

## Ground rules

- **Zero required dependencies.** The core runs on the Python standard library
  (3.9+). Don't add a runtime dependency without discussion; optional extras go
  under `[project.optional-dependencies]`.
- **Privacy first.** The tool must never phone home. No telemetry, no analytics.
- **Everything works offline where it can.** Failures degrade gracefully — a
  dead feed is skipped, a failed LLM call falls back to no-LLM.

## Getting started

```bash
git clone https://github.com/fedor-i/OpenBioNews.git
cd OpenBioNews
python3 -m openbionews run --demo     # works offline, no install
pip install .                          # optional: install the CLI
```

## Running the tests

The suite uses only the standard library, so no install is needed:

```bash
python3 tests/test_pipeline.py         # prints ok/FAIL per test
# or, if you have pytest:
pytest
```

CI runs these on Linux, macOS and Windows across Python 3.9–3.12. Please make
sure `python3 tests/test_pipeline.py` passes before opening a PR.

**Changing a ranking weight?** The MCP server (Python) and the website
(JavaScript) implement the same scores. `tests/fixtures/ranking_vectors.json` is
the shared spec: update its expected values, change both implementations, and
run `python3 tests/test_ranking_parity.py` (needs Node for the website half).

**Live checks.** `python3 tests/live/check_live.py` calls the real APIs and checks
that every tool still gets the fields it relies on; `python3 benchmarks/run_landmarks.py`
scores salience ranking against known landmark trials. Both need the network and
run daily in CI (`.github/workflows/live.yml`), so you don't have to run them for
every PR — but do if you touch a connector or the ranking.

## Adding a primary-source connector

Connectors are the highest-value contributions. See
[`ARCHITECTURE.md`](ARCHITECTURE.md) → *Adding a primary-source connector*. In
short:

1. Add `openbionews/connectors/<name>.py` with a class extending
   `connectors.base.Connector`, a `fetch()` and an `available()`.
2. **Split parsing from fetching** (a `parse_*` function) so it can be tested
   with a fixture and no network.
3. Attach a `Citation` to every `Item` and set `age_exempt=True`.
4. Register it in `connectors/__init__.py`, add a config block in `config.py`,
   and a step in `setup_wizard.py`.
5. Add fixture-based tests.

## Adding news feeds

News feeds are optional extras (off by default) — official primary sources are
the core, so a new connector is usually the more valuable contribution. To
improve a bundle, edit `openbionews/sources.py`. Prefer official or well-known
RSS/Atom feeds, and run `openbionews doctor` to confirm the URL resolves.

## Style

- Match the surrounding code; keep functions small and documented.
- Prefer clarity over cleverness. Comment *why*, not *what*.
- Keep user-facing text plain and active-voice.

## Pull requests

- One focused change per PR.
- Update `CHANGELOG.md` under "Unreleased".
- Describe what changed and how you tested it.

By contributing, you agree your work is licensed under the project's
[MIT License](LICENSE).
