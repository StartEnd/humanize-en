"""humanize_en._lang.en.prompts — English writer / judge prompt templates.

**M1 status: re-exports the framework-shipped placeholders.**
``humanize-core`` ships generic English placeholder prompts
(:data:`humanize_core.prompt.POSTPROCESS_PROMPT_EN`,
:data:`~humanize_core.prompt.JUDGE_PROMPT_EN`,
:data:`~humanize_core.prompt.LOOP_JUDGE_PROMPT_EN`) which were added in
core's P2.5 explicitly so the framework could run EN-fallback polish
before this plugin existed. We adopt them verbatim at M1 so the
profile is fully wired; M5 replaces them with prompts that match
humanize-en's six rule buckets and Humano-inspired strength knob.

Imported by :mod:`humanize_en._lang.en.profile` and re-exported from
:mod:`humanize_en.prompt` (the public dispatcher, lands in M5).
"""

from __future__ import annotations

from humanize_core.prompt import (
    JUDGE_PROMPT_EN,
    LOOP_JUDGE_PROMPT_EN,
    POSTPROCESS_PROMPT_EN,
)

# Re-export under the plugin-canonical names so external code can
# import ``from humanize_en._lang.en.prompts import POSTPROCESS_PROMPT``
# without caring about the framework module path.
POSTPROCESS_PROMPT = POSTPROCESS_PROMPT_EN
JUDGE_PROMPT = JUDGE_PROMPT_EN
LOOP_JUDGE_PROMPT = LOOP_JUDGE_PROMPT_EN


def build_humanize_prompt(*, scene: str = "analysis") -> str:
    """Build the standalone rules block for ``PromptPack.rules_section``.

    **M1 stub** — returns a single-line placeholder. The real
    implementation (M5) mirrors humanize_zh.prompt.build_humanize_prompt
    by injecting the scene-specific rule list (analysis / report /
    casual / academic) into a Markdown block.

    Args:
        scene: One of ``"analysis"``, ``"report"``, ``"casual"``,
            ``"academic"``. Ignored at M1.
    """
    return (
        "## English humanization rules\n\n"
        f"(scene={scene}) — rule list lands in M5. "
        "For now, the writer relies on the core framework's "
        "EN postprocess prompt only."
    )


__all__ = [
    "JUDGE_PROMPT",
    "LOOP_JUDGE_PROMPT",
    "POSTPROCESS_PROMPT",
    "build_humanize_prompt",
]
