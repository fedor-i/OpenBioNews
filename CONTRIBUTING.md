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

## Adding feeds

Edit the bundles in `openbionews/sources.py`. Prefer official or well-known
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
