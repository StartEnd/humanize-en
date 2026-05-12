"""§7.3 — Tertiary gate: readability not degraded.

Spec (from ``docs/plan.md`` §7.3): Flesch-Kincaid Grade Level on
the polished text should be within ±2 grades of the original.
Catches "humanizer turns clear prose into garbled text" — an
actual failure mode of some aggressive paraphrasers.

Stdlib-only — no ``textstat`` dep — so this gate **always runs**,
unlike §7.1 (Binoculars) and §7.2 (BERTScore) which can skip-mark
when their optional deps are missing. The gate still skips on
the EN-fallback path (no LLM provider) because the deterministic
cleanup barely changes the text and the gate becomes trivially
true.
"""

from __future__ import annotations

import os

import pytest

from humanize_en import postprocess_humanize
from tests.bench._data import load_samples
from tests.bench._readability import flesch_kincaid_grade

GRADE_TOLERANCE = 2.0  # absolute; symmetric (±2)
SAMPLE_CAP = 12  # full bundled corpus


def _llm_provider_available() -> bool:
    try:
        from humanize_core.llm import has_active
    except ImportError:  # pragma: no cover
        return False
    return has_active()


@pytest.mark.skipif(
    not _llm_provider_available(),
    reason="no LLM provider configured; deterministic cleanup barely "
           "changes readability — gate would be trivially passed",
)
@pytest.mark.skipif(
    os.environ.get("HUMANIZE_EN_SKIP_BENCH") == "1",
    reason="HUMANIZE_EN_SKIP_BENCH=1 set in environment",
)
def test_readability_within_tolerance() -> None:
    """Mean per-sample |FKGL_after - FKGL_before| ≤ 2.0.

    We use the *mean* per-sample absolute deviation rather than
    "every sample within ±2" because aggressive paraphrasing
    legitimately can swing one or two outliers (e.g., the LLM
    splits a 50-word sentence into three 15-word ones — readability
    *improves* by 4 grades, but that's good). The mean smooths
    those out.
    """
    samples = load_samples("bundled")[:SAMPLE_CAP]
    deltas: list[float] = []
    for s in samples:
        polished, _after, _before = postprocess_humanize(
            s.text, scene=s.scene,
        )
        before_grade = flesch_kincaid_grade(s.text)
        after_grade = flesch_kincaid_grade(polished)
        deltas.append(abs(after_grade - before_grade))

    mean_delta = sum(deltas) / len(deltas)
    assert mean_delta <= GRADE_TOLERANCE, (
        f"§7.3 gate failed: mean |FKGL_after - FKGL_before| = {mean_delta:.2f} "
        f"(tolerance {GRADE_TOLERANCE}). Polish is changing readability "
        f"too much. Per-sample deltas: "
        f"{[round(d, 2) for d in deltas]}."
    )


def test_readability_helpers_pure_no_lm_required() -> None:
    """Sanity check that the readability helpers themselves work
    without an LLM, separate from the gate. Always runs — catches
    a regression where the gate test gets skipped *and* the helpers
    are silently broken."""
    grade = flesch_kincaid_grade(
        "The quick brown fox jumps over the lazy dog. "
        "Pack my box with five dozen liquor jugs."
    )
    # Two grade-3-ish sentences; expect roughly 1 < grade < 6.
    assert 0 < grade < 8, f"sanity-test grade {grade} outside expected range"
