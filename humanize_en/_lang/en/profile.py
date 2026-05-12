"""humanize_en._lang.en.profile — assembled English LanguageProfile.

Single integration point for the EN plugin. Wires the four component
singletons (:data:`detector.en_detector`, :data:`ngram.en_ngram`,
:data:`replacements.en_replacements`, plus a freshly-built
:class:`~humanize_core.protocols.PromptPack`) into one frozen
:class:`~humanize_core.protocols.LanguageProfile` named :data:`en_profile`.

Auto-registration happens in :mod:`humanize_en.__init__` (one
``register_language(en_profile)`` call wrapped in
``contextlib.suppress(LanguageAlreadyRegistered)`` for idempotency).
Tests that need an isolated registry should call
:func:`make_en_profile` directly to get a fresh instance that does
not share state with the process-global singleton.
"""

from __future__ import annotations

from humanize_core.protocols import LanguageProfile, PromptPack

from ._labels import EN_LEVEL_LABELS
from .detector import en_detector
from .ngram import en_ngram
from .prompts import (
    JUDGE_PROMPT,
    LOOP_JUDGE_PROMPT,
    POSTPROCESS_PROMPT,
    build_humanize_prompt,
)
from .replacements import en_replacements

# ``EN_LEVEL_LABELS`` lives in :mod:`humanize_en._lang.en._labels` so
# that detector / ngram can import it without depending on this module
# (which would create an import cycle: profile → detector → profile).
# We re-export it here for backwards-compatible discoverability.


# ─── Prompt pack assembly ──────────────────────────────────────────────────


def _build_en_prompt_pack() -> PromptPack:
    """Build the EN ``PromptPack``.

    M6 wires ``writer_prompt_builder`` to
    :func:`humanize_en.prompt.build_humanize_postprocess_prompt`,
    which assembles the real EN postprocess prompt with
    ``{VIOLATIONS}`` and ``{HUMANIZE_RULES}`` injection. Without
    this hook, ``humanize-core``'s naive ``str.format(ARTICLE=...)``
    fallback would raise ``KeyError`` because the EN
    :data:`POSTPROCESS_PROMPT` declares all three placeholders.

    The import of :mod:`humanize_en.prompt` is deferred inside the
    factory to avoid an import cycle:
    ``humanize_en.prompt`` re-exports symbols from
    :mod:`humanize_en._lang.en.prompts` (which this module also
    imports), so importing the dispatcher at module-level here would
    re-enter ``humanize_en.prompt``'s import while we are still in
    the middle of loading this profile module.
    """
    from ...prompt import build_humanize_postprocess_prompt

    def _en_writer_prompt_builder(
        *,
        article: str,
        violations: list,
        scene: str,
        aggressive: bool,
    ) -> str:
        return build_humanize_postprocess_prompt(
            article,
            violations,
            scene=scene,
            aggressive=aggressive,
        )

    return PromptPack(
        code="en",
        writer_system="",
        writer_user_template=POSTPROCESS_PROMPT,
        judge_system="",
        judge_user_template=JUDGE_PROMPT,
        loop_judge_user_template=LOOP_JUDGE_PROMPT,
        rules_section=build_humanize_prompt(scene="analysis"),
        writer_prompt_builder=_en_writer_prompt_builder,
    )


# ─── Profile factory ───────────────────────────────────────────────────────


def make_en_profile() -> LanguageProfile:
    """Build a fresh ``LanguageProfile`` for ``en``.

    Tests should prefer this over importing :data:`en_profile` when
    they need a profile that does not share state with the
    process-global singleton. Production callers (Web UI, CLI) use
    the singleton via
    :func:`humanize_core.language_registry.get_language`.
    """
    return LanguageProfile(
        code="en",
        display_name="English",
        detector=en_detector,
        ngram_engine=en_ngram,
        replacements=en_replacements,
        prompt_pack=_build_en_prompt_pack(),
        level_labels=dict(EN_LEVEL_LABELS),  # defensive copy
        metadata={
            "corpus": "HC3-English",
            "rule_set_version": en_detector.version,
            "ngram_corpus_id": en_ngram.corpus_id,
            "ngram_test_auc": "0.8847",  # held-out test AUC, see CHANGELOG M2
            "milestone": "M6-prompt-pack",
        },
    )


# Singleton consumed by ``humanize_en/__init__.py``'s auto-registration
# hook. Built exactly once at import time.
en_profile: LanguageProfile = make_en_profile()


__all__ = [
    "EN_LEVEL_LABELS",
    "en_profile",
    "make_en_profile",
]
