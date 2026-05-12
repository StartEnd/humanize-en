"""M6 tests — humanize_en prompt pack assembly + dispatcher.

These pin the contract:
- ``build_humanize_prompt`` returns rule-list Markdown for each
  scene, never empty, never crashes on unknown scenes.
- The 8 section constants are non-empty and non-overlapping by
  primary heading.
- The 4 templates carry the placeholders the dispatcher fills in.
- ``build_humanize_postprocess_prompt`` injects violations and the
  rules block correctly under every flag combination.
- The :class:`PromptPack` produced by the EN profile correctly
  routes through the dispatcher when called via the framework
  (i.e. integration with ``humanize_core.postprocess``).
"""

from __future__ import annotations

import pytest

from humanize_en._lang.en.prompts import (
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
from humanize_en.prompt import build_humanize_postprocess_prompt

# ── 1. Section constants ─────────────────────────────────────────────────


SECTION_CONSTANTS = [
    ("CORE_RULES", CORE_RULES),
    ("HARD_NEVER", HARD_NEVER),
    ("HARD_LIMITS", HARD_LIMITS),
    ("WORDS_BLACKLIST", WORDS_BLACKLIST),
    ("OPENING_DIVERSITY", OPENING_DIVERSITY),
    ("SOUL_INJECTION", SOUL_INJECTION),
    ("ASSERTION_TEMPLATE", ASSERTION_TEMPLATE),
    ("SELF_CHECK", SELF_CHECK),
]


@pytest.mark.parametrize("name,section", SECTION_CONSTANTS)
def test_each_section_constant_is_substantial(name: str, section: str) -> None:
    """Every section is real Markdown, not a placeholder."""
    assert isinstance(section, str)
    assert len(section) >= 200, f"{name} too short ({len(section)} chars)"
    assert section.startswith("##"), f"{name} missing Markdown H2 opener"


def test_section_headings_are_unique() -> None:
    """No two sections share the same H2 heading — the assembler
    glues them with `---` so duplicate headings would render badly.
    """
    headings = [
        section.split("\n", 1)[0].strip() for _, section in SECTION_CONSTANTS
    ]
    assert len(headings) == len(set(headings)), (
        f"duplicate section headings: {headings}"
    )


# ── 2. SCENES + build_humanize_prompt ────────────────────────────────────


def test_scenes_table_has_expected_keys() -> None:
    """Same four scenes as humanize-zh: analysis / essay / academic / blog."""
    assert set(SCENES.keys()) == {"analysis", "essay", "academic", "blog"}


@pytest.mark.parametrize("scene", ["analysis", "essay", "academic", "blog"])
def test_build_humanize_prompt_produces_substantial_block(scene: str) -> None:
    """Each scene must produce a block long enough to actually
    constrain the LLM (>= 2000 chars) and short enough to fit in
    a writer prompt without dominating it (<= 30000 chars).
    """
    out = build_humanize_prompt(scene=scene)
    assert isinstance(out, str)
    assert 2000 <= len(out) <= 30000, (
        f"scene={scene!r} length {len(out)} out of expected range"
    )
    # The discipline header is included in non-compact mode.
    assert "De-AI writing discipline" in out


def test_build_humanize_prompt_unknown_scene_falls_back_to_analysis() -> None:
    """Unknown scenes silently fall back to ``analysis`` rather
    than raising — matches the ZH plugin's behaviour.
    """
    fallback = build_humanize_prompt(scene="this-does-not-exist")
    expected = build_humanize_prompt(scene="analysis")
    assert fallback == expected


def test_build_humanize_prompt_compact_drops_header() -> None:
    """``compact=True`` skips the leading discipline header but
    keeps every section body intact.
    """
    full = build_humanize_prompt(scene="analysis", compact=False)
    compact = build_humanize_prompt(scene="analysis", compact=True)
    assert len(compact) < len(full)
    assert "De-AI writing discipline" not in compact
    # Every section body is still present.
    for _, body in SECTION_CONSTANTS:
        first_line = body.split("\n", 1)[0]
        # ASSERTION_TEMPLATE is in the analysis scene; OPENING_DIVERSITY
        # too. Each scene picks a subset, but analysis includes all 8.
        assert first_line in compact, f"missing section: {first_line}"


def test_analysis_scene_includes_all_eight_sections() -> None:
    """Analysis is the most demanding scene and must use every
    section. Other scenes are subsets — they are spot-checked
    by ``test_build_humanize_prompt_produces_substantial_block``.
    """
    assert len(SCENES["analysis"]) == 8


# ── 3. Templates carry the right placeholders ────────────────────────────


def test_postprocess_template_has_all_three_placeholders() -> None:
    """Standard polish template needs ARTICLE / VIOLATIONS / HUMANIZE_RULES."""
    for ph in ("{ARTICLE}", "{VIOLATIONS}", "{HUMANIZE_RULES}"):
        assert ph in POSTPROCESS_PROMPT, (
            f"POSTPROCESS_PROMPT missing placeholder {ph}"
        )


def test_aggressive_template_has_two_placeholders() -> None:
    """Aggressive rewrite template injects rules inline (no separate
    HUMANIZE_RULES placeholder) but still needs ARTICLE + VIOLATIONS.
    """
    for ph in ("{ARTICLE}", "{VIOLATIONS}"):
        assert ph in POSTPROCESS_PROMPT_AGGRESSIVE, (
            f"POSTPROCESS_PROMPT_AGGRESSIVE missing placeholder {ph}"
        )
    assert "{HUMANIZE_RULES}" not in POSTPROCESS_PROMPT_AGGRESSIVE


def test_judge_template_has_only_article_placeholder() -> None:
    """Judge prompt is article-in, JSON-out — no violation injection."""
    assert "{ARTICLE}" in JUDGE_PROMPT
    assert "{VIOLATIONS}" not in JUDGE_PROMPT
    assert "{HUMANIZE_RULES}" not in JUDGE_PROMPT


def test_loop_judge_template_has_only_article_placeholder() -> None:
    """Loop-judge is the in-loop AI-likelihood probe — also article-only."""
    assert "{ARTICLE}" in LOOP_JUDGE_PROMPT
    assert "{VIOLATIONS}" not in LOOP_JUDGE_PROMPT


def test_judge_template_specifies_required_json_schema() -> None:
    """JUDGE_PROMPT is a structured-JSON-output contract. The schema
    documents 7 fields; downstream parsers depend on them.
    """
    for field in (
        "publishable",
        "worst_ai_sections",
        "unsupported_claims",
        "template_smell",
        "fake_human_details",
        "best_theses",
        "rewrite_brief",
    ):
        assert field in JUDGE_PROMPT, f"JUDGE_PROMPT missing field: {field}"


def test_loop_judge_template_specifies_required_json_schema() -> None:
    """LOOP_JUDGE_PROMPT outputs a 3-field probe."""
    for field in ("ai_score", "tells", "verdict"):
        assert field in LOOP_JUDGE_PROMPT, (
            f"LOOP_JUDGE_PROMPT missing field: {field}"
        )


# ── 4. Dispatcher: build_humanize_postprocess_prompt ─────────────────────


class _FakeViolation:
    """Stand-in for :class:`RuleViolation` that exposes the four
    attributes the dispatcher reads.
    """

    def __init__(self, category: str, rule: str, count: int, sample: str) -> None:
        self.category = category
        self.rule = rule
        self.count = count
        self.sample = sample


def test_dispatcher_injects_article_violations_and_rules() -> None:
    """End-to-end happy path: article + violations + scene → rendered
    prompt with all three substituted in.
    """
    article = "The system aims to delve into multifaceted considerations."
    violations = [
        _FakeViolation(
            category="blacklist_words",
            rule="liang_2024_lexical_tells",
            count=2,
            sample="delve",
        )
    ]
    rendered = build_humanize_postprocess_prompt(article, violations)
    assert article in rendered
    assert "blacklist_words.liang_2024_lexical_tells" in rendered
    assert "delve" in rendered
    # The HUMANIZE_RULES block was injected (compact form, no top header).
    assert "Five core rules" in rendered  # CORE_RULES heading
    # No leftover unsubstituted placeholders.
    for ph in ("{ARTICLE}", "{VIOLATIONS}", "{HUMANIZE_RULES}"):
        assert ph not in rendered


def test_dispatcher_aggressive_picks_rewrite_template() -> None:
    """``aggressive=True`` returns the rewrite template instead of
    the standard one. We detect it by the unique header it prints.
    """
    standard = build_humanize_postprocess_prompt(
        "x", [], aggressive=False,
    )
    aggressive = build_humanize_postprocess_prompt(
        "x", [], aggressive=True,
    )
    assert "AI text deep rewrite pass" in aggressive
    assert "AI text deep rewrite pass" not in standard


def test_dispatcher_handles_empty_violations() -> None:
    """When violations is empty, the dispatcher inserts a placeholder
    note rather than producing an empty bullet list — that note is
    important context for the LLM.
    """
    rendered = build_humanize_postprocess_prompt("x", [])
    assert "rule scanner found no violations" in rendered


def test_dispatcher_truncates_to_thirty_violations() -> None:
    """Pathologically broken articles can fire dozens of violations.
    The dispatcher keeps the prompt manageable by capping at 30.
    """
    violations = [
        _FakeViolation("cat", "rule", 1, f"sample{i}") for i in range(50)
    ]
    rendered = build_humanize_postprocess_prompt("article", violations)
    assert "sample29" in rendered
    assert "sample30" not in rendered


@pytest.mark.parametrize(
    "scene", ["analysis", "essay", "academic", "blog", "unknown-scene"]
)
def test_dispatcher_renders_every_scene(scene: str) -> None:
    """Dispatcher must accept every documented scene plus fall back
    cleanly on unknowns.
    """
    rendered = build_humanize_postprocess_prompt(
        "article", [], scene=scene,
    )
    assert "Five core rules" in rendered  # CORE_RULES is in every scene
    # Scenes have different lengths but all should be substantial.
    assert len(rendered) > 3000


# ── 5. Integration with PromptPack on the EN profile ─────────────────────


def test_writer_prompt_builder_routes_through_dispatcher() -> None:
    """The framework's :func:`humanize_core.postprocess._build_writer_prompt`
    calls ``profile.prompt_pack.writer_prompt_builder(...)``. We
    replicate that call here and verify the dispatcher path is taken.
    """
    from humanize_en._lang.en.profile import en_profile

    builder = en_profile.prompt_pack.writer_prompt_builder
    assert builder is not None
    rendered = builder(
        article="The team will leverage cutting-edge solutions.",
        violations=[
            _FakeViolation(
                category="blacklist_words",
                rule="corporate_filler",
                count=1,
                sample="leverage",
            )
        ],
        scene="analysis",
        aggressive=False,
    )
    assert "The team will leverage" in rendered
    assert "blacklist_words.corporate_filler" in rendered
    # Rules block injected.
    assert "Five core rules" in rendered
