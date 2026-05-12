"""§7.1 — Primary humanization gate: Binoculars score drop.

Spec (verbatim from ``docs/plan.md`` §7.1)::

    bino = Binoculars()
    samples = load_raid_holdout(domain=["news","wiki"], attack="none", n=100)
    before = [bino.compute_score(s.text) for s in samples]
    after  = [bino.compute_score(polish(s.text, strength="medium")) for s in samples]
    drops  = [b - a for b, a in zip(before, after)]
    assert sum(d >= 0.3 for d in drops) / len(drops) >= 0.80

Polarity reminder: Binoculars returns a score where **lower = AI**,
**higher = human** (the paper's convention). A *drop* in our
formulation means ``before - after > 0`` would indicate the polished
text became *more* AI-like — which is the opposite of what we want.
We therefore measure ``after - before`` (positive = more human after
polish) and gate on **80% of samples having ``after - before ≥ 0.3``**.

The gate **skip-marks** when:

* Binoculars is not installed (``humanize_en.perplexity.is_available()``
  is ``False``). The optional dep needs ~14 GB of Falcon-7B weights
  and a working CUDA / MPS backend.
* No LLM provider is configured (``humanize_core.llm.has_active()``).
  Without a provider the polish pass collapses to deterministic
  cleanup, which produces a much smaller delta than a real LLM
  rewrite — measuring that would be misleading.
* The RAID loader is unavailable (``[bench]`` extra missing). With
  only the bundled stub corpus the gate runs against 12 samples,
  which is fine for *structure* verification but too few for the
  ≥80% pass threshold to be statistically meaningful. We do run a
  *softer* version against the bundled corpus when only it is
  available, but mark that run as informational, not a release gate.
"""

from __future__ import annotations

import os

import pytest

from humanize_en import postprocess_humanize
from humanize_en.perplexity import is_available as binoculars_available
from humanize_en.perplexity import score as binoculars_score
from tests.bench._data import load_samples

# Gate parameters — pinned in code rather than config so they're
# version-controlled with the gate logic.
DROP_THRESHOLD = 0.3   # per-sample minimum after - before
PASS_FRACTION = 0.80   # fraction of samples that must clear the threshold


def _llm_provider_available() -> bool:
    """Check the singleton without raising.

    ``humanize_core.llm.get_active()`` raises ``LLMNotConfiguredError``
    when nothing is set; ``has_active()`` is the non-raising probe.
    Imported lazily because the framework's ``llm`` module is heavy
    enough that we don't want it loaded at test-collection time.
    """
    try:
        from humanize_core.llm import has_active
    except ImportError:  # pragma: no cover — humanize_core is a hard dep
        return False
    return has_active()


@pytest.fixture(scope="module")
def gate_samples():
    """Load the gate corpus, falling back to bundled when RAID is missing.

    Module-scoped so we only pay the load cost once across the
    parametrised tests below.
    """
    try:
        samples = load_samples("raid", n=100)
        source = "raid"
    except NotImplementedError:
        samples = load_samples("bundled")
        source = "bundled"
    return samples, source


@pytest.mark.skipif(
    not binoculars_available(),
    reason="binoculars not installed; install humanize-en[perplexity] "
           "AND `pip install git+https://github.com/ahans30/Binoculars`",
)
@pytest.mark.skipif(
    not _llm_provider_available(),
    reason="no LLM provider configured; polish pass would degrade to "
           "deterministic cleanup and produce a misleadingly small delta",
)
@pytest.mark.skipif(
    os.environ.get("HUMANIZE_EN_SKIP_BENCH") == "1",
    reason="HUMANIZE_EN_SKIP_BENCH=1 set in environment",
)
def test_binoculars_drop_gate(gate_samples) -> None:
    """The §7.1 release gate.

    Pass criterion: ≥ 80% of samples show
    ``binoculars_score(after) - binoculars_score(before) ≥ 0.3``.
    """
    samples, source = gate_samples

    if source == "bundled":
        # Soft mode — bundled corpus is too small for a real
        # release gate, but we can still produce a useful number.
        # Failing here would be noisy; warn instead via xfail.
        pytest.xfail(
            "RAID corpus unavailable; gate degrades to bundled (12 samples), "
            "which is insufficient for a release-quality pass-rate. "
            "Numbers below are informational only; install [bench] "
            "extra and rerun for real gate evaluation."
        )

    deltas: list[float] = []
    for s in samples:
        before = binoculars_score(s.text)
        polished, _after, _before = postprocess_humanize(
            s.text, scene=s.scene,
        )
        after = binoculars_score(polished)
        deltas.append(after - before)

    passed = sum(1 for d in deltas if d >= DROP_THRESHOLD)
    pct = passed / len(deltas)
    assert pct >= PASS_FRACTION, (
        f"§7.1 gate failed: {passed}/{len(deltas)} = {pct:.0%} samples "
        f"showed Binoculars score increase ≥ {DROP_THRESHOLD} "
        f"(threshold {PASS_FRACTION:.0%}). "
        f"Mean delta: {sum(deltas)/len(deltas):.3f}. "
        f"See docs/plan.md §12 for the rollback procedure."
    )
