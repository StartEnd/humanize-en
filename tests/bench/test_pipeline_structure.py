"""Structural smoke tests for the plan-M8 benchmark pipeline.

These tests **always run** (no skip-marks). Their job is to catch
the kind of regression that breaks the pipeline regardless of
whether the optional GPU/dataset deps are installed:

- the bundled samples still fire the detector (so a future rule
  refactor doesn't silently mute the structure tests);
- the loader returns the right shape;
- ``postprocess_humanize`` actually changes the text (deterministic
  cleanup at minimum, even without an LLM provider configured);
- the rule-layer score after polish is ≤ before polish on the
  bundled corpus (sanity: polish must not make AI-tells *worse*).

The numerical-quality gates (§7.1 Binoculars drop, §7.2 BERTScore,
§7.3 Flesch-Kincaid) live in ``test_binoculars_drop.py`` /
``test_meaning_preservation.py`` / ``test_readability.py``.
"""

from __future__ import annotations

import pytest

from humanize_en import postprocess_humanize, score
from tests.bench._data import BenchSample, load_samples

# We pin a small subset rather than the full 12 because the polish
# tests are O(N) over LLM calls, and any provider configured in the
# environment will get hit. Three samples is enough to verify the
# pipeline in CI without breaking the wallet of someone running
# ``pytest`` locally with their real OPENAI_API_KEY exported.
SMOKE_SUBSET_N = 3


# ─── Sample loader sanity ──────────────────────────────────────────────


def test_load_bundled_returns_at_least_ten_samples() -> None:
    """The bundled corpus must have enough samples to compute mean
    deltas on. Below 10 the variance is too high to interpret."""
    samples = load_samples("bundled")
    assert len(samples) >= 10, f"only {len(samples)} bundled samples"


def test_bundled_samples_have_unique_ids() -> None:
    samples = load_samples("bundled")
    ids = [s.id for s in samples]
    assert len(ids) == len(set(ids)), "duplicate sample ids"


def test_bundled_samples_have_scene_tags() -> None:
    """Every sample must declare a ``scene`` so polish picks the right
    rule subset (analysis / blog / academic / essay). The polish
    pipeline doesn't validate this — drift would surface as bad
    polish quality without a clear error — so we pin it here."""
    valid_scenes = {"analysis", "blog", "academic", "essay"}
    samples = load_samples("bundled")
    for s in samples:
        assert s.scene in valid_scenes, f"{s.id} has unknown scene {s.scene!r}"


def test_load_with_n_caps_results() -> None:
    samples = load_samples("bundled", n=3)
    assert len(samples) == 3


def test_load_with_domain_filter() -> None:
    blog_only = load_samples("bundled", domain="blog")
    assert blog_only
    assert all(s.domain == "blog" for s in blog_only)


def test_raid_source_raises_until_implemented() -> None:
    """The RAID loader is intentionally a NotImplementedError — silent
    fallback to the bundled set would yield fake RAID numbers in
    ``docs/benchmarks.md``."""
    with pytest.raises(NotImplementedError):
        load_samples("raid")


# ─── Detector still fires on bundled corpus ────────────────────────────


def test_bundled_samples_fire_detector() -> None:
    """Every bundled sample must score ≥ 50 on the rule layer.

    This is the contract: the stub corpus exists *because* the
    pipeline needs visible work to do without RAID. If a rule-set
    refactor mutes most samples, the polish-delta tests would
    silently start measuring noise. Catch it here instead.
    """
    weak = []
    samples = load_samples("bundled")
    for s in samples:
        result = score(s.text)
        if result.total < 50:
            weak.append((s.id, result.total))
    assert not weak, (
        f"{len(weak)} bundled samples scored < 50 on the rule layer: {weak}. "
        f"Either retune the samples in tests/bench/_samples.json or "
        f"investigate the rule-set change that muted them."
    )


def test_each_sample_fires_at_least_five_violations() -> None:
    """Each sample must trigger at least 5 distinct rule violations.

    This is documented in ``_samples.json::_meta.design_rules``.
    Below 5, the polish pass has too little to work with for the
    delta tests to be meaningful.
    """
    samples = load_samples("bundled")
    weak = [(s.id, len(score(s.text).violations)) for s in samples
            if len(score(s.text).violations) < 5]
    assert not weak, (
        f"samples below 5-violation floor: {weak}. "
        f"Update tests/bench/_samples.json to retune."
    )


# ─── Polish pipeline produces a delta ──────────────────────────────────


@pytest.fixture(scope="module")
def smoke_samples() -> list[BenchSample]:
    return load_samples("bundled", n=SMOKE_SUBSET_N)


def test_polish_returns_three_tuple(smoke_samples: list[BenchSample]) -> None:
    """``postprocess_humanize`` must return ``(text, after_score,
    before_score)``. Catches a contract regression separately from
    the delta test below — failing this is a different kind of bug."""
    polished, after, before = postprocess_humanize(
        smoke_samples[0].text, scene=smoke_samples[0].scene,
    )
    assert isinstance(polished, str) and polished
    # The two scores can be ``None`` if detect_first=False or on the
    # EN-fallback path; but on the EN-plugin path with default args
    # they should be non-None.
    assert before is not None, "expected before-score on EN-plugin path"
    assert after is not None, "expected after-score on EN-plugin path"


def test_polish_does_not_increase_rule_score(
    smoke_samples: list[BenchSample],
) -> None:
    """Polish must not make the rule-layer score *worse* on average.

    Per-sample worsening is permitted (the rule detector has known
    false positives in pre/post comparisons; aggressive paraphrase
    can introduce a new violation while removing two old ones), but
    the *mean* delta over the smoke subset must be ≤ 0.

    This is a structural sanity check, not a quality gate. The real
    quality gates (§7.1 Binoculars drop, §7.2 BERTScore) live in
    sibling test files.
    """
    befores = []
    afters = []
    for sample in smoke_samples:
        polished, after, before = postprocess_humanize(
            sample.text, scene=sample.scene,
        )
        if before is None or after is None:
            pytest.skip("EN-fallback path returned no scores; smoke test "
                        "requires EN-plugin path.")
        befores.append(before.total)
        afters.append(after.total)

    mean_delta = (sum(afters) - sum(befores)) / len(befores)
    assert mean_delta <= 0, (
        f"polish *increased* mean rule score by {mean_delta:.2f}. "
        f"befores={befores}, afters={afters}"
    )
