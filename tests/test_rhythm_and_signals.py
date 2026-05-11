"""M4 tests — structural / rhythm / fake_human / soul_signals.

These categories are less lexical-regex and more statistics-over-
structure, so tests focus on: threshold crossings, metric values in
stats, has_notes gating, and end-to-end discrimination on essay-
shaped AI text that didn't previously trip the M3 rules.
"""

from __future__ import annotations

import pytest

from humanize_en._lang.en.detector import (
    _check_soul_signals,
    _check_structural,
    _coef_of_variation,
    _load_rules,
    score,
)

# ─── Rules data shape ────────────────────────────────────────────────────


def test_m4_buckets_carry_concrete_rules() -> None:
    """After M4 all four buckets must have at least one concrete rule
    (non-``_``-prefixed dict entry). A missing rule category suggests
    accidental revert to the M3 scaffold.
    """
    rules = _load_rules()
    for bucket in ("structural_rules", "rhythm_rules", "fake_human", "soul_signals"):
        concrete = [
            n for n, conf in rules[bucket].items()
            if not n.startswith("_") and isinstance(conf, dict)
        ]
        assert len(concrete) >= 1, f"{bucket} has no concrete rules after M4"


def test_m4_rule_count_within_promised_range() -> None:
    """README + CHANGELOG promise ~10 M4 rules; guard against drift."""
    rules = _load_rules()
    m4_total = sum(
        1
        for bucket in ("structural_rules", "rhythm_rules", "fake_human", "soul_signals")
        for name, conf in rules[bucket].items()
        if not name.startswith("_") and isinstance(conf, dict)
    )
    assert 8 <= m4_total <= 15, (
        f"M4 rule count drifted: got {m4_total}. Update README + CHANGELOG."
    )


# ─── Structural rules ────────────────────────────────────────────────────


def test_heading_density_fires_on_heading_heavy_essay() -> None:
    """Markdown-heading-per-paragraph AI essay outputs must trip
    ``heading_density``. Each '## Section' emit at paragraph start
    counts once.
    """
    text = (
        "## Introduction\n\nSomething brief here.\n\n"
        "## Background\n\nMore brief content.\n\n"
        "## Method\n\nA bit of method.\n\n"
        "## Results\n\nShort results.\n\n"
        "## Conclusion\n\nEnd of essay."
    )
    # Pad to > 500 chars so the min_text_length gate opens.
    text = text + ("\n\nFiller sentence. " * 20)
    s = score(text)
    rule_names = {v.rule for v in s.violations}
    assert "heading_density" in rule_names


def test_list_density_fires_on_listicle() -> None:
    """A text where > 50% of non-empty lines start with bullet /
    numbered markers must trip ``list_density``.
    """
    text = (
        "Here is a plan.\n\n"
        "- First point to consider\n"
        "- Second point about something\n"
        "- Third idea that matters\n"
        "- Fourth take on the topic\n"
        "- Fifth and related note\n"
        "- Sixth follow-up detail\n"
        "- Seventh closing thought\n"
    )
    text = text * 3  # Pad past min_text_length.
    s = score(text)
    rule_names = {v.rule for v in s.violations}
    assert "list_density" in rule_names


def test_structural_rules_skip_short_text() -> None:
    """Both structural rules have ``min_text_length >= 500``. Short
    bullet lists or heading-only sketches must not be penalised.
    """
    short = "- one\n- two\n- three"
    rules = _load_rules()
    out = _check_structural(short, rules["structural_rules"])
    assert out == []


# ─── Rhythm rules ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "values,expected_cv_band",
    [
        ([10, 10, 10, 10, 10], (0.0, 0.01)),  # Uniform → ~0 CV
        ([5, 10, 15, 20, 25], (0.4, 0.7)),    # Varied → clear non-zero
        ([], (0.0, 0.01)),                    # Empty → safe 0
    ],
)
def test_coef_of_variation_basic(
    values: list[int], expected_cv_band: tuple[float, float]
) -> None:
    """CV helper must be safe on empty/short inputs and give the
    right magnitude on the two extreme cases.
    """
    cv = _coef_of_variation(values)
    low, high = expected_cv_band
    assert low <= cv <= high


def test_sentence_length_cv_fires_on_uniform_sentences() -> None:
    """Ten sentences of exactly similar length (stddev ≈ 0) must
    push sentence_cv below 0.35 and fire ``sentence_length_cv``.
    """
    text = " ".join([
        "This sentence has exactly seven short words today.",
        "Another sentence uses exactly eight words right here.",
        "Yet another has exactly eight compact words here.",
        "One more sentence with eight evenly placed words.",
        "Final sentence has exactly eight neatly formed words.",
        "Here again are eight words in one sentence.",
        "Eight words here again in this short one.",
        "Eight more words fitting a similar pattern here.",
    ])
    s = score(text)
    rule_names = {v.rule for v in s.violations}
    assert "sentence_length_cv" in rule_names
    assert "sentence_cv" in s.stats


def test_paragraph_uniformity_fires_on_identical_paragraphs() -> None:
    """Three equal-length paragraphs must push paragraph_cv below 0.3
    and trip ``paragraph_uniformity``.
    """
    para = (
        "This is a single paragraph of a moderately reasonable length "
        "designed to match its siblings closely so the CV falls low."
    )
    text = "\n\n".join([para] * 4)
    s = score(text)
    rule_names = {v.rule for v in s.violations}
    assert "paragraph_uniformity" in rule_names


def test_para_opening_enumeration_fires_on_numbered_paragraphs() -> None:
    """Three or more paragraphs starting with 'First,' / '1.' /
    'Moreover,' must trip ``para_opening_enumeration``.
    """
    text = (
        "First, consider that software is hard to test.\n\n"
        "Second, production environments always differ from staging.\n\n"
        "Third, users find bugs that internal testers miss.\n\n"
        "Finally, rollback plans must always be ready.\n\n"
        "Moreover, good teams write post-mortems that blame systems."
    )
    s = score(text)
    rule_names = {v.rule for v in s.violations}
    assert "para_opening_enumeration" in rule_names


def test_rhythm_stats_populated_even_when_no_rule_fires() -> None:
    """Even on natural text where rhythm rules don't fire, the metrics
    themselves must be reported so downstream UIs can show them.
    """
    text = (
        "I rode my bike home in the rain last night. "
        "The streets shone under the yellow lamps. "
        "A fox crossed my path near the bridge and "
        "stared for just a moment. Then it was gone, "
        "and I was pedalling alone again. The chain "
        "needs oil; it's been squeaking for a week."
    )
    s = score(text)
    assert "sentence_cv" in s.stats


# ─── Fake-human rules ────────────────────────────────────────────────────


def test_vague_personal_experience_fires_without_notes() -> None:
    """A text with 'In my experience' and similar pseudo-specifics
    must trip ``vague_personal_experience`` when ``has_notes=False``.
    """
    text = (
        "In my personal experience, working with microservices is hard. "
        "I've been doing this for 10 years. "
        "As someone who has worked with Kubernetes, I can tell you."
    )
    s = score(text, has_notes=False)
    rule_names = {v.rule for v in s.violations}
    assert "vague_personal_experience" in rule_names


def test_has_notes_skips_fake_human_pass() -> None:
    """Same text as above but with ``has_notes=True`` must NOT fire
    ``vague_personal_experience``. The stats dict must advertise the
    skip so the debug trail is honest.
    """
    text = (
        "In my personal experience, working with microservices is hard. "
        "I've been doing this for 10 years."
    )
    s = score(text, has_notes=True)
    rule_names = {v.rule for v in s.violations}
    assert "vague_personal_experience" not in rule_names
    assert s.stats.get("fake_human_check", "").startswith("skipped")


def test_generic_authority_claim_fires() -> None:
    text = (
        "Trust me, the system is fine. I strongly believe that our approach "
        "will work out. I firmly believe that this pattern scales."
    )
    s = score(text)
    rule_names = {v.rule for v in s.violations}
    assert "generic_authority_claim" in rule_names


# ─── Soul signals (penalty for MISSING human fingerprints) ──────────────


def test_concrete_specifics_fires_on_abstract_text() -> None:
    """A long abstract text lacking proper nouns / numbers / dates must
    trigger ``concrete_specifics``. Human writing about anything real
    usually touches a place, a brand, a year, or a count.
    """
    abstract = (
        "It is important to reflect on the nature of things in general. "
        "One must consider how processes relate to each other in the "
        "abstract. There are many factors that affect outcomes, and a "
        "variety of considerations that come into play. Ultimately, the "
        "relationship between cause and effect is nuanced and complex, "
        "depending on circumstances and context. Factors vary, and "
        "considerations evolve over time in ways that are difficult to "
        "predict with certainty."
    )
    s = score(abstract)
    rule_names = {v.rule for v in s.violations}
    assert "concrete_specifics" in rule_names


def test_concrete_specifics_satisfied_by_proper_nouns_and_numbers() -> None:
    """Text laden with names, years, and counts must NOT fire
    ``concrete_specifics``. Guards the false-positive side.
    """
    concrete = (
        "Last week I met Alex Chen at the Blue Bottle on Mission Street. "
        "He works at Stripe and has been there since 2019. We talked "
        "about their Series H round and the 42% growth they hit last "
        "quarter. He mentioned that San Francisco rents have dropped "
        "18 percent since the pandemic."
    )
    # Need to pad past min_text_length=300 but keep specifics dense.
    concrete = concrete + " " + concrete
    s = score(concrete)
    rule_names = {v.rule for v in s.violations}
    assert "concrete_specifics" not in rule_names


def test_contrarian_hinge_fires_when_missing() -> None:
    """Text that's pure enumeration with zero argumentative hinges
    in > 300 chars must trip ``contrarian_hinge``.
    """
    pure_enum = (
        "Software has many good properties to consider carefully. "
        "Software is composable and reasonably well-structured. "
        "Software is flexible in deployment choices across teams. "
        "Software is cheap to copy and easy to redistribute. Software "
        "enables automation and saves repeated manual work. Software "
        "can be versioned and rolled back when mistakes happen. "
        "Software supports testing and fast iteration cycles. "
        "Software scales with compute resources and load patterns. "
        "Software runs on many platforms and diverse architectures. "
        "Software integrates via APIs and standardized protocols."
    )
    # Contains no 'but', 'however', 'actually', 'unless', etc.
    assert len(pure_enum) >= 300, f"test text must be >=300 chars, got {len(pure_enum)}"
    s = score(pure_enum)
    rule_names = {v.rule for v in s.violations}
    assert "contrarian_hinge" in rule_names


def test_contrarian_hinge_satisfied_by_a_single_but() -> None:
    """Just one hinge word is enough to satisfy the signal."""
    with_hinge = (
        "Software has many good properties. Software is composable and "
        "flexible. However, software is also brittle in production. "
        "Software is cheap to copy, but operations costs are real. "
        "Software enables automation. Software can be versioned. Software "
        "supports testing. Software scales with compute resources."
    )
    s = score(with_hinge)
    rule_names = {v.rule for v in s.violations}
    assert "contrarian_hinge" not in rule_names


def test_soul_signals_skip_short_text() -> None:
    """Soul signals have ``min_text_length=300``. Short texts must
    not fire either rule — we can't meaningfully assess argumentation
    quality in a tweet.
    """
    short = "Here's a short note about one thing."
    rules = _load_rules()
    out = _check_soul_signals(short, rules["soul_signals"])
    assert out == []


# ─── Integration: M4 catches AI essays M3 would miss ────────────────────


def test_ai_essay_without_blacklist_hits_still_scores_via_rhythm() -> None:
    """An AI essay engineered to dodge the M3 word/phrase blacklist
    (no 'it is important to note', no 'delve', no 'utilize') should
    still score non-trivially thanks to M4's rhythm + structural +
    soul_signals rules catching its uniform shape.
    """
    text = (
        "Software has shaped the modern economy in profound ways.\n\n"
        "First, it reduced costs of information sharing globally.\n\n"
        "Second, it enabled new kinds of work across borders.\n\n"
        "Third, it changed how teams coordinate on complex tasks.\n\n"
        "Finally, software eats through older business models quickly."
    )
    s = score(text)
    # M4 rules must fire even without M3 hits.
    cats = {v.category for v in s.violations}
    assert cats & {"rhythm_rules", "soul_signals", "structural_rules"}, (
        f"no M4 categories fired; violations = {[(v.category, v.rule) for v in s.violations]}"
    )
