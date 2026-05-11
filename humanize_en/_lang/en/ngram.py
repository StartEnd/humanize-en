#!/usr/bin/env python3
"""humanize_en._lang.en.ngram — English n-gram statistical detector.

Combines the stdlib-only feature engine in
:mod:`humanize_en._lang.en.data._ngram_engine` with a logistic-regression
calibration trained on HC3-en (see ``scripts/build_ngram_data.py``).

Calibration files (shipped in ``humanize_en/_lang/en/data/``):

- ``ngram_freq_en.json.gz`` — unigram + bigram counts on HC3-en human
  side (57k answers, 6.9M tokens, top-500k bigrams). License:
  CC-BY-SA-4.0 (data); MIT (counts file).
- ``lr_coef_en.json`` — sklearn LogisticRegression coefficients +
  per-feature mean/std for standardisation. Trained on a balanced
  10k human / 10k AI sample with stratified 80/20 split.
  Held-out **test AUC = 0.8597** (M2.0).

Per-feature signals (from the engine):

- ``perplexity`` + ``avg_log_prob`` (bigram with unigram backoff)
- ``burstiness``: CV of per-sentence avg log-prob
- ``entropy_cv`` + ``mean_entropy``: per-paragraph token entropy
- ``transition_density``: AI-distinctive transition phrases / 1000 words
- ``sentence_cv`` + ``short_frac`` + ``equal_mid_frac``: sentence-length stats
- ``word_mattr``: Moving-Average Type-Token Ratio (50-word window)
- ``comma_density`` + ``punct_density``: punctuation per 100 words

Honest scope: AUC ~0.86 on un-attacked HC3-en is solid for a
stdlib-only pipeline but stays below dedicated zero-shot detectors
(Binoculars ICML 2024 ~0.99). The value here is interpretable
per-feature breakdown that the polish pipeline can act on.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._labels import en_level_label as level_label
from .data._ngram_engine import (
    compute_burstiness,
    compute_entropy_uniformity,
    compute_perplexity,
    compute_punctuation_density,
    compute_sentence_length_features,
    compute_transition_density,
    compute_word_mattr,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
_FREQ_PATH = DATA_DIR / "ngram_freq_en.json.gz"
_LR_COEF_PATH = DATA_DIR / "lr_coef_en.json"


# ─── LR coefficients loader ────────────────────────────────────────────────


_LR_CACHE: dict[str, Any] | None = None
_LR_LOAD_ERROR: str | None = None


def _load_lr_coef() -> dict[str, Any] | None:
    """Load logistic-regression coefficients once and cache.

    Returns ``None`` if the file is missing or malformed; the
    :class:`EnNgramEngine` adapter then advertises ``available=False``
    and the combined-score pipeline falls back to rule-only.
    """
    global _LR_CACHE, _LR_LOAD_ERROR
    if _LR_CACHE is not None:
        return _LR_CACHE
    if _LR_LOAD_ERROR is not None:
        return None
    if not _LR_COEF_PATH.exists():
        _LR_LOAD_ERROR = f"LR coefficients missing: {_LR_COEF_PATH}"
        return None
    try:
        data = json.loads(_LR_COEF_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        _LR_LOAD_ERROR = f"cannot load {_LR_COEF_PATH}: {e}"
        logger.error("[humanize_en.ngram] %s", _LR_LOAD_ERROR)
        return None
    # Validate shape — all four arrays must have the same length.
    n = len(data.get("feature_order", []))
    for key in ("feature_mean", "feature_std", "coef"):
        if len(data.get(key, [])) != n:
            _LR_LOAD_ERROR = (
                f"shape mismatch in {_LR_COEF_PATH}: "
                f"feature_order has {n} entries but {key} has "
                f"{len(data.get(key, []))}"
            )
            return None
    _LR_CACHE = data
    return _LR_CACHE


def _lr_predict_proba(features: list[float], coef_data: dict[str, Any]) -> float:
    """Apply the (mean, std, coef, intercept) tuple from
    ``lr_coef_en.json`` to a feature vector.

    Standardise → linear combination → sigmoid → AI probability in [0, 1].
    The featurisation order MUST match
    :data:`scripts.build_ngram_data.FEATURE_ORDER`.
    """
    mu = coef_data["feature_mean"]
    sigma = coef_data["feature_std"]
    coef = coef_data["coef"]
    intercept = float(coef_data["intercept"])
    # Standardise; clip to ±10 std to limit OOD inputs from blowing up
    # the linear sum (a single 50σ outlier would dominate without this).
    z = 0.0
    for x, m, s, w in zip(features, mu, sigma, coef, strict=True):
        if s == 0:
            continue
        std_x = max(min((x - m) / s, 10.0), -10.0)
        z += std_x * w
    z += intercept
    # Numerically-stable sigmoid.
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


# ─── Public dataclass ──────────────────────────────────────────────────────


@dataclass
class NgramScore:
    """Output of :func:`ngram_score`. Same shape as humanize_zh.ngram_check.NgramScore."""

    ai_probability: float
    level: str
    metrics: dict[str, float] = field(default_factory=dict)
    text_length: int = 0
    char_count: int = 0
    """Tokens-of-interest count — for EN this is the *word* count
    (apostrophe-bound contractions kept whole). The protocol
    docstring on humanize_core uses ``char_count`` as the field name
    for symmetry with the ZH adapter; in EN it really is words."""

    available: bool = True

    def __str__(self) -> str:  # pragma: no cover — pretty-print only
        if not self.available:
            return f"ngram engine unavailable (level={self.level})"
        lines = [
            f"ngram AI probability: {self.ai_probability:.1f}/100  ({self.level})",
            f"Words: {self.char_count}",
            "",
            "Per-feature metrics:",
        ]
        for k, v in sorted(self.metrics.items()):
            lines.append(f"  {k:25s}: {v}")
        return "\n".join(lines)


# ─── Scoring ───────────────────────────────────────────────────────────────


def ngram_score(text: str) -> NgramScore:
    """Run the full feature engine + LR calibration on ``text``.

    Returns ``available=False`` (with a diagnostic level) when the
    freq table or LR coefficients are missing — the combined-score
    pipeline degrades gracefully to rule-only in that case.

    Short texts (< 30 words) skip scoring and return
    ``ai_probability=0.0`` with a level marker — too noisy to be
    useful and the LR was trained on min-50-char answers.
    """
    if not text or not text.strip():
        return NgramScore(
            ai_probability=0.0,
            level=level_label(0.0),
            text_length=0,
            char_count=0,
            available=True,
        )

    # Compute features first so we have something to surface even when
    # the LR file is missing.
    metrics: dict[str, float] = {}
    ppl = compute_perplexity(text)
    metrics["perplexity"] = round(ppl.get("perplexity", 0.0), 2)
    metrics["avg_log_prob"] = round(ppl.get("avg_log_prob", 0.0), 3)
    word_count = int(ppl.get("word_count", 0))

    if word_count < 30:
        return NgramScore(
            ai_probability=0.0,
            level=f"{level_label(0.0)} (too short for ngram)",
            metrics=metrics,
            text_length=len(text),
            char_count=word_count,
            available=True,
        )

    burst = compute_burstiness(text)
    metrics["burstiness"] = round(burst.get("burstiness", 0.0), 4)

    ent = compute_entropy_uniformity(text)
    metrics["entropy_cv"] = round(ent.get("entropy_cv", 0.0), 4)
    metrics["mean_entropy"] = round(ent.get("mean_entropy", 0.0), 3)

    trans = compute_transition_density(text)
    metrics["transition_density"] = round(trans.get("transition_density", 0.0), 2)
    metrics["transition_count"] = float(trans.get("transition_count", 0))

    sent = compute_sentence_length_features(text)
    metrics["sentence_cv"] = round(sent.get("cv", 0.0), 4)
    metrics["short_frac"] = round(sent.get("short_frac", 0.0), 4)
    metrics["equal_mid_frac"] = round(sent.get("equal_mid_frac", 0.0), 4)

    metrics["word_mattr"] = round(compute_word_mattr(text), 4)

    punct = compute_punctuation_density(text)
    metrics["comma_density"] = round(punct.get("comma_density", 0.0), 2)
    metrics["punct_density"] = round(punct.get("punct_density", 0.0), 2)

    # Apply LR. If coefficients are missing, surface metrics with a
    # placeholder probability so the caller still gets something useful.
    coef_data = _load_lr_coef()
    if coef_data is None:
        return NgramScore(
            ai_probability=0.0,
            level=level_label(0.0),
            metrics=metrics,
            text_length=len(text),
            char_count=word_count,
            available=False,
        )

    feature_order = coef_data["feature_order"]
    feature_vec = [float(metrics.get(name, 0.0)) for name in feature_order]
    p_ai = _lr_predict_proba(feature_vec, coef_data)
    ai_probability = round(p_ai * 100, 1)

    return NgramScore(
        ai_probability=ai_probability,
        level=level_label(ai_probability),
        metrics=metrics,
        text_length=len(text),
        char_count=word_count,
        available=True,
    )


# ─── Protocol adapter ─────────────────────────────────────────────────────


class EnNgramEngine:
    """:class:`~humanize_core.protocols.NgramEngine` adapter.

    Reports availability honestly via :attr:`available`. The combined
    score code falls back to rule-only when this returns ``False``.
    """

    code: str = "en"
    corpus_id: str = "HC3-English"

    def __init__(self) -> None:
        # Force-load both calibration files up-front so :attr:`available`
        # is accurate before any caller touches :meth:`score`.
        from .data import _ngram_engine as eng

        eng._load_freq()
        _load_lr_coef()

    @property
    def available(self) -> bool:
        from .data import _ngram_engine as eng

        # Truthful: both the freq table AND the LR coefficients must
        # be loadable. If either is missing, we degrade.
        return bool(eng._load_freq().get("unigram")) and _load_lr_coef() is not None

    def reason_unavailable(self) -> str | None:
        from .data import _ngram_engine as eng

        if self.available:
            return None
        if not eng._load_freq().get("unigram"):
            return f"frequency table not loaded; expected at {_FREQ_PATH}"
        if _LR_LOAD_ERROR:
            return _LR_LOAD_ERROR
        return f"LR coefficients not loaded; expected at {_LR_COEF_PATH}"

    def score(self, text: str) -> NgramScore:
        return ngram_score(text)


# Singleton consumed by ``humanize_en._lang.en.profile``.
en_ngram: EnNgramEngine = EnNgramEngine()


__all__ = [
    "EnNgramEngine",
    "NgramScore",
    "en_ngram",
    "ngram_score",
]
