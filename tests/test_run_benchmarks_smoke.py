"""Smoke tests for ``scripts/run_benchmarks.py``.

Pin three things:

1. **The renderer's output shape** — every run, regardless of which
   gates skip, produces the same Markdown skeleton (run-metadata
   table, gate-summary table, "Enabling each gate" footer). A
   downstream tool or wiki may rely on this layout, so a refactor
   that drops one of the section headers should fail loudly.
2. **The gate-runner contract** — each ``run_*_gate`` function
   returns a :class:`GateResult` with ``status ∈ {pass, fail,
   skipped}`` and a non-empty ``notes`` field. This keeps the
   table renderable without conditional rendering logic.
3. **End-to-end via the CLI** — invoking the script as a
   subprocess produces a valid Markdown file with the expected
   sections. Catches regressions in argument parsing /
   ``__main__`` plumbing that pure-import tests miss.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "run_benchmarks.py"


@pytest.fixture(scope="module")
def driver():
    """Import ``scripts/run_benchmarks.py`` as a module."""
    spec = importlib.util.spec_from_file_location("run_benchmarks", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_benchmarks"] = mod
    spec.loader.exec_module(mod)
    return mod


# ─── Renderer output shape ─────────────────────────────────────────────


REQUIRED_SECTIONS = (
    "# humanize-en benchmark results",
    "## Run metadata",
    "## Gate summary",
    "## Enabling each gate",
)


def test_renderer_produces_required_sections(driver) -> None:
    """A fully-skipped report (the v0.1 default) still contains every
    section header we promise downstream tools."""
    samples = driver.load_samples("bundled", n=3)
    assert samples
    # Three "skipped" results — simulates the no-deps state.
    results = [
        driver.GateResult(
            name="binoculars_drop", spec_section="§7.1",
            status="skipped", threshold=0.3, notes="test stub",
        ),
        driver.GateResult(
            name="bertscore_f1", spec_section="§7.2",
            status="skipped", threshold=0.85, notes="test stub",
        ),
        driver.GateResult(
            name="readability", spec_section="§7.3",
            status="skipped", threshold=2.0, notes="test stub",
        ),
    ]
    out = driver.render_report(
        results, source="bundled", n_samples=3,
        timestamp="2025-01-01T00:00:00+00:00",
    )
    for section in REQUIRED_SECTIONS:
        assert section in out, f"missing section header: {section!r}"


def test_renderer_per_sample_section_when_data_present(driver) -> None:
    """When a gate has ``per_sample`` rows, a detailed table appears."""
    results = [
        driver.GateResult(
            name="readability", spec_section="§7.3", status="pass",
            metric=1.5, threshold=2.0, notes="test",
            per_sample=[{"id": "x", "fkgl_before": 19.0, "fkgl_after": 17.5}],
        ),
    ]
    out = driver.render_report(
        results, source="bundled", n_samples=1,
        timestamp="2025-01-01T00:00:00+00:00",
    )
    assert "## §7.3 `readability` — per-sample" in out
    assert "fkgl_before" in out
    assert "fkgl_after" in out


def test_renderer_status_emojis(driver) -> None:
    """Gate status icons are stable so regex consumers (CI badges,
    docs scripts) can parse them."""
    results = [
        driver.GateResult(name="x", spec_section="§7.x", status="pass",
                          metric=1.0, threshold=0.5, notes=""),
        driver.GateResult(name="y", spec_section="§7.y", status="fail",
                          metric=0.1, threshold=0.5, notes=""),
        driver.GateResult(name="z", spec_section="§7.z", status="skipped",
                          notes=""),
    ]
    out = driver.render_report(
        results, source="bundled", n_samples=0,
        timestamp="2025-01-01T00:00:00+00:00",
    )
    assert "✅ pass" in out
    assert "❌ fail" in out
    assert "⏭ skipped" in out


# ─── Gate-runner contract ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "runner_name",
    ["run_binoculars_drop", "run_bertscore", "run_readability"],
)
def test_gate_runner_returns_valid_result(driver, runner_name) -> None:
    """Each ``run_*_gate`` returns a :class:`GateResult` with a valid
    ``status`` and a non-empty ``notes`` field."""
    runner = getattr(driver, runner_name)
    samples = driver.load_samples("bundled", n=2)
    result = runner(samples)
    assert isinstance(result, driver.GateResult)
    assert result.status in {"pass", "fail", "skipped"}
    assert result.spec_section.startswith("§7.")
    # Skipped results in particular MUST explain why — that's the
    # main reason readers open this file.
    if result.status == "skipped":
        assert result.notes, "skipped gates must include a non-empty notes field"


# ─── End-to-end CLI ────────────────────────────────────────────────────


def test_cli_no_autodetect_writes_canonical_report(tmp_path) -> None:
    """``--no-autodetect`` produces the deterministic alpha-state report
    regardless of what env vars the test runner happens to have set."""
    out_path = tmp_path / "bench.md"
    json_path = tmp_path / "bench.json"
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--source", "bundled",
            "--no-autodetect",
            "--out", str(out_path),
            "--json", str(json_path),
        ],
        capture_output=True, text=True, timeout=60,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"driver crashed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert out_path.exists(), "driver did not write the markdown report"
    md = out_path.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in md, f"CLI report missing section: {section!r}"

    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["source"] == "bundled"
    assert payload["n_samples"] == 12
    assert {r["name"] for r in payload["results"]} == {
        "binoculars_drop", "bertscore_f1", "readability",
    }
    # All three should be skipped under --no-autodetect (no providers,
    # no extras assumed installed in CI).
    assert all(r["status"] == "skipped" for r in payload["results"])


def test_committed_docs_benchmarks_md_exists() -> None:
    """``docs/benchmarks.md`` ships in the repo so curious readers can
    see the gate format without running anything. If this file is
    missing, ``make bench-skip-llm`` and commit the result."""
    path = REPO_ROOT / "docs" / "benchmarks.md"
    assert path.exists(), "docs/benchmarks.md missing — run `make bench-skip-llm`"
    md = path.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in md, f"docs/benchmarks.md missing: {section!r}"
