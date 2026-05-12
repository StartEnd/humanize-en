"""humanize_en.perplexity - Optional Binoculars-based AI detector.

This package is the M8 wrapper around the upstream **Binoculars**
library (Hans et al., ICML 2024 — Falcon-7B base vs Falcon-7B-instruct
perplexity-ratio detector, BSD-3 licensed). Binoculars achieves ~0.99
zero-shot AUC on English news and ~0.92 after paraphrase attacks,
substantially above the 0.88 AUC our HC3-trained n-gram achieves. When
installed, it provides a much stronger detection signal for
benchmarking and for the §7.1 Binoculars-drop gate.

Design decisions (see ``docs/plan.md`` §8):

- **Wrap, not reimplement.** We depend on the upstream PyPI/GitHub
  install; we do not vendor the model weights or the detector code.
- **Lazy import.** ``import humanize_en.perplexity`` never tries to
  import ``binoculars`` at module-load time. Importing this package
  always succeeds. The actual ``from binoculars import Binoculars``
  call happens inside :func:`score` on first use.
- **Single-point install check.** :func:`is_available` tells callers
  whether the optional dependency is importable without instantiating
  a detector (model download is ~14 GB, you do not want it as a
  side-effect of an availability check).
- **Clear error on missing dep.** If a caller invokes :func:`score`
  (or instantiates :class:`BinocularsScorer`) without installing the
  extra, they get :class:`PerplexityNotInstalledError` with the exact
  install commands, not a ``ModuleNotFoundError`` from deep inside
  transformers.
- **Singleton detector.** Binoculars loads two Falcon-7B models. First
  call is expensive (~30s on GPU, minutes on CPU). We cache the
  instance in ``_GLOBAL_SCORER`` so repeated :func:`score` calls reuse
  it. Callers who want isolation (tests, multi-threaded scoring with
  different devices) should construct :class:`BinocularsScorer`
  directly.

Install (two steps, documented in README):

.. code-block:: bash

   pip install humanize-en[perplexity]
   pip install git+https://github.com/ahans30/Binoculars

The first line pulls ``transformers`` + ``torch``; the second pulls
Binoculars itself (which is not yet on PyPI as of this writing).

Typical usage:

.. code-block:: python

   from humanize_en.perplexity import score, is_available

   if is_available():
       raw_score = score(article_text)
   else:
       # Fall back to the n-gram detector.
       raw_score = None

Note on polarity: Binoculars' :meth:`compute_score` returns a float
where **lower values indicate AI-generated** text and higher values
indicate human-written. This is the opposite of our rule/n-gram
detectors (where higher = more AI). We expose the upstream value
**unchanged** so callers can match the Binoculars paper's numbers;
wrap or invert in your own adapter if you need a unified polarity.
"""

from __future__ import annotations

from .binoculars_wrapper import (
    BinocularsScorer,
    PerplexityNotInstalledError,
    is_available,
    score,
)

__all__ = [
    "BinocularsScorer",
    "PerplexityNotInstalledError",
    "is_available",
    "score",
]
