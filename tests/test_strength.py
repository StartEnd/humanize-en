"""M7 tests - Strength knob (low / medium / high) for the postprocess
prompt dispatcher.

Pin the contract:
- ``Strength`` enum exposes exactly the three documented members.
- ``Strength`` is a string-enum so ``"low"`` works as well as
  ``Strength.LOW``.
- The three levels produce visibly different prompts (length and
  template choice).
- LOW uses a trimmed 3-section rules block (CORE_RULES +
  WORDS_BLACKLIST + SELF_CHECK).
- MEDIUM uses the full scene-specific rules block.
- HIGH switches to ``POSTPROCESS_PROMPT_AGGRESSIVE`` and is
  equivalent to legacy ``aggressive=True``.
- Backward compatibility: ``aggressive=True`` -> HIGH,
  ``aggressive=False`` -> MEDIUM, both honoured only when
  ``strength=None``.
- Explicit ``strength=`` overrides ``aggressive``.
- The Strength enum is re-exported from the package root.
"""

from __future__ import annotations

import pytest

from humanize_en import Strength as PackageStrength
from humanize_en._lang.en.prompts import (
    ASSERTION_TEMPLATE,
    CORE_RULES,
    HARD_LIMITS,
    HARD_NEVER,
    OPENING_DIVERSITY,
    SELF_CHECK,
    SOUL_INJECTION,
    WORDS_BLACKLIST,
)
from humanize_en.prompt import (
    Strength,
    _resolve_strength,
    build_humanize_postprocess_prompt,
)


class _FakeViolation:
    def __init__(self, category: str = "cat", rule: str = "r",
                 count: int = 1, sample: str = "s") -> None:
        self.category = category
        self.rule = rule
        self.count = count
        self.sample = sample


# ── 1. Enum shape ────────────────────────────────────────────────────────


def test_strength_has_exactly_three_members() -> None:
    """The knob is intentionally 3-position. Adding a 4th level
    should be a deliberate design change, not a sneaky addition.
    """
    assert {s.value for s in Strength} == {"low", "medium", "high"}


def test_strength_is_str_enum_for_cli_friendliness() -> None:
    """Inheriting from ``str`` lets CLI arg parsers pass strings
    straight through without conversion.
    """
    assert isinstance(Strength.LOW, str)
    assert Strength.LOW == "low"
    assert Strength("medium") is Strength.MEDIUM


def test_strength_is_re_exported_from_package_root() -> None:
    """``from humanize_en import Strength`` must work."""
    assert PackageStrength is Strength


# ── 2. _resolve_strength precedence ──────────────────────────────────────


@pytest.mark.parametrize(
    "strength,aggressive,expected",
    [
        # Explicit strength wins, regardless of aggressive.
        (Strength.LOW, None, Strength.LOW),
        (Strength.LOW, True, Strength.LOW),
        (Strength.LOW, False, Strength.LOW),
        (Strength.HIGH, False, Strength.HIGH),
        ("low", None, Strength.LOW),
        ("medium", None, Strength.MEDIUM),
        ("high", None, Strength.HIGH),
        # No strength -> aggressive bool drives the result.
        (None, True, Strength.HIGH),
        (None, False, Strength.MEDIUM),
        # Both absent -> default MEDIUM.
        (None, None, Strength.MEDIUM),
    ],
)
def test_resolve_strength_precedence(
    strength, aggressive, expected,
) -> None:
    assert _resolve_strength(strength, aggressive) is expected


def test_resolve_strength_rejects_invalid_string() -> None:
    """Invalid strength strings raise ValueError (not a silent
    fallback) so typos surface immediately.
    """
    with pytest.raises(ValueError):
        _resolve_strength("YOLO", None)


# ── 3. The three levels produce different prompts ────────────────────────


@pytest.fixture
def sample_text() -> str:
    return "This is a sample article that needs polishing."


@pytest.fixture
def sample_violations() -> list:
    return [_FakeViolation("blacklist_words", "delve", 2, "delve")]


def test_three_strengths_produce_distinct_prompts(
    sample_text, sample_violations,
) -> None:
    """Three different strengths must produce three different
    prompts. Otherwise the knob is cosmetic.
    """
    out = {
        s: build_humanize_postprocess_prompt(
            sample_text, sample_violations, strength=s,
        )
        for s in Strength
    }
    # Each pair must differ.
    assert out[Strength.LOW] != out[Strength.MEDIUM]
    assert out[Strength.MEDIUM] != out[Strength.HIGH]
    assert out[Strength.LOW] != out[Strength.HIGH]


def test_high_uses_aggressive_template(sample_text, sample_violations) -> None:
    """HIGH switches the template, not just the rule subset."""
    out = build_humanize_postprocess_prompt(
        sample_text, sample_violations, strength=Strength.HIGH,
    )
    assert "AI text deep rewrite pass" in out
    # The aggressive template inlines its own rules; the
    # HUMANIZE_RULES block from build_humanize_prompt must NOT appear.
    assert "Five core rules (violation = retraction)" not in out


def test_medium_includes_full_rules_block(
    sample_text, sample_violations,
) -> None:
    """MEDIUM uses POSTPROCESS_PROMPT with the full 8-section
    analysis scene by default.
    """
    out = build_humanize_postprocess_prompt(
        sample_text, sample_violations, strength=Strength.MEDIUM,
    )
    assert "AI text deep rewrite pass" not in out
    # All 8 sections must be substrings of the prompt.
    for section in (
        CORE_RULES, HARD_NEVER, HARD_LIMITS, WORDS_BLACKLIST,
        OPENING_DIVERSITY, SOUL_INJECTION, ASSERTION_TEMPLATE, SELF_CHECK,
    ):
        first_line = section.split("\n", 1)[0]
        assert first_line in out, f"MEDIUM missing section: {first_line}"


def test_low_uses_trimmed_three_section_block(
    sample_text, sample_violations,
) -> None:
    """LOW retains only CORE_RULES + WORDS_BLACKLIST + SELF_CHECK.
    The structural / rhythm / soul / assertion sections must NOT
    appear because LOW is meant to leave structurally-fine prose
    alone.
    """
    out = build_humanize_postprocess_prompt(
        sample_text, sample_violations, strength=Strength.LOW,
    )
    # Kept:
    for kept in (CORE_RULES, WORDS_BLACKLIST, SELF_CHECK):
        first_line = kept.split("\n", 1)[0]
        assert first_line in out, f"LOW missing kept section: {first_line}"
    # Dropped:
    for dropped in (
        HARD_NEVER, HARD_LIMITS, OPENING_DIVERSITY,
        SOUL_INJECTION, ASSERTION_TEMPLATE,
    ):
        first_line = dropped.split("\n", 1)[0]
        assert first_line not in out, (
            f"LOW unexpectedly contains section: {first_line}"
        )


def test_low_prompt_is_shorter_than_medium(
    sample_text, sample_violations,
) -> None:
    """LOW dropping 5 sections must visibly shrink the prompt -
    that's the whole point of the knob.
    """
    low = build_humanize_postprocess_prompt(
        sample_text, sample_violations, strength=Strength.LOW,
    )
    medium = build_humanize_postprocess_prompt(
        sample_text, sample_violations, strength=Strength.MEDIUM,
    )
    # Heuristic: dropping ~5 of 8 sections should remove >= 3000 chars.
    assert (len(medium) - len(low)) >= 3000, (
        f"LOW prompt only saved {len(medium) - len(low)} chars vs MEDIUM"
    )


# ── 4. Backward compatibility with the aggressive flag ───────────────────


def test_aggressive_true_equivalent_to_strength_high(
    sample_text, sample_violations,
) -> None:
    """The framework's writer_prompt_builder hook only knows
    about ``aggressive``. ``aggressive=True`` must keep producing
    the same prompt as ``strength=Strength.HIGH``.
    """
    via_aggressive = build_humanize_postprocess_prompt(
        sample_text, sample_violations, aggressive=True,
    )
    via_strength = build_humanize_postprocess_prompt(
        sample_text, sample_violations, strength=Strength.HIGH,
    )
    assert via_aggressive == via_strength


def test_aggressive_false_equivalent_to_strength_medium(
    sample_text, sample_violations,
) -> None:
    """Same back-compat check for the ``aggressive=False`` branch."""
    via_aggressive = build_humanize_postprocess_prompt(
        sample_text, sample_violations, aggressive=False,
    )
    via_strength = build_humanize_postprocess_prompt(
        sample_text, sample_violations, strength=Strength.MEDIUM,
    )
    assert via_aggressive == via_strength


def test_default_call_is_medium(sample_text, sample_violations) -> None:
    """No strength, no aggressive -> MEDIUM. This is the main path
    every existing caller takes today.
    """
    default_out = build_humanize_postprocess_prompt(
        sample_text, sample_violations,
    )
    medium_out = build_humanize_postprocess_prompt(
        sample_text, sample_violations, strength=Strength.MEDIUM,
    )
    assert default_out == medium_out


def test_explicit_strength_overrides_aggressive(
    sample_text, sample_violations,
) -> None:
    """If both are supplied, ``strength`` wins. Mixing the two
    should never produce surprise -- precedence is documented.
    """
    out = build_humanize_postprocess_prompt(
        sample_text, sample_violations,
        strength=Strength.LOW, aggressive=True,
    )
    # LOW path emits the full rules-block POSTPROCESS_PROMPT, not
    # the aggressive template -- proves strength took precedence.
    assert "AI text deep rewrite pass" not in out
    # And the LOW kept-section is present.
    assert "Five core rules" in out


# ── 5. String form works in every callsite ───────────────────────────────


@pytest.mark.parametrize("variant", ["low", "medium", "high"])
def test_string_form_equivalent_to_enum(
    variant, sample_text, sample_violations,
) -> None:
    """CLI users will pass plain strings. The dispatcher must accept
    them and produce identical output to the enum form.
    """
    via_str = build_humanize_postprocess_prompt(
        sample_text, sample_violations, strength=variant,
    )
    via_enum = build_humanize_postprocess_prompt(
        sample_text, sample_violations, strength=Strength(variant),
    )
    assert via_str == via_enum
