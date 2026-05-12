"""humanize_en.combined — EN-defaulted wrapper around :mod:`humanize_core.combined`.

Mirrors :mod:`humanize_zh.combined` byte-for-byte except that we pin
``lang="en"``. The aggregator itself (rule + n-gram fusion, the
``CombinedScore`` dataclass shape) lives in humanize-core and is
shared with the ZH plugin — only the language binding differs.

Usage::

    from humanize_en import combined_score
    s = combined_score(article, has_notes=False)
    print(s.total, s.level)
"""

from __future__ import annotations

from humanize_core.combined import CombinedScore
from humanize_core.combined import combined_score as _core_combined_score


def combined_score(text: str, has_notes: bool = False) -> CombinedScore:
    """EN-defaulted wrapper over :func:`humanize_core.combined.combined_score`.

    Locks ``lang="en"`` so callers can use the readable two-arg form
    (``combined_score(text, has_notes=True)``) without remembering to
    thread a language code through every call site. All other
    semantics — rule + n-gram fusion weights, level-label mapping,
    fallback when the n-gram engine fails — come straight from the
    framework function; see its docstring for the canonical contract.

    Args:
        text: Article to score.
        has_notes: Whether the document has real operation notes
            attached (affects the rule layer's fake-human heuristics).

    Returns:
        :class:`CombinedScore` with ``lang="en"`` set on the result.
    """
    return _core_combined_score(text, has_notes=has_notes, lang="en")


__all__ = ["CombinedScore", "combined_score"]
