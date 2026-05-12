"""humanize_en.prompt - EN plugin prompt assembly + dispatcher.

Public-facing module. Mirrors :mod:`humanize_zh.prompt`:

- Re-exports the section constants and the rule-list builder from
  :mod:`humanize_en._lang.en.prompts` so that
  ``from humanize_en.prompt import build_humanize_prompt`` works
  without callers needing to know the internal module path.

- Owns :func:`build_humanize_postprocess_prompt` -- the EN postprocess
  prompt dispatcher with rule-list injection. The framework
  ``humanize-core`` calls this function via the EN plugin's
  ``writer_prompt_builder`` hook on its :class:`PromptPack`.

The framework EN placeholder prompts in :mod:`humanize_core.prompt`
remain as fallbacks for the case where the EN plugin is not
installed (LLM-only polish, no rule injection). When the plugin
**is** installed, this dispatcher replaces them.
"""

from __future__ import annotations

from humanize_core.prompt import (
    JUDGE_PROMPT_EN,
    LOOP_JUDGE_PROMPT_EN,
    POSTPROCESS_PROMPT_EN,
)

from ._lang.en.prompts import (
    ASSERTION_TEMPLATE,
    CORE_RULES,
    HARD_LIMITS,
    HARD_NEVER,
    JUDGE_PROMPT,
    LOOP_JUDGE_PROMPT,
    OPENING_DIVERSITY,
    POSTPROCESS_PROMPT,
    POSTPROCESS_PROMPT_AGGRESSIVE,
    SCENES,
    SELF_CHECK,
    SOUL_INJECTION,
    WORDS_BLACKLIST,
    build_humanize_prompt,
)


def build_humanize_postprocess_prompt(
    article: str,
    violations: list,
    scene: str = "analysis",
    *,
    aggressive: bool = False,
) -> str:
    """Assemble the EN de-AI postprocess prompt with rule injection.

    Three template paths:

    1. ``aggressive=True`` -> :data:`POSTPROCESS_PROMPT_AGGRESSIVE`,
       used when a third-party detector still reports >50% AI score
       after the standard pass. Rewrites sentence structure rather
       than just word choice.
    2. ``aggressive=False`` (default) -> :data:`POSTPROCESS_PROMPT`
       with :data:`HUMANIZE_RULES` populated by
       :func:`build_humanize_prompt` for the requested ``scene``,
       plus a Markdown bullet list of ``violations``.
    3. Fallback when ``violations`` is empty: a placeholder note
       explains that the rule scanner found nothing but a third-
       party detector might still flag the text -- the LLM should
       focus on rhythm rather than vocabulary.

    Args:
        article:    The article body to polish.
        violations: Output from
                    :meth:`humanize_en._lang.en.detector.score`.
                    Each item should expose ``category``, ``rule``,
                    ``count``, ``sample`` attributes (the detector's
                    ``RuleViolation`` does).
        scene:      Rule-list scene -- ``analysis`` / ``essay`` /
                    ``academic`` / ``blog``. Defaults to ``analysis``.
        aggressive: When ``True``, picks the rewrite-level template.

    Returns:
        Fully-assembled prompt string ready for the LLM provider.
    """
    if violations:
        viol_text = "\n".join(
            f"- {v.category}.{v.rule}: hit {v.count}x | sample: \"{v.sample[:60]}\""
            for v in violations[:30]
        )
    else:
        viol_text = (
            "(rule scanner found no violations, but a third-party "
            "detector still flagged the text -- the issue is sentence "
            "rhythm and structure, not vocabulary.)"
        )

    if aggressive:
        return POSTPROCESS_PROMPT_AGGRESSIVE.format(
            ARTICLE=article,
            VIOLATIONS=viol_text,
        )

    rules = build_humanize_prompt(scene=scene, compact=True)
    return POSTPROCESS_PROMPT.format(
        ARTICLE=article,
        VIOLATIONS=viol_text,
        HUMANIZE_RULES=rules,
    )


__all__ = [
    "ASSERTION_TEMPLATE",
    "CORE_RULES",
    "HARD_LIMITS",
    "HARD_NEVER",
    "JUDGE_PROMPT",
    "JUDGE_PROMPT_EN",
    "LOOP_JUDGE_PROMPT",
    "LOOP_JUDGE_PROMPT_EN",
    "OPENING_DIVERSITY",
    "POSTPROCESS_PROMPT",
    "POSTPROCESS_PROMPT_AGGRESSIVE",
    "POSTPROCESS_PROMPT_EN",
    "SCENES",
    "SELF_CHECK",
    "SOUL_INJECTION",
    "WORDS_BLACKLIST",
    "build_humanize_postprocess_prompt",
    "build_humanize_prompt",
]


if __name__ == "__main__":
    print(build_humanize_prompt("analysis"))
