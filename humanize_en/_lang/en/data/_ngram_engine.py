#!/usr/bin/env python3
"""humanize_en._lang.en.data._ngram_engine — self-contained EN n-gram engine.

Stdlib-only at runtime. The companion build script
``scripts/build_ngram_data.py`` produces the calibration files this
engine consumes:

- ``ngram_freq_en.json.gz`` — unigram + bigram frequencies trained on
  the HC3-en human side (CC-BY-SA-4.0,
  https://huggingface.co/datasets/Hello-SimpleAI/HC3).
- ``lr_coef_en.json`` — logistic-regression coefficients mapping the
  feature vector below to an AI probability in [0, 100].

Features computed (each function returns a dict; missing keys are
allowed and the LR scorer ignores them):

- ``compute_perplexity``         — word-level bigram perplexity with
                                   add-1 smoothing and unigram backoff.
- ``compute_burstiness``         — CV of per-sentence avg log-prob.
                                   Human writing has higher burstiness.
- ``compute_entropy_uniformity`` — CV of per-paragraph token entropy.
                                   AI paragraphs trend toward uniform
                                   entropy across paragraphs.
- ``compute_transition_density`` — transition-phrase count per 1000
                                   words. AI text uses ~2x more (Liang
                                   et al. arXiv:2403.07183 + HC3).
- ``compute_sentence_length_features`` — CV of sentence lengths,
                                   ``short_frac`` (< 6 words), and
                                   ``equal_mid_frac`` (15-25 words).
- ``compute_word_mattr``         — Moving-Average Type-Token Ratio
                                   over 50-word windows. Human writing
                                   has higher lexical diversity.
- ``compute_punctuation_density`` — commas / total punctuation per
                                   100 words. HC3 reports human EN at
                                   higher comma density than ChatGPT.

Why bigram + unigram backoff (not trigram): the HC3-en human side is
~85k answers (~25 MB raw text). Bigrams give ~500k entries; trigrams
would balloon to >5 MB gzipped and only marginally improve AUC. We
trade <1 AUC point for a 4x smaller wheel.

Why no curvature / DivEye / Binoculars-ratio here (vs. ZH's heavier
engine vendored from voidborne-d/humanize-chinese): those features
require a paired LM forward pass and aren't free-running. The
``humanize-en[perplexity]`` extra (M7) wraps real Binoculars for
that signal; here we stay stdlib-pure.
"""

from __future__ import annotations

import gzip
import json
import logging
import math
import os
import re
import statistics
from typing import Any

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FREQ_FILE = os.path.join(SCRIPT_DIR, "ngram_freq_en.json.gz")

_FREQ_CACHE: dict[str, Any] | None = None


def _load_freq() -> dict[str, Any]:
    """Load the gzipped frequency table once and cache it.

    The table has shape::

        {
          "_meta": {...},
          "unigram": {"the": 12345, ...},
          "bigram":  {"the cat": 7, ...},
          "total_unigrams": <int>,
          "total_bigrams":  <int>,
          "vocab_size":     <int>,
        }

    Falls back to an empty table on IO/JSON failure so the engine
    degrades gracefully (every feature returns 0/empty rather than
    raising; the ``EnNgramEngine`` adapter then advertises
    ``available=False``).
    """
    global _FREQ_CACHE
    if _FREQ_CACHE is not None:
        return _FREQ_CACHE
    if not os.path.exists(FREQ_FILE):
        logger.warning("[humanize_en.ngram] freq table missing: %s", FREQ_FILE)
        _FREQ_CACHE = {}
        return _FREQ_CACHE
    try:
        with gzip.open(FREQ_FILE, "rt", encoding="utf-8") as f:
            _FREQ_CACHE = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("[humanize_en.ngram] cannot load %s: %s", FREQ_FILE, e)
        _FREQ_CACHE = {}
    return _FREQ_CACHE


# ─── Tokenisation ───────────────────────────────────────────────────────────


# Word: any run of letters (incl. apostrophe-bound contractions). We
# lowercase before counting to keep the freq table case-insensitive.
# This is the same tokeniser the build script uses; both must stay
# in lockstep so the freq table is queried with matching strings.
_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"\'(\[])|\n+")
_PARA_SPLIT_RE = re.compile(r"\n\s*\n+")


def _tokens(text: str) -> list[str]:
    """Lowercase word tokenisation. Apostrophe-bound contractions stay
    together (``don't``, ``it's``) — important so common contractions
    have stable bigram frequencies in the table.
    """
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def _sentences(text: str) -> list[str]:
    """Conservative sentence splitter: split on sentence-final punct
    followed by whitespace + capital/quote, OR on hard newlines.
    Avoids splitting ``Dr. Smith`` or ``e.g.`` mid-abbreviation.
    """
    parts = _SENT_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in _PARA_SPLIT_RE.split(text) if p.strip()]


# ─── Perplexity ─────────────────────────────────────────────────────────────


def _bigram_log_prob(w1: str, w2: str, freq: dict[str, Any]) -> float:
    """Add-1 smoothed bigram log-prob with unigram backoff.

    ``log P(w2 | w1) = log( (count(w1 w2) + 1) / (count(w1) + V) )``
    where V is the vocab size. If ``w1`` is OOV, fall back to
    pure-unigram add-1: ``log( (count(w2) + 1) / (N + V) )`` where
    N is total token count. This matches the standard
    Jurafsky-Martin SLP formulation §3.6.
    """
    bigrams = freq.get("bigram") or {}
    unigrams = freq.get("unigram") or {}
    vocab_size = freq.get("vocab_size") or max(len(unigrams), 1)
    total_unigrams = freq.get("total_unigrams") or sum(unigrams.values()) or 1

    bg_key = f"{w1} {w2}"
    bg_count = bigrams.get(bg_key, 0)
    w1_count = unigrams.get(w1, 0)
    if w1_count > 0:
        # add-1 smoothed conditional
        return math.log((bg_count + 1) / (w1_count + vocab_size))
    # unseen w1 → unigram backoff with add-1
    w2_count = unigrams.get(w2, 0)
    return math.log((w2_count + 1) / (total_unigrams + vocab_size))


def compute_perplexity(text: str) -> dict[str, float]:
    """Word-level bigram perplexity with unigram backoff.

    Lower perplexity → more predictable → AI-like. HC3-en calibration
    typically puts human writing at PP ≥ 200 and ChatGPT at PP ≤ 100,
    but the LR layer learns this cut-off rather than us hard-coding
    it (so the boundary tracks freq-table changes).
    """
    freq = _load_freq()
    if not freq.get("unigram"):
        return {"perplexity": 0.0, "avg_log_prob": 0.0, "word_count": 0}

    toks = _tokens(text)
    if len(toks) < 5:
        return {"perplexity": 0.0, "avg_log_prob": 0.0, "word_count": len(toks)}

    log_probs = [_bigram_log_prob(toks[i - 1], toks[i], freq) for i in range(1, len(toks))]
    avg_lp = sum(log_probs) / len(log_probs)
    # Clamp PPL upper bound to avoid overflow on completely OOV input.
    ppl = min(math.exp(-avg_lp), 1e6)
    return {
        "perplexity": ppl,
        "avg_log_prob": avg_lp,
        "word_count": len(toks),
    }


# ─── Burstiness ─────────────────────────────────────────────────────────────


def compute_burstiness(text: str) -> dict[str, float]:
    """Coefficient-of-variation of per-sentence avg log-prob.

    Human writing alternates between predictable filler and
    unpredictable content sentences (high CV). AI writing is uniformly
    predictable (low CV). This is the original GPTZero metric, see
    https://gptzero.me/technology.
    """
    freq = _load_freq()
    if not freq.get("unigram"):
        return {"burstiness": 0.0}
    sents = _sentences(text)
    if len(sents) < 3:
        return {"burstiness": 0.0}
    sent_log_probs: list[float] = []
    for s in sents:
        toks = _tokens(s)
        if len(toks) < 3:
            continue
        lps = [_bigram_log_prob(toks[i - 1], toks[i], freq) for i in range(1, len(toks))]
        sent_log_probs.append(sum(lps) / len(lps))
    if len(sent_log_probs) < 3:
        return {"burstiness": 0.0}
    mu = statistics.mean(sent_log_probs)
    if mu == 0:
        return {"burstiness": 0.0}
    sigma = statistics.pstdev(sent_log_probs)
    return {"burstiness": abs(sigma / mu)}


# ─── Entropy uniformity ────────────────────────────────────────────────────


def _shannon_entropy(tokens: list[str]) -> float:
    """Shannon entropy of token distribution within a single sequence.
    Used per-paragraph; paragraphs that are too short (< 8 words) are
    excluded by the caller.
    """
    if not tokens:
        return 0.0
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    n = len(tokens)
    h = 0.0
    for c in counts.values():
        p = c / n
        h -= p * math.log2(p)
    return h


def compute_entropy_uniformity(text: str) -> dict[str, float]:
    """CV of per-paragraph Shannon entropy.

    AI text shows nearly uniform per-paragraph entropy because the
    decoder samples from a similar distribution every time. Human
    writing varies: a vivid anecdote paragraph has lower entropy
    (repeated character names) than an analytical one.

    Returns ``entropy_cv`` and ``mean_entropy``. Low CV = AI-like.
    """
    paras = _paragraphs(text)
    entropies: list[float] = []
    for p in paras:
        toks = _tokens(p)
        if len(toks) < 8:
            continue
        entropies.append(_shannon_entropy(toks))
    if len(entropies) < 2:
        return {"entropy_cv": 0.0, "mean_entropy": 0.0}
    mu = statistics.mean(entropies)
    if mu == 0:
        return {"entropy_cv": 0.0, "mean_entropy": 0.0}
    sigma = statistics.pstdev(entropies)
    return {"entropy_cv": sigma / mu, "mean_entropy": mu}


# ─── Transition density ────────────────────────────────────────────────────


# Curated from HC3-en human/AI diff + Liang et al. arXiv:2403.07183
# (the "delve" paper) Tables 2-3. Sources are noted in the build
# script's metadata. Each phrase is matched case-insensitively at
# word boundaries.
_TRANSITION_PHRASES: tuple[str, ...] = (
    # additive
    "moreover", "furthermore", "additionally", "in addition", "besides",
    # contrast
    "however", "nevertheless", "nonetheless", "on the other hand",
    "conversely", "in contrast", "on the contrary",
    # causal
    "therefore", "consequently", "thus", "hence", "as a result",
    # exemplar / clarification
    "for instance", "for example", "in particular", "specifically",
    "in other words", "that is to say",
    # summary
    "in summary", "in conclusion", "to summarize", "to sum up",
    "ultimately", "overall",
    # AI-distinctive openers
    "it's important to note", "it is important to note",
    "it's worth noting", "it is worth noting",
    "it's worth mentioning", "it is worth mentioning",
)

_TRANSITION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in _TRANSITION_PHRASES) + r")\b",
    re.IGNORECASE,
)


def compute_transition_density(text: str) -> dict[str, float]:
    """Transition phrases per 1000 words.

    HC3-en shows ChatGPT at ~14/1000 vs. human at ~7/1000 (Cohen's
    d ≈ 0.6), aligning with Liang et al.'s finding that "delve",
    "moreover", and meta-comments are AI tells. Density (not raw
    count) so it generalises across text length.
    """
    toks = _tokens(text)
    if not toks:
        return {"transition_density": 0.0, "transition_count": 0}
    count = len(_TRANSITION_RE.findall(text))
    density = count * 1000 / len(toks)
    return {"transition_density": density, "transition_count": float(count)}


# ─── Sentence length features ──────────────────────────────────────────────


def compute_sentence_length_features(text: str) -> dict[str, float]:
    """Sentence-length distribution stats.

    Three signals — all CV-driven so they generalise across text
    length without needing per-corpus calibration:

    - ``cv``: coefficient of variation of word-counts per sentence.
      AI uniform → low CV.
    - ``short_frac``: fraction of sentences with fewer than 6 words.
      Human writing more often pivots with short punchy sentences;
      AI writing rarely emits one.
    - ``equal_mid_frac``: fraction of sentences in the 15-25-word
      "default ChatGPT length" band. Strong AI tell when > 0.5.
    """
    sents = _sentences(text)
    if len(sents) < 3:
        return {"cv": 0.0, "short_frac": 0.0, "equal_mid_frac": 0.0}
    lens = [len(_tokens(s)) for s in sents]
    if not any(lens):
        return {"cv": 0.0, "short_frac": 0.0, "equal_mid_frac": 0.0}
    mu = statistics.mean(lens)
    sigma = statistics.pstdev(lens)
    cv = sigma / mu if mu > 0 else 0.0
    short_frac = sum(1 for L in lens if L < 6) / len(lens)
    equal_mid_frac = sum(1 for L in lens if 15 <= L <= 25) / len(lens)
    return {"cv": cv, "short_frac": short_frac, "equal_mid_frac": equal_mid_frac}


# ─── Word MATTR ─────────────────────────────────────────────────────────────


def compute_word_mattr(text: str, window: int = 50) -> float:
    """Moving-Average Type-Token Ratio over a sliding word window.

    Standard lexical-diversity measure (Covington & McFall 2010 JQL).
    Higher MATTR → more lexical diversity → human-like. Default
    window=50 follows the literature.

    Returns 0.0 when text is shorter than the window — caller should
    treat 0 as "not enough data" rather than "AI tell".
    """
    toks = _tokens(text)
    if len(toks) < window:
        return 0.0
    ratios: list[float] = []
    for i in range(len(toks) - window + 1):
        chunk = toks[i:i + window]
        ratios.append(len(set(chunk)) / window)
    return statistics.mean(ratios) if ratios else 0.0


# ─── Punctuation density ───────────────────────────────────────────────────


def compute_punctuation_density(text: str) -> dict[str, float]:
    """Comma + total-punctuation density per 100 words.

    HC3 numerical analysis (https://arxiv.org/abs/2301.07597 §4)
    reports human EN at ~6.0 commas/100 words vs. ChatGPT at ~4.5
    (Cohen's d ≈ -0.5). The LR layer picks up the gap automatically.
    """
    toks = _tokens(text)
    if not toks:
        return {"comma_density": 0.0, "punct_density": 0.0}
    n = len(toks)
    commas = text.count(",")
    # Other sentence-internal punct that humans use more freely.
    other = sum(text.count(c) for c in (";", ":", "—", "–", "(", ")"))
    return {
        "comma_density": commas * 100 / n,
        "punct_density": (commas + other) * 100 / n,
    }


__all__ = [
    "FREQ_FILE",
    "compute_burstiness",
    "compute_entropy_uniformity",
    "compute_perplexity",
    "compute_punctuation_density",
    "compute_sentence_length_features",
    "compute_transition_density",
    "compute_word_mattr",
]
