# Releasing OpenBioNews

Releases are published to [PyPI](https://pypi.org/) automatically by the
`.github/workflows/publish.yml` workflow when you publish a GitHub Release.
Authentication uses **PyPI Trusted Publishing** (OIDC) — no API token is stored
in the repository.

## One-time setup (per project, on PyPI)

1. Create the project on PyPI (or reserve the name with a first manual upload).
2. In the PyPI project → **Settings → Publishing → Add a trusted publisher**:
   - Owner: `fedor-i`
   - Repository: `OpenBioNews`
   - Workflow name: `publish.yml`
   - Environment: `pypi`
3. In GitHub → **Settings → Environments → New environment** named `pypi`
   (optionally add required reviewers to gate publishes).

## Cutting a release

1. Update the version in `pyproject.toml` and `openbionews/__init__.py`
   (they must match), following semantic versioning.
2. Move the `## [Unreleased]` notes in `CHANGELOG.md` under a new
   `## [x.y.z]` heading.
3. Commit, then tag and push:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
4. On GitHub → **Releases → Draft a new release**, choose the tag, paste the
   changelog section, and **Publish**.
5. The `Publish to PyPI` workflow builds the sdist + wheel, runs `twine check`,
   and uploads to PyPI. Confirm it appears at
   `https://pypi.org/project/openbionews/`.

## Local build check (optional)

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```
