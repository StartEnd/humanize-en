"""Tests for the M7-follow-up top-level convenience surface.

The README documents a flat ``from humanize_en import score,
postprocess_humanize, judge, llm, ...`` API mirroring
:mod:`humanize_zh`. These tests pin the public shape so the next
refactor cannot silently drop or rename one of those symbols.

We do **not** retest the underlying behaviour here — that lives in
``test_detector.py`` / ``test_ngram.py`` / etc. and in humanize-core's
own ``test_postprocess.py``. The job of this file is to verify that:

1. every symbol named in the README example actually resolves at
   import time;
2. the convenience modules forward to humanize-core (we check
   function identity rather than re-running the implementation);
3. the LLM submodule forwarding is identity-preserving (the
   ``humanize_en.llm.registry`` module is *the same object* as
   ``humanize_core.llm.registry``, so the active-provider singleton
   is shared);
4. ``combined_score`` and ``judge`` bake in ``lang="en"`` so callers
   don't need to thread it through.
"""

from __future__ import annotations

import importlib

import pytest

import humanize_en
import humanize_en.combined as en_combined
import humanize_en.detect as en_detect
import humanize_en.iterative as en_iterative
import humanize_en.llm as en_llm
import humanize_en.ngram_check as en_ngram_check
import humanize_en.postprocess as en_postprocess

# ─── 1. Top-level __all__ shape ────────────────────────────────────────


class TestPackageAll:
    """``humanize_en.__all__`` must cover every README-documented symbol."""

    README_REQUIRED = {
        # detection
        "score",
        "Score",
        "Violation",
        "ngram_score",
        "NgramScore",
        "combined_score",
        "CombinedScore",
        # polish / judge / loop
        "postprocess_humanize",
        "judge",
        "format_judge_report",
        "iterative_polish",
        "IterativeResult",
        "RoundResult",
        # prompt assembly
        "build_humanize_prompt",
        "build_humanize_postprocess_prompt",
        "Strength",
        # LLM
        "llm",
        # registry + profile
        "en_profile",
        "get_language",
        "LanguageProfile",
    }

    def test_readme_symbols_are_in_all(self) -> None:
        missing = self.README_REQUIRED - set(humanize_en.__all__)
        assert not missing, f"missing from __all__: {missing}"

    def test_readme_symbols_resolve(self) -> None:
        for name in self.README_REQUIRED:
            assert hasattr(humanize_en, name), f"missing attribute: {name}"
            # Light callable / value sanity: it isn't ``None``.
            assert getattr(humanize_en, name) is not None, name

    def test_version_string_present(self) -> None:
        assert isinstance(humanize_en.__version__, str)
        assert humanize_en.__version__  # non-empty


# ─── 2. Convenience modules forward to humanize-core ───────────────────


class TestForwardingIdentity:
    """Shims must return the *same* function objects as humanize-core / EN internals."""

    def test_score_is_en_detector_score(self) -> None:
        from humanize_en._lang.en import detector as en_det

        assert en_detect.score is en_det.score
        assert humanize_en.score is en_det.score

    def test_ngram_score_is_en_ngram(self) -> None:
        from humanize_en._lang.en import ngram as en_ng

        assert en_ngram_check.ngram_score is en_ng.ngram_score
        assert humanize_en.ngram_score is en_ng.ngram_score

    def test_combined_dataclass_is_core_class(self) -> None:
        """The dataclass must be the canonical one — same identity."""
        from humanize_core.combined import CombinedScore as CoreCombined

        assert en_combined.CombinedScore is CoreCombined
        assert humanize_en.CombinedScore is CoreCombined

    def test_postprocess_humanize_uses_core(self) -> None:
        """The shim adds a thin profile-resolution layer but forwards through."""
        import humanize_core.postprocess as core_pp_mod

        called = {}

        def fake_core(article, *, profile, lang, scene, violations, provider,
                      detect_first, force_llm):
            called.update(locals())
            return ("polished", None, None)

        original = core_pp_mod.postprocess_humanize
        core_pp_mod.postprocess_humanize = fake_core
        # The shim imported the *function* directly at module load — patch the
        # shim's local reference too, otherwise our fake is bypassed.
        en_postprocess._core_postprocess_humanize = fake_core
        try:
            polished, after, before = en_postprocess.postprocess_humanize(
                "hello", scene="essay"
            )
        finally:
            core_pp_mod.postprocess_humanize = original
            en_postprocess._core_postprocess_humanize = original

        assert polished == "polished"
        # The shim resolved the EN profile and passed it through, not a lang code.
        assert called["profile"] is humanize_en.en_profile
        assert called["lang"] is None
        assert called["scene"] == "essay"

    def test_judge_pins_lang_en(self) -> None:
        """``humanize_en.judge.judge`` must always pass ``lang='en'``.

        Note: we resolve both judge *modules* via :data:`sys.modules`
        rather than the dotted attribute lookup because both
        ``humanize_core/__init__.py`` *and*
        ``humanize_en/__init__.py`` do ``from .judge import judge``,
        which shadows the module attribute with the function of the
        same name. ``sys.modules`` always holds the canonical module.
        """
        import sys

        core_judge_mod = sys.modules["humanize_core.judge"]
        en_judge_mod = sys.modules["humanize_en.judge"]

        captured = {}

        def fake_core(article, *, profile, lang, writer_provider,
                      judge_provider, allow_self_judge):
            captured.update(locals())
            return {"_meta": {}, "publishable": True}

        original = core_judge_mod.judge
        core_judge_mod.judge = fake_core
        en_judge_mod._core_judge = fake_core
        try:
            en_judge_mod.judge("some article")
        finally:
            core_judge_mod.judge = original
            en_judge_mod._core_judge = original

        assert captured["lang"] == "en"
        assert captured["profile"] is None

    def test_iterative_polish_pins_lang_en_when_no_profile(self) -> None:
        import humanize_core.iterative as core_iter_mod

        captured = {}

        def fake_core(article, *, profile, lang, rounds, target_ai_score,
                      scene, writer_provider, judge_provider, allow_self_judge):
            captured.update(locals())
            return "STUB"

        original = core_iter_mod.iterative_polish
        core_iter_mod.iterative_polish = fake_core
        en_iterative._core_iterative_polish = fake_core
        try:
            en_iterative.iterative_polish("hello", rounds=1)
        finally:
            core_iter_mod.iterative_polish = original
            en_iterative._core_iterative_polish = original

        assert captured["lang"] == "en"
        assert captured["profile"] is None

    def test_combined_score_pins_lang_en(self) -> None:
        import humanize_core.combined as core_comb_mod

        captured = {}

        def fake_core(text, *, has_notes, lang):
            captured.update(locals())
            return core_comb_mod.CombinedScore(
                combined_probability=0.0,
                combined_level="LOW",
                rule_probability=0.0,
                rule_level="LOW",
                ngram_probability=0.0,
                ngram_level="LOW",
                ngram_available=False,
                lang=lang,
            )

        original = core_comb_mod.combined_score
        core_comb_mod.combined_score = fake_core
        en_combined._core_combined_score = fake_core
        try:
            result = en_combined.combined_score("text", has_notes=True)
        finally:
            core_comb_mod.combined_score = original
            en_combined._core_combined_score = original

        assert captured["lang"] == "en"
        assert captured["has_notes"] is True
        assert result.lang == "en"


# ─── 3. LLM submodule forwarding preserves identity ────────────────────


class TestLLMForwarding:
    """``humanize_en.llm.<sub>`` must be the *same module object* as the core's.

    Otherwise the registry singleton would split and ``llm.use(...)``
    on one side wouldn't update ``llm.get_active()`` on the other.
    """

    SUBMODULES = (
        "_resolve",
        "anthropic_provider",
        "base",
        "callable_provider",
        "openai_compat",
        "openai_provider",
        "registry",
    )

    @pytest.mark.parametrize("name", SUBMODULES)
    def test_submodule_identity(self, name: str) -> None:
        en_mod = importlib.import_module(f"humanize_en.llm.{name}")
        core_mod = importlib.import_module(f"humanize_core.llm.{name}")
        assert en_mod is core_mod, (
            f"humanize_en.llm.{name} is a different module object than "
            f"humanize_core.llm.{name}; provider state would diverge"
        )

    def test_use_writes_into_shared_active_slot(self) -> None:
        """A ``use_callable`` call via ``humanize_en.llm`` must be visible
        via :func:`humanize_core.llm.get_active`."""
        import humanize_core.llm as core_llm

        # Record current state (may be ``None`` — use the non-raising probe).
        had_active = core_llm.has_active()
        snapshot = core_llm.get_active() if had_active else None
        try:
            en_llm.use_callable(lambda prompt, **kw: "stub-response")
            assert core_llm.has_active()
            # The active provider object responds correctly:
            response = core_llm.get_active().complete("hi")
            # ``complete()`` returns an ``LLMResponse``; ``.text`` matches.
            assert response.text == "stub-response"
        finally:
            if snapshot is not None:
                core_llm.set_active(snapshot)
            else:
                core_llm.clear()


# ─── 4. Profile registration end-to-end ────────────────────────────────


class TestProfileRegistration:
    """``humanize_core.get_language("en")`` must return the singleton EN profile."""

    def test_get_language_returns_en_profile(self) -> None:
        looked_up = humanize_en.get_language("en")
        assert looked_up is humanize_en.en_profile

    def test_re_import_does_not_raise(self) -> None:
        """``importlib.reload(humanize_en)`` must be a no-op for registration.

        The :data:`contextlib.suppress(LanguageAlreadyRegistered)` guard
        in ``humanize_en/__init__.py`` is exactly there to make this case
        safe. If someone removes the guard, this test catches it.
        """
        importlib.reload(humanize_en)
        # And the profile is still findable afterwards:
        assert humanize_en.get_language("en") is humanize_en.en_profile


# ─── 5. End-to-end smoke (no LLM) ──────────────────────────────────────


class TestEndToEndSmoke:
    """Light end-to-end check of the README's documented usage flow."""

    AI_TEXT = (
        "It is important to note that this comprehensive solution "
        "will leverage cutting-edge technology to deliver a paradigm "
        "shift in how we approach the problem. Moreover, by harnessing "
        "the power of AI, we unlock unprecedented opportunities."
    )

    def test_rule_score_flags_ai_text(self) -> None:
        s = humanize_en.score(self.AI_TEXT)
        # We don't pin an exact number (rule weights still evolve),
        # but it should surface *something* on this dense AI sample.
        assert s.total > 0, "AI sample should produce at least one violation"
        # Levels are tier strings produced by the EN labels table
        # (``LOW (looks human-written)`` / ``MEDIUM ...`` / ``HIGH ...``).
        # Just check the tier prefix — the parenthesised explanation evolves.
        tier = s.level.split()[0]
        assert tier in {"LOW", "MEDIUM", "HIGH"}, f"unexpected tier: {s.level}"

    def test_combined_score_emits_lang_en(self) -> None:
        s = humanize_en.combined_score(self.AI_TEXT)
        assert s.lang == "en"

    def test_build_humanize_prompt_returns_text(self) -> None:
        prompt = humanize_en.build_humanize_prompt(scene="analysis")
        assert isinstance(prompt, str)
        assert len(prompt) > 200  # the rules block is substantial
