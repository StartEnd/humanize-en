"""humanize_en.detect — compat shim over :mod:`humanize_en._lang.en.detector`.

Mirrors :mod:`humanize_zh.detect` exactly. The actual rule-based
detector implementation lives under
``humanize_en._lang.en.detector`` (see ``docs/plan.md`` §3 for the
rule taxonomy and §4 for the n-gram tier). This module re-exports the
public detection surface so the README's ``from humanize_en import
score`` pattern works, and so test files lifted from humanize-zh
compile against EN with only a package-prefix substitution.

    from humanize_en.detect import score, Score, Violation
    from humanize_en.detect import _load_patterns   # internal, used by tests
    from humanize_en.detect import _strip_codeblocks   # internal, used by tests

New code should prefer ``humanize_en._lang.en.detector`` directly, or
the protocol-typed handle :data:`humanize_en._lang.en.detector.en_detector`.
"""

from __future__ import annotations

# The EN detector module ships a small number of test-only helpers
# (``_load_patterns``, ``_strip_codeblocks``, ``PATTERNS_PATH``, …).
# Forward whichever ones actually exist — they evolve as the rule set
# grows and we don't want this shim to crash a future import if one
# is renamed.
from . import _lang as _en_lang_pkg  # noqa: F401
from ._lang.en import detector as _en_detector_mod  # for getattr passthrough
from ._lang.en.detector import (
    EnDetector,
    Score,
    Violation,
    en_detector,
    score,
)


def __getattr__(name: str):
    """Lazy forwarder for any private helper still exposed by the detector.

    Keeps the legacy ``humanize_en.detect._load_patterns`` import path
    alive without us having to hard-code every internal name (the rule
    set is still moving; pinning the list here would create churn on
    every M-series detector change).
    """
    try:
        return getattr(_en_detector_mod, name)
    except AttributeError as exc:  # pragma: no cover — defensive
        raise AttributeError(
            f"module 'humanize_en.detect' has no attribute {name!r}"
        ) from exc


__all__ = [
    "EnDetector",
    "Score",
    "Violation",
    "en_detector",
    "score",
]
