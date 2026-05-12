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

- Owns the M7 :class:`Strength` knob (``low`` / ``medium`` /
  ``high``) and a back-compat ``aggressive`` boolean that maps
  to ``high`` / ``medium`` for the framework hook signature.

The framework EN placeholder prompts in :mod:`humanize_core.prompt`
remain as fallbacks for the case where the EN plugin is not
installed (LLM-only polish, no rule injection). When the plugin
**is** installed, this dispatcher replaces them.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

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


class Strength(str, Enum):
    """M7 strength knob for the polish pass.

    The three levels trade conservatism for rewrite latitude:

    - :attr:`LOW` -- light touch. Uses :data:`POSTPROCESS_PROMPT`
      with a **trimmed** rules section (only ``CORE_RULES`` +
      ``WORDS_BLACKLIST`` + ``SELF_CHECK``). Suitable when the
      input is already mostly human-written and you only want to
      strip obvious AI vocabulary.
    - :attr:`MEDIUM` -- the default. Uses :data:`POSTPROCESS_PROMPT`
      with the full scene-specific rules section. Good first pass
      for typical LLM output.
    - :attr:`HIGH` -- aggressive rewrite. Uses
      :data:`POSTPROCESS_PROMPT_AGGRESSIVE`, which instructs the
      LLM to rewrite sentence structure (not just substitute words).
      Equivalent to ``aggressive=True`` on the legacy signature.

    Inheriting from ``str`` lets callers pass plain strings
    (``strength="low"``) or the enum directly. CLI flags can pass
    the string form straight from argparse without conversion.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Sections retained at LOW strength. Deliberately small: no rhythm
# / opening-diversity / soul-injection / assertion-template
# prescription, so the LLM has more room to leave structurally-fine
# prose alone.
_LOW_STRENGTH_SECTIONS: Final = (CORE_RULES, WORDS_BLACKLIST, SELF_CHECK)


def _build_low_strength_rules() -> str:
    """Compact 3-section rule block for :attr:`Strength.LOW`."""
    return "\n\n---\n\n".join(_LOW_STRENGTH_SECTIONS) + "\n"


def _resolve_strength(
    strength: Strength | str | None,
    aggressive: bool | None,
) -> Strength:
    """Reconcile the ``strength`` and ``aggressive`` arguments.

    Precedence: explicit ``strength`` wins. ``aggressive=True/False``
    only takes effect when ``strength`` is ``None`` (the default,
    set by the framework's writer_prompt_builder signature).
    """
    if strength is not None:
        return strength if isinstance(strength, Strength) else Strength(strength)
    if aggressive is True:
        return Strength.HIGH
    return Strength.MEDIUM


def build_humanize_postprocess_prompt(
    article: str,
    violations: list,
    scene: str = "analysis",
    *,
    strength: Strength | str | None = None,
    aggressive: bool | None = None,
) -> str:
    """Assemble the EN de-AI postprocess prompt with rule injection.

    Three template paths driven by the M7 strength knob:

    1. :attr:`Strength.HIGH` (or legacy ``aggressive=True``) ->
       :data:`POSTPROCESS_PROMPT_AGGRESSIVE`, used when a third-party
       detector still reports > 50% AI score after the standard
       pass. Rewrites sentence structure rather than just word choice.
    2. :attr:`Strength.MEDIUM` (default) -> :data:`POSTPROCESS_PROMPT`
       with :data:`HUMANIZE_RULES` populated by
       :func:`build_humanize_prompt` for the requested ``scene``
       (the full scene rule list).
    3. :attr:`Strength.LOW` -> :data:`POSTPROCESS_PROMPT` with a
       **trimmed** 3-section rule list (CORE_RULES + WORDS_BLACKLIST
       + SELF_CHECK only). The LLM gets more latitude to leave
       structurally-fine prose alone.

    Empty ``violations`` is handled by inserting a placeholder note
    explaining that the rule scanner found nothing but the LLM should
    still focus on rhythm and structure.

    Args:
        article:    The article body to polish.
        violations: Output from
                    :meth:`humanize_en._lang.en.detector.score`.
                    Each item should expose ``category``, ``rule``,
                    ``count``, ``sample`` attributes (the detector's
                    ``RuleViolation`` does).
        scene:      Rule-list scene -- ``analysis`` / ``essay`` /
                    ``academic`` / ``blog``. Defaults to ``analysis``.
                    Ignored when ``strength=Strength.HIGH`` (the
                    aggressive template carries its own rules) or
                    ``strength=Strength.LOW`` (forced 3-section
                    minimal block).
        strength:   :class:`Strength` enum value or matching string
                    (``"low"`` / ``"medium"`` / ``"high"``). When
                    ``None`` (default), falls back to the
                    ``aggressive`` argument: ``True`` -> ``high``,
                    ``False`` -> ``medium``.
        aggressive: Legacy boolean compatible with the framework's
                    ``writer_prompt_builder`` signature. Equivalent
                    to ``strength=Strength.HIGH`` when ``True``.
                    Only consulted when ``strength`` is ``None``.

    Returns:
        Fully-assembled prompt string ready for the LLM provider.
    """
    s = _resolve_strength(strength, aggressive)

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

    if s is Strength.HIGH:
        return POSTPROCESS_PROMPT_AGGRESSIVE.format(
            ARTICLE=article,
            VIOLATIONS=viol_text,
        )

    rules = (
        _build_low_strength_rules()
        if s is Strength.LOW
        else build_humanize_prompt(scene=scene, compact=True)
    )

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
    "Strength",
    "WORDS_BLACKLIST",
    "build_humanize_postprocess_prompt",
    "build_humanize_prompt",
]


if __name__ == "__main__":
    print(build_humanize_prompt("analysis"))
