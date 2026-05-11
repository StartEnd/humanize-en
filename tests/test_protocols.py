"""M1 contract tests for humanize-en.

Validates that the scaffolded EN plugin:

1. Builds a :class:`~humanize_core.protocols.LanguageProfile` whose
   four components (detector, ngram, replacements, prompt pack) all
   satisfy their runtime-checkable protocols.
2. Auto-registers ``en`` on ``import humanize_en`` so
   ``humanize_core.get_language("en")`` works without any
   hand-registration.
3. Reports honest "stub" status on the components that aren't yet
   implemented (detector returns ``total=0`` with a status marker;
   ngram engine reports ``available=False`` with a clear reason).

These tests are deliberately stricter than they need to be at M1 so
that later milestones (M2-M8) can't silently regress the scaffolding
contract.
"""

from __future__ import annotations

import pytest
from humanize_core.language_registry import (
    ENTRY_POINT_GROUP,
    get_language,
    list_languages,
    register_language,
)
from humanize_core.protocols import (
    Detector,
    LanguageProfile,
    NgramEngine,
    NgramScoreResult,
    PromptPack,
    ReplacementsTable,
    RuleScoreResult,
)

# ─── Profile assembly ────────────────────────────────────────────────────


def test_en_profile_singleton_is_a_language_profile() -> None:
    """``en_profile`` must be a fully-wired ``LanguageProfile`` whose
    component codes all agree. The post-init guard already raises on
    import if not, but we want an explicit regression test in case
    that guard ever weakens.
    """
    from humanize_en._lang.en.profile import en_profile

    assert isinstance(en_profile, LanguageProfile)
    assert en_profile.code == "en"
    assert en_profile.display_name == "English"
    assert en_profile.detector.code == "en"
    assert en_profile.ngram_engine is not None
    assert en_profile.ngram_engine.code == "en"
    assert en_profile.replacements.code == "en"
    assert en_profile.prompt_pack.code == "en"


def test_en_profile_components_satisfy_protocols() -> None:
    """Structural typing — every component answers ``isinstance``
    against its declared protocol. Catches accidental method removal
    or signature drift as components grow in M2-M5.
    """
    from humanize_en._lang.en.profile import en_profile

    assert isinstance(en_profile.detector, Detector)
    assert isinstance(en_profile.ngram_engine, NgramEngine)
    assert isinstance(en_profile.replacements, ReplacementsTable)
    assert isinstance(en_profile.prompt_pack, PromptPack)


def test_make_en_profile_returns_independent_instances() -> None:
    """``make_en_profile()`` must build a fresh profile each call so
    tests can swap profiles without poisoning the global singleton."""
    from humanize_en._lang.en.profile import en_profile, make_en_profile

    fresh = make_en_profile()
    assert fresh is not en_profile
    assert fresh.code == en_profile.code
    # Component singletons are shared intentionally — they cache JSON.
    assert fresh.detector is en_profile.detector
    assert fresh.ngram_engine is en_profile.ngram_engine
    assert fresh.replacements is en_profile.replacements


def test_en_profile_level_labels_are_english() -> None:
    """The level-label dict must carry English strings keyed by the
    canonical LOW/MEDIUM/HIGH/VERY_HIGH codes. M2+ must not drop these.
    """
    from humanize_en._lang.en.profile import EN_LEVEL_LABELS, en_profile

    expected_keys = {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}
    assert set(EN_LEVEL_LABELS) == expected_keys
    assert set(en_profile.level_labels) == expected_keys
    for label in EN_LEVEL_LABELS.values():
        # Every label is non-empty and looks English (no CJK chars).
        assert label
        assert all(ord(c) < 0x4e00 or ord(c) > 0x9fff for c in label)


def test_en_profile_metadata_records_milestone() -> None:
    """While we're pre-alpha, metadata must clearly mark which
    milestone the bundle is at so downstream operators know what
    they're getting.
    """
    from humanize_en._lang.en.profile import en_profile

    md = en_profile.metadata
    # M1 scaffold is now M2-ngram. Future milestones will keep bumping
    # this; the test asserts presence + canonical prefix only.
    assert md["milestone"].startswith("M")
    assert md["rule_set_version"] == en_profile.detector.version
    # M2 ships HC3-English calibration; "planned" was the M1 stub.
    assert md["corpus"] == "HC3-English"
    # AUC must be recorded as a string-encoded float for stability.
    assert float(md["ngram_test_auc"]) >= 0.75


# ─── Auto-registration on import ────────────────────────────────────────


def test_importing_humanize_en_registers_en_with_core() -> None:
    """A bare ``import humanize_en`` must leave the registry with the
    EN profile already accessible via ``get_language("en")``.

    This is the contract that lets every downstream call site
    (``humanize_core.postprocess_humanize``,
    ``humanize_core.iterative_polish``, the FastAPI Web UI, the
    ``humanize`` CLI) reach EN by language code without any user code
    importing :mod:`humanize_en` first.
    """
    import humanize_en  # noqa: F401 — import triggers auto-register

    profile = get_language("en")
    assert profile is humanize_en.en_profile
    assert profile.code == "en"
    assert "en" in list_languages()


def test_entry_point_string_matches_pyproject() -> None:
    """``pyproject.toml`` declares an entry point under
    ``humanize_core.languages`` named ``en`` pointing at
    ``humanize_en._lang.en.profile:en_profile``. If either the group
    constant or the dotted path drift, plugin auto-discovery breaks
    for users who didn't ``import humanize_en`` first.

    Read the entry-point metadata at runtime and assert it matches.
    """
    from importlib.metadata import entry_points

    eps = entry_points(group=ENTRY_POINT_GROUP)
    en_eps = [ep for ep in eps if ep.name == "en"]
    assert en_eps, (
        f"no entry point named 'en' registered under {ENTRY_POINT_GROUP!r} — "
        f"check pyproject.toml [project.entry-points.\"humanize_core.languages\"]"
    )
    ep = en_eps[0]
    assert ep.value == "humanize_en._lang.en.profile:en_profile"


# ─── Honest component status (M1 stubs) ─────────────────────────────────


def test_detector_runs_clean_text_without_firing_rules() -> None:
    """A short, naturally-phrased English sentence with none of the
    M3 lexical / phrase tells must produce ``total=0.0``, zero
    violations, and a populated ``stats`` dict (version + rule
    count). M1 used to assert "stub" presence in stats; M3 ships
    real rules so we assert the engine ran cleanly instead.
    """
    from humanize_en._lang.en.detector import en_detector

    s = en_detector.score("The cat sat by the window watching birds.")
    assert isinstance(s, RuleScoreResult)
    assert s.total == 0.0
    assert s.violations == []
    # Stats now record the rule-set version + how many rules fired.
    assert s.stats.get("rule_set_version", "").startswith(("0.", "1."))
    assert s.stats.get("rule_count_evaluated", -1) == 0


def test_ngram_engine_is_available_with_calibration_shipped() -> None:
    """M2 ships the HC3-en frequency table + LR coefficients in
    ``humanize_en/_lang/en/data/``. The engine must advertise
    ``available=True`` and ``reason_unavailable()`` must return
    ``None``. (M1 used to assert the opposite — flipped here when
    M2 landed real calibration data.)
    """
    from humanize_en._lang.en.ngram import en_ngram

    assert en_ngram.available is True
    assert en_ngram.reason_unavailable() is None
    # score() returns a valid NgramScoreResult.
    result = en_ngram.score(
        "hello world this is a fairly normal English sentence "
        "that should score below the AI threshold."
    )
    assert isinstance(result, NgramScoreResult)
    assert result.available is True


def test_replacements_table_loads_empty_pairs_at_m1() -> None:
    """The M1 stub replacements.json has empty buckets — loader must
    return an empty tuple without raising. M5 will populate ~80 pairs.
    """
    from humanize_en._lang.en.replacements import en_replacements

    pairs = en_replacements.ordered_pairs()
    assert isinstance(pairs, tuple)
    assert pairs == ()


def test_prompt_pack_carries_framework_en_templates() -> None:
    """Until M5 ships humanize-en-owned prompts, the PromptPack must
    re-export the EN placeholder prompts that ``humanize-core``
    already ships. This guarantees ``polish(text, lang="en")`` works
    out of the box even before M5.
    """
    from humanize_core.prompt import (
        JUDGE_PROMPT_EN,
        LOOP_JUDGE_PROMPT_EN,
        POSTPROCESS_PROMPT_EN,
    )

    from humanize_en._lang.en.profile import en_profile

    pp = en_profile.prompt_pack
    assert pp.writer_user_template is POSTPROCESS_PROMPT_EN
    assert pp.judge_user_template is JUDGE_PROMPT_EN
    assert pp.loop_judge_user_template is LOOP_JUDGE_PROMPT_EN
    # ``writer_prompt_builder`` is intentionally None at M1 — the
    # framework's naive str.format suffices for the placeholder
    # template. M5 wires this to a real EN dispatcher.
    assert pp.writer_prompt_builder is None


# ─── End-to-end smoke ───────────────────────────────────────────────────


def test_get_language_en_works_through_core(clean_registry) -> None:
    """The most important M1 gate: a fresh registry state, manually
    register the EN profile, and confirm ``humanize_core.get_language``
    routes correctly.
    """
    from humanize_en._lang.en.profile import en_profile

    register_language(en_profile)
    fetched = get_language("en")
    assert fetched is en_profile
    # Every component is reachable and shape-compatible.
    rule_result = fetched.detector.score("hello world")
    assert isinstance(rule_result, RuleScoreResult)
    assert fetched.ngram_engine is not None
    ngram_result = fetched.ngram_engine.score("hello world")
    assert isinstance(ngram_result, NgramScoreResult)
    pairs = fetched.replacements.ordered_pairs()
    assert isinstance(pairs, tuple)
    assert fetched.level_labels["LOW"]


@pytest.mark.parametrize(
    "level,expected_prefix",
    [
        ("LOW", "LOW"),
        ("MEDIUM", "MEDIUM"),
        ("HIGH", "HIGH"),
        ("VERY_HIGH", "VERY HIGH"),
    ],
)
def test_level_labels_use_canonical_prefixes(level: str, expected_prefix: str) -> None:
    """The framework's :func:`humanize_core._format.level_label`
    expects labels prefixed with the canonical level codes so the Web
    UI can extract a CSS class from the prefix. Lock the shape here
    against accidental rephrasing.
    """
    from humanize_en._lang.en.profile import EN_LEVEL_LABELS

    assert EN_LEVEL_LABELS[level].startswith(expected_prefix)
