"""humanize_en.ngram_check — compat shim over :mod:`humanize_en._lang.en.ngram`.

Mirrors :mod:`humanize_zh.ngram_check`. The real implementation
(an HC3-en-trained character-level frequency table + a logistic-
regression calibration head) lives at
:mod:`humanize_en._lang.en.ngram`; this module forwards the
public + test-imported surface so that:

    from humanize_en.ngram_check import ngram_score, NgramScore
    from humanize_en.ngram_check import _load_engine            # used by tests
    from humanize_en.ngram_check import en_ngram                # protocol handle

continue to work without callers needing to know about the
``_lang/en`` internal layout. New code should prefer the canonical
path or the protocol-typed handle
:data:`humanize_en._lang.en.ngram.en_ngram`.
"""

from __future__ import annotations

from ._lang.en import ngram as _en_ngram_mod  # for getattr passthrough
from ._lang.en.ngram import (
    DATA_DIR,
    EnNgramEngine,
    NgramScore,
    en_ngram,
    ngram_score,
)


def __getattr__(name: str):
    """Forward any private helper still exposed by the ngram module.

    The ngram module ships a number of private helpers
    (``_load_engine``, ``_lr_predict_proba``, ``_FREQ_PATH``, …) that
    older tests imported through the top-level ``ngram_check`` path.
    Forwarding lazily here avoids hard-coding a list that drifts as
    the engine evolves.
    """
    try:
        return getattr(_en_ngram_mod, name)
    except AttributeError as exc:  # pragma: no cover — defensive
        raise AttributeError(
            f"module 'humanize_en.ngram_check' has no attribute {name!r}"
        ) from exc


__all__ = [
    "DATA_DIR",
    "EnNgramEngine",
    "NgramScore",
    "en_ngram",
    "ngram_score",
]
