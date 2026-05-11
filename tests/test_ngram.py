"""M2 tests for the EN n-gram engine + LR calibration.

Goals:

1. **Sanity** — the engine produces a numeric ai_probability in
   [0, 100] for typical input, and the per-feature metrics match
   what the runtime actually fed into the LR.
2. **Discrimination** — a paragraph laden with AI tells (transition
   phrases, uniform sentence length, low MATTR) scores meaningfully
   higher than one written naturally. We don't assert exact thresholds
   (those would brittle-couple to LR retrains), only the *direction*.
3. **Graceful degradation** — short inputs and inputs in unexpected
   shapes (empty string, single word, no sentences) don't raise.
4. **Calibration provenance** — the shipped ``lr_coef_en.json`` carries
   metadata that lets operators audit which corpus + seed + AUC
   produced the coefficients.
"""

from __future__ import annotations

import json

import pytest

from humanize_en._lang.en.data._ngram_engine import (
    _load_freq,
    compute_burstiness,
    compute_perplexity,
    compute_punctuation_density,
    compute_sentence_length_features,
    compute_transition_density,
    compute_word_mattr,
)
from humanize_en._lang.en.ngram import (
    _LR_COEF_PATH,
    _load_lr_coef,
    en_ngram,
    ngram_score,
)

# ─── Calibration files shipped ──────────────────────────────────────────


def test_freq_table_is_loadable_and_has_expected_shape() -> None:
    """``ngram_freq_en.json.gz`` must load and contain the four keys
    the engine queries: ``unigram``, ``bigram``, ``total_unigrams``,
    ``vocab_size``. Catches accidental mismatched-format builds.
    """
    freq = _load_freq()
    assert freq, "freq table failed to load — was scripts/build_ngram_data.py run?"
    for key in ("unigram", "bigram", "total_unigrams", "vocab_size"):
        assert key in freq, f"freq table missing {key!r}"
    assert freq["vocab_size"] > 1000, "freq vocab unrealistically small"
    # Top tokens look like English (sanity that we trained on the right corpus).
    top10 = sorted(freq["unigram"].items(), key=lambda kv: -kv[1])[:10]
    top_words = {w for w, _ in top10}
    # ``the`` and ``of`` should always be in the top 10 of any English corpus.
    assert "the" in top_words
    assert "of" in top_words


def test_lr_coef_carries_provenance_metadata() -> None:
    """The shipped LR coef file must record the corpus, model, seed,
    and held-out AUC. This is non-negotiable for reproducibility —
    we promise it in plan.md §0 (prior-art landscape) and in the
    README's calibration provenance footer.
    """
    coef = _load_lr_coef()
    assert coef is not None
    meta = coef["_meta"]
    assert "model" in meta
    assert "seed" in meta
    assert meta["test_auc"] >= 0.75, (
        f"shipped LR test AUC = {meta['test_auc']:.4f}; M2 gate is 0.75. "
        f"Re-run scripts/build_ngram_data.py and investigate."
    )
    assert meta["n_human"] > 0 and meta["n_ai"] > 0


def test_lr_coef_shape_matches_feature_order() -> None:
    """``feature_order`` length must match ``feature_mean`` /
    ``feature_std`` / ``coef``. The runtime loader validates this on
    cache-fill; we re-assert here so a malformed file gets caught
    in CI rather than the first user-facing call.
    """
    raw = json.loads(_LR_COEF_PATH.read_text(encoding="utf-8"))
    n = len(raw["feature_order"])
    assert n > 0
    for key in ("feature_mean", "feature_std", "coef"):
        assert len(raw[key]) == n, f"shape mismatch: {key} has {len(raw[key])}, expected {n}"


# ─── Per-feature engine behaviour ───────────────────────────────────────


def test_perplexity_lower_for_typical_text_than_random_chars() -> None:
    """A coherent English paragraph should have meaningfully lower
    perplexity than an arbitrary jumble of low-frequency English
    words. Direction-only assertion — we don't pin numeric values
    because they shift with each freq-table rebuild.
    """
    typical = (
        "The team worked late into the evening to finish the report. "
        "By the time we left the office, the streets were empty and "
        "the rain had stopped."
    )
    jumble = (
        "Quibble fizzy quark zephyr lumbago xanthic kludge crepuscular "
        "obfuscate verisimilitude antediluvian discombobulate."
    )
    p_typical = compute_perplexity(typical)
    p_jumble = compute_perplexity(jumble)
    assert p_typical["perplexity"] < p_jumble["perplexity"]


def test_transition_density_picks_up_ai_distinctive_phrases() -> None:
    """The ``transition_density`` feature should fire on the AI
    phrases curated from Liang et al. arXiv:2403.07183 + HC3.
    """
    ai_text = (
        "Moreover, this is important. Furthermore, we should note. "
        "It's worth noting that, in conclusion, this matters. "
        "Specifically, here's why. Therefore, in summary, take this. "
        "Additionally, on the other hand, considering this."
    )
    # ~10 transitions in ~40 words → density > 200/1000.
    result = compute_transition_density(ai_text)
    assert result["transition_density"] > 100
    assert result["transition_count"] >= 8


def test_burstiness_handles_short_input_without_raising() -> None:
    """Burstiness needs >= 3 sentences with >= 3 words each. Anything
    shorter must return 0.0, never raise — many real-world inputs
    are short comments / fragments.
    """
    assert compute_burstiness("Hi.")["burstiness"] == 0.0
    assert compute_burstiness("")["burstiness"] == 0.0
    assert compute_burstiness("One. Two. Three.")["burstiness"] == 0.0


def test_word_mattr_returns_zero_for_short_text() -> None:
    """MATTR's default 50-word window means anything shorter is not
    enough data. Caller must treat 0.0 as "skip", not "AI tell".
    """
    assert compute_word_mattr("a b c d") == 0.0


def test_sentence_features_produce_valid_ranges() -> None:
    """``cv``, ``short_frac``, and ``equal_mid_frac`` are all bounded
    in [0, 1] (CV in theory unbounded, but never negative). Empty
    or near-empty input must return zeros, not NaN / inf.
    """
    sample = (
        "Short. Here is a slightly longer sentence with several words. "
        "And one more for good measure."
    )
    feats = compute_sentence_length_features(sample)
    assert feats["cv"] >= 0
    assert 0 <= feats["short_frac"] <= 1
    assert 0 <= feats["equal_mid_frac"] <= 1


def test_punctuation_density_counts_commas_correctly() -> None:
    """Comma density must be (#commas * 100 / #words). Plain
    arithmetic check — guards against unit drift if we ever
    tweak the denominator.
    """
    text = "one, two, three, four, five, six, seven, eight, nine, ten."
    # 9 commas, 10 words → comma_density = 90.0.
    result = compute_punctuation_density(text)
    assert result["comma_density"] == pytest.approx(90.0)


# ─── End-to-end ngram_score behaviour ───────────────────────────────────


def test_ngram_score_on_empty_text_is_safe() -> None:
    """Empty input must not raise; protocol contract requires a
    valid NgramScoreResult with available=True (engine *was* able
    to evaluate, the answer is just trivially "low")."""
    s = ngram_score("")
    assert s.ai_probability == 0.0
    assert s.available is True
    assert s.text_length == 0


def test_ngram_score_on_short_input_returns_too_short_marker() -> None:
    """Inputs below the 30-word threshold get a level marked
    "too short for ngram" so callers can see the engine ran but
    declined to score, rather than mistaking 0 for "definitely human".
    """
    s = ngram_score("Just a few words here please.")
    assert "too short" in s.level
    assert s.ai_probability == 0.0


def test_ngram_score_returns_metric_dict_for_normal_text() -> None:
    """A normal-length passage must populate every per-feature key
    the LR consumes. If any key drifts, the runtime call will fall
    back to 0.0 silently — which would mask calibration drift.
    """
    text = (
        "Reading on a paper book is a different experience from reading on "
        "a screen. The eye fatigue is lower, you can scribble in the "
        "margins, and there's no notification to break the spell. I keep "
        "my favourites on a shelf next to the desk so I can grab one when "
        "I need a break. The smell of an old paperback is half the "
        "pleasure. Most of mine are bought second-hand at the market down "
        "the road; the bookseller knows my taste by now."
    )
    s = ngram_score(text)
    expected_keys = {
        "perplexity", "avg_log_prob", "burstiness", "entropy_cv",
        "mean_entropy", "transition_density", "transition_count",
        "sentence_cv", "short_frac", "equal_mid_frac", "word_mattr",
        "comma_density", "punct_density",
    }
    assert expected_keys <= set(s.metrics.keys())
    assert 0 <= s.ai_probability <= 100


def test_ngram_score_discriminates_ai_tells_from_natural_prose() -> None:
    """Direction-only test: an AI-written-looking paragraph (uniform
    sentence length, transition-phrase scaffold, neutral vocabulary)
    must score *higher* than a paragraph written with concrete details
    and varied syntax. Threshold is loose because LR retrains can
    shift absolute values; what matters is the gap.
    """
    ai_like = (
        "It's important to note that effective communication is "
        "essential in modern workplaces. Moreover, clear communication "
        "fosters collaboration and innovation. Furthermore, it helps "
        "build trust among team members. In addition, it reduces "
        "misunderstandings and conflicts. Therefore, organizations "
        "should prioritize communication training. Specifically, "
        "managers should model open dialogue. Consequently, employees "
        "feel more engaged and productive. In conclusion, communication "
        "is the cornerstone of organizational success. Ultimately, "
        "investing in communication yields significant returns."
    )
    natural = (
        "I learned to ride a bike when I was seven, in the alley behind "
        "our flat. My dad held the back of the seat, jogging alongside "
        "until he wasn't there anymore — but I was still pedalling. "
        "When I noticed, I panicked and crashed into a bin. He laughed "
        "so hard he had to lean on the wall. The graze on my elbow "
        "took a week to scab over. I still remember the smell of the "
        "rust on the chain and the weird hum the wheels made on the "
        "concrete. Funny how some afternoons just stick."
    )
    s_ai = ngram_score(ai_like)
    s_nat = ngram_score(natural)
    # If both are above the floor, AI sample should score noticeably higher.
    assert s_ai.ai_probability > s_nat.ai_probability, (
        f"expected AI-like text to score higher; got "
        f"ai_like={s_ai.ai_probability} vs natural={s_nat.ai_probability}"
    )


# ─── Engine adapter (protocol-level) ────────────────────────────────────


def test_engine_corpus_id_records_hc3_english() -> None:
    """Operators reading ``humanize providers`` (Phase 2 of humanize-core)
    need a stable string identifying the training corpus. M2 ships
    HC3-English; lock the literal here so future calibration swaps
    advertise themselves explicitly.
    """
    assert en_ngram.corpus_id == "HC3-English"
