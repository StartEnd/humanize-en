# Releasing `humanize-en` (TestPyPI dry-run + PyPI checklist)

This document is the **release runbook**. It is intentionally
narrow: it covers the mechanics of cutting an alpha, dry-running
on TestPyPI, and promoting to PyPI. It does **not** cover the
benchmark/quality gates (those live in `docs/benchmarks.md`) or
the user-facing changelog (that lives in `CHANGELOG.md`).

Status when first written: cutting `0.1.0a1` (the first wheel
intended for TestPyPI). `humanize-core` is still pre-release and
local-only; the [§2 quirks](#2-pre-release-quirks-while-humanize-core-is-local-only)
section covers what to do until it ships.

## 0. One-time setup (per machine)

```bash
# uv is all you need — it builds and publishes.
# https://docs.astral.sh/uv/
brew install uv   # or: curl -LsSf https://astral.sh/uv/install.sh | sh

# TestPyPI + PyPI credentials. Create an API token (not your password).
#   https://test.pypi.org/manage/account/token/    →  scope = "Entire account"
#   https://pypi.org/manage/account/token/         →  scope = project-specific after first release
# Supply at publish time via: UV_PUBLISH_TOKEN=pypi-… uv publish …
# (never store the token in the repo or shell history)
```

## 1. Pre-flight checklist

Every release. Skip nothing — these are cheap and the failure
modes are expensive.

- [ ] Working tree is clean: `git status` shows no unstaged
      changes; current branch is `main` (or a release branch).
- [ ] `pyproject.toml` `version` matches the version you intend
      to ship (see [PEP 440][pep440] — `0.1.0a1`, `0.1.0`,
      `0.1.0.post1`, etc).
- [ ] `humanize_en/__init__.py` `__version__` matches.
- [ ] `LICENSE` exists at the repo root and is referenced in
      `pyproject.toml` (`license = { text = "MIT" }`).
- [ ] `README.md` renders cleanly on the PyPI preview
      (no broken images; relative `docs/` links are OK on
      GitHub but PyPI will show them as 404 — that's expected).
- [ ] `CHANGELOG.md` has a dated entry for this version.
- [ ] Full test suite is green:
      ```bash
      uv run pytest --no-cov -q                       # 282 tests, ~4 s
      uv run pytest tests/bench --no-cov -q           # 11 + 3 skips (no LLM / no GPU)
      uv run pytest -q --cov=humanize_en              # coverage report
      ```
- [ ] Ruff is clean:
      ```bash
      uv run ruff check .
      uv run ruff format --check .
      ```
- [ ] CLI smoke check (covers entry-point discovery):
      ```bash
      uv run humanize-en --version
      uv run humanize-en detect README.md          # any markdown file works
      uv run humanize-en providers
      uv run humanize-en ui &                      # check GET / returns HTML
      sleep 2 && curl -sf http://127.0.0.1:8765/ | grep -q humanize-en && echo OK
      kill %1
      ```
- [ ] Auto-generated docs are in sync:
      ```bash
      uv run python scripts/gen_rules_doc.py --check     # docs/rules.md
      ```

## 2. Pre-release quirks (while humanize-core is local-only)

`pyproject.toml` currently contains:

```toml
[tool.uv.sources]
humanize-core = { path = "../humanize-core", editable = true }
```

This is **fine for development** (uv resolves the sibling working
copy) and is **ignored by hatchling at build time** (it only
emits the PEP 621 `dependencies` table into the wheel
`METADATA`). But pip / TestPyPI installers will resolve
`humanize-core>=0.1.0a1` from PyPI, so:

- **TestPyPI dry-run.** Upload `humanize-core` to TestPyPI
  first, then upload `humanize-en` to TestPyPI. The TestPyPI
  index resolves both packages by name, so the
  `[tool.uv.sources]` table never enters the picture for the
  installer. **Do not** strip the table from the source tree —
  developers still need it.
- **Real PyPI release.** Same ordering: ship `humanize-core`
  to PyPI first. Until that happens, `pip install humanize-en`
  from PyPI will fail with `No matching distribution found for
  humanize-core>=…`, which is the right error message.

If you absolutely must ship `humanize-en` before `humanize-core`
is on TestPyPI (we don't recommend this), bump the
`humanize-core>=0.1.0a1` constraint to a version that already
exists on the index you are targeting, or remove the dependency
temporarily and document the manual install step in the release
notes. **Do not** ship a wheel that no installer can resolve.

## 3. Build

```bash
# Clean the previous artifacts.
rm -rf dist/

# Build sdist + wheel (hatchling backend, configured in pyproject.toml).
uv build
```

Expected output:

```
dist/
├── humanize_en-0.1.0a1-py3-none-any.whl
└── humanize_en-0.1.0a1.tar.gz
```

### 3.1 Manifest sanity check

The trained n-gram artefacts live in `humanize_en/_lang/en/data/`.
They are pulled in by `[tool.hatch.build.targets.wheel.force-include]`,
but verify before every upload — a missing data file means a
silent-but-broken n-gram score at runtime.

```bash
unzip -l dist/humanize_en-*.whl | grep '_lang/en/data'
# Expect at least: freq_table.json, calibration.json, manifest.json
```

```bash
tar -tzf dist/humanize_en-*.tar.gz | grep -E 'pyproject|LICENSE|README'
# Expect: pyproject.toml, LICENSE, README.md present in the sdist.
```

### 3.2 Local install smoke

Install the freshly-built wheel into a **throwaway venv** —
not the project's uv venv. This catches missing-data /
missing-entry-point bugs that an editable install would mask.

```bash
uv venv /tmp/he-smoke --python 3.12
uv pip install --python /tmp/he-smoke/bin/python \
    "humanize-core[ui]>=0.1.0a1" dist/humanize_en-*.whl
/tmp/he-smoke/bin/humanize-en --version        # sanity
/tmp/he-smoke/bin/humanize-en detect README.md # data files reachable?
/tmp/he-smoke/bin/python -c "
from humanize_en.web.app import app
routes = {r.path for r in app.routes if hasattr(r, 'path')}
assert '/' in routes and '/htmx/detect' in routes
print('HTMX routes OK:', sorted(r for r in routes if r.startswith('/htmx')))
"
rm -rf /tmp/he-smoke
```

## 4. TestPyPI dry-run

```bash
# Publish humanize-core first (humanize-en depends on it).
UV_PUBLISH_TOKEN=pypi-… uv publish \
    --publish-url https://test.pypi.org/legacy/ \
    /path/to/humanize-core/dist/humanize_core-*.whl \
    /path/to/humanize-core/dist/humanize_core-*.tar.gz

# Then publish humanize-en.
UV_PUBLISH_TOKEN=pypi-… uv publish \
    --publish-url https://test.pypi.org/legacy/ \
    dist/*
```

Then re-run the smoke install from TestPyPI (this is the **real**
test, not the wheel-from-local-disk smoke in §3.2):

```bash
uv venv /tmp/he-testpypi --python 3.12
uv pip install --python /tmp/he-testpypi/bin/python \
    --index-url       https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    'humanize-en[ui]'
/tmp/he-testpypi/bin/humanize-en --version
/tmp/he-testpypi/bin/humanize-en detect README.md
/tmp/he-testpypi/bin/humanize-en providers
/tmp/he-testpypi/bin/python -c "
from humanize_en.web.app import app
routes = {r.path for r in app.routes if hasattr(r,'path')}
assert '/htmx/detect' in routes; print('UI routes OK')
"
rm -rf /tmp/he-testpypi
```

If any of those four commands fails, **stop**: the published
artefact is broken. Yank it from TestPyPI (TestPyPI allows
yanks; only Project Owners can delete) and fix the root cause
before retrying with a bumped version (`0.1.0a2` etc — PyPI
disallows re-uploading the same version even after a yank).

## 5. Promote to PyPI

Only after every checkbox in §1–§4 is ticked.

```bash
# Upload humanize-core to real PyPI first (same ordering as TestPyPI).
UV_PUBLISH_TOKEN=pypi-… uv publish \
    /path/to/humanize-core/dist/humanize_core-*.whl \
    /path/to/humanize-core/dist/humanize_core-*.tar.gz

# Then humanize-en.
UV_PUBLISH_TOKEN=pypi-… uv publish dist/*
```

Then tag and push:

```bash
git tag -a v0.1.0a1 -m "humanize-en 0.1.0a1 — first PyPI alpha"
git push origin v0.1.0a1
```

## 6. Post-release

- [ ] Update `README.md` install line if the install command
      changes (e.g. when `humanize-core` lands on PyPI and
      `[tool.uv.sources]` becomes a dev-only convenience).
- [ ] Bump `humanize_en/__init__.py` `__version__` and
      `pyproject.toml` `version` to the *next* unreleased
      number with the `.dev0` suffix
      (`0.1.0a2.dev0`) so unintentional uploads of
      build artefacts from `main` don't collide with the
      shipped version.
- [ ] Drop a short note in the linked plan-tracker (e.g.
      `docs/plan.md` §10 status table) so contributors know
      which version corresponds to which milestone.

## 7. References

[pep440]: https://peps.python.org/pep-0440/

- [PEP 440 — Version Identification][pep440] — controls how
  TestPyPI and PyPI sort the alpha (`a1`, `b1`, `rc1`, …)
  suffixes. Get this wrong and `pip install humanize-en`
  silently grabs an older final release in preference to your
  alpha.
- [TestPyPI: using `--extra-index-url`](https://packaging.python.org/en/latest/guides/using-testpypi/)
  — TestPyPI is **not** a complete mirror of PyPI; transitive
  deps must come from the main index.
- [Hatchling: force-include](https://hatch.pypa.io/latest/config/build/#forced-inclusion)
  — how we ship the `_lang/en/data/` artefacts inside the wheel.
