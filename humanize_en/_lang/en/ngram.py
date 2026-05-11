"""humanize_en._lang.en.ngram — English n-gram statistical detector.

**M1 status: stub** (advertises ``available=False``). The real engine
lands in M2: regex-tokenised unigram + bigram frequencies trained on
the HC3-en human side (CC-BY-SA-4.0,
https://huggingface.co/datasets/Hello-SimpleAI/HC3), with logistic
regression calibration to map raw log-prob features → an AI
probability in [0, 100].

Why HC3-en (not RAID) for training:

- HC3-en is small (~30 MB) so the gzipped frequency table ships
  inside the wheel without bloating it.
- It provides direct human/ChatGPT paired answers across 5 domains,
  which gives clean labels for LR calibration.
- RAID is 10 GB and is the right corpus for *evaluation* (M8 bench
  suite), not training.

Honest about scope: even with a strong calibration, n-gram detection
caps around AUC ~0.80 on un-attacked text — well below
Binoculars/Fast-DetectGPT. The value is interpretable per-feature
breakdown (perplexity, burstiness, MATTR, etc.) that downstream
writer prompts can act on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ._labels import en_level_label as level_label

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
_FREQ_PATH = DATA_DIR / "ngram_freq_en.json.gz"
_LR_COEF_PATH = DATA_DIR / "lr_coef_en.json"


@dataclass
class NgramScore:
    """Output of :func:`ngram_score`. Same shape as humanize_zh.ngram_check.NgramScore."""

    ai_probability: float
    level: str
    metrics: dict[str, float] = field(default_factory=dict)
    text_length: int = 0
    char_count: int = 0
    """For EN this is the *word* count, not character count — see the
    NgramEngine protocol docstring. Named ``char_count`` for symmetry
    with the ZH adapter and the protocol contract."""

    available: bool = True

    def __str__(self) -> str:  # pragma: no cover
        if not self.available:
            return f"ngram engine unavailable (level={self.level})"
        lines = [
            f"ngram AI probability: {self.ai_probability:.1f}/100  ({self.level})",
            f"Words: {self.char_count}",
            "",
            "Per-feature metrics:",
        ]
        for k, v in self.metrics.items():
            lines.append(f"  {k:25s}: {v}")
        return "\n".join(lines)


def ngram_score(text: str) -> NgramScore:
    """Run the n-gram statistical detector on ``text``.

    **M1 stub** — always returns ``available=False`` because the
    frequency table and LR coefficients are not yet built. The
    :func:`humanize_core.combined.combined_score` pipeline degrades
    gracefully to rule-only when this happens (see core's combined
    module docstring).
    """
    return NgramScore(
        ai_probability=0.0,
        level=level_label(0.0),
        metrics={"engine_status": "M1 stub — frequency table not yet built"},  # type: ignore[dict-item]
        text_length=len(text),
        char_count=0,
        available=False,
    )


# ─── Protocol adapter ─────────────────────────────────────────────────────


class EnNgramEngine:
    """:class:`~humanize_core.protocols.NgramEngine` adapter.

    Reports availability honestly via :attr:`available`. The combined
    score code falls back to rule-only when this returns ``False``.
    """

    code: str = "en"
    corpus_id: str = "HC3-English (planned, M2)"

    @property
    def available(self) -> bool:
        # Truthful availability: ``True`` only when both calibration
        # files are on disk. M1 ships neither, so this is always False
        # until M2 lands the build script + data files.
        return _FREQ_PATH.exists() and _LR_COEF_PATH.exists()

    def reason_unavailable(self) -> str | None:
        if self.available:
            return None
        missing = []
        if not _FREQ_PATH.exists():
            missing.append(str(_FREQ_PATH.name))
        if not _LR_COEF_PATH.exists():
            missing.append(str(_LR_COEF_PATH.name))
        return (
            f"humanize-en n-gram engine not yet built (M1 stub). "
            f"Missing data files: {', '.join(missing)}. "
            f"Implementation lands in M2."
        )

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
