"""humanize_en._lang.en._labels — English level-label dictionary.

Lives in its own module so :mod:`humanize_en._lang.en.detector` and
:mod:`humanize_en._lang.en.ngram` can import it without depending on
:mod:`humanize_en._lang.en.profile` (which itself imports them and
would create a cycle).

The framework's :func:`humanize_core._format.level_label` takes the
labels mapping as an explicit argument (unlike humanize_zh's
hard-coded ZH version), so we curry it here for ergonomic
single-argument use inside detector / ngram code paths.
"""

from __future__ import annotations

from humanize_core._format import level_label as _core_level_label

# Mirrors the band cut-offs in :func:`humanize_core._format.level_key`:
#   [0, 25)   → LOW
#   [25, 50)  → MEDIUM
#   [50, 75)  → HIGH
#   [75, 100] → VERY_HIGH
#
# English equivalents of humanize_zh's ZH_LEVEL_LABELS. The framework's
# ``level_label(prob, labels)`` looks each key up and falls back to
# the bare key string if missing, so missing keys never crash callers.
EN_LEVEL_LABELS: dict[str, str] = {
    "LOW": "LOW (looks human-written)",
    "MEDIUM": "MEDIUM (some AI traces)",
    "HIGH": "HIGH (likely AI-generated)",
    "VERY_HIGH": "VERY HIGH (almost certainly AI)",
}


def en_level_label(prob: float) -> str:
    """Single-arg helper — produces an English localized label for
    a 0-100 AI probability. Wraps the framework function with our
    :data:`EN_LEVEL_LABELS` baked in.
    """
    return _core_level_label(prob, EN_LEVEL_LABELS)


__all__ = ["EN_LEVEL_LABELS", "en_level_label"]
