"""humanize_en.iterative — EN-defaulted thin shim over :mod:`humanize_core.iterative`.

The writer/judge ping-pong loop itself lives in humanize-core; this
shim pins the EN profile so callers can write::

    from humanize_en import iterative_polish
    result = iterative_polish(article, rounds=3, target_ai_score=30)

without remembering to thread ``lang=`` / ``profile=`` through each
call. Dataclasses (:class:`RoundResult`, :class:`IterativeResult`)
are re-exported from humanize-core unchanged so tests that introspect
their fields keep working.

Mirrors :mod:`humanize_zh.iterative` byte-for-byte modulo the EN
default — the loop logic is shared.
"""

from __future__ import annotations

from humanize_core.iterative import (
    IterativeResult,
    RoundResult,
    Verdict,
    _build_round_violations,  # noqa: F401  (legacy re-export)
)
from humanize_core.iterative import _judge_one_round as _core_judge_one_round
from humanize_core.iterative import iterative_polish as _core_iterative_polish
from humanize_core.protocols import LanguageProfile

from ._lang.en.profile import en_profile
from ._lang.en.prompts import LOOP_JUDGE_PROMPT  # noqa: F401  (legacy re-export)
from .llm import LLMProvider, ProviderArg, provider_id  # noqa: F401  (legacy re-export)


def _judge_one_round(
    text: str,
    *,
    judge_provider: LLMProvider,
    profile: LanguageProfile | None = None,
) -> tuple[int | None, list[str], Verdict]:
    """Run one judge round; defaults ``profile=en_profile``.

    Thin wrapper over :func:`humanize_core.iterative._judge_one_round`.
    The framework function requires ``profile=`` as an explicit
    keyword argument; this shim supplies :data:`en_profile` when the
    caller leaves it unset so test fixtures lifted from humanize-zh
    work after swapping the package prefix.
    """
    return _core_judge_one_round(
        text,
        judge_provider=judge_provider,
        profile=en_profile if profile is None else profile,
    )


def iterative_polish(
    article: str,
    *,
    rounds: int = 3,
    target_ai_score: int = 30,
    scene: str = "analysis",
    profile: LanguageProfile | None = None,
    writer_provider: ProviderArg = None,
    judge_provider: ProviderArg = None,
    allow_self_judge: bool = False,
) -> IterativeResult:
    """Closed-loop polish — each round writer rewrites, judge scores.

    Thin wrapper over :func:`humanize_core.iterative.iterative_polish`
    with ``lang="en"`` locked in. All other arguments forward verbatim.

    Loop termination (inherited from the framework):

    - ``judge.ai_score <= target_ai_score`` — reached the bar.
    - ``rounds`` exhausted.
    - Judge call fails (the failure is captured as
      ``stopped_reason`` and surfaced on
      :class:`RoundResult.error`).

    Args:
        article: Source markdown.
        rounds: Maximum number of writer/judge passes.
        target_ai_score: Early-exit threshold on the judge's 0-100 AI
            probability. ``<=`` wins.
        scene: EN rule-list scene forwarded to the writer prompt.
        profile: Pre-resolved :class:`LanguageProfile`. Takes
            priority over the EN default.
        writer_provider: LLM provider for the polish call.
        judge_provider: LLM provider for the judge call. Must differ
            from ``writer_provider`` unless
            ``allow_self_judge=True``.
        allow_self_judge: Override the collusion check.

    Returns:
        :class:`IterativeResult` with each round's polished text,
        scores, verdicts, and a ``stopped_reason`` tag.
    """
    return _core_iterative_polish(
        article,
        profile=profile,
        lang="en" if profile is None else None,
        rounds=rounds,
        target_ai_score=target_ai_score,
        scene=scene,
        writer_provider=writer_provider,
        judge_provider=judge_provider,
        allow_self_judge=allow_self_judge,
    )


__all__ = [
    "IterativeResult",
    "RoundResult",
    "Verdict",
    "iterative_polish",
    "LOOP_JUDGE_PROMPT",
]
