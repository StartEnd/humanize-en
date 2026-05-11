"""M3 tests for the EN lexical + phrase rule detector.

Each test pins one rule's expected behaviour so future rule
additions / weight changes are detected by CI rather than discovered
in production. Tests use minimal "rule X fires once, rule Y doesn't
fire" assertions so a rebalance doesn't have to re-author them.
"""

from __future__ import annotations

import json

import pytest

from humanize_en._lang.en.detector import (
    RULES_PATH,
    Violation,
    _apply_threshold_ladder,
    _build_phrase_regex,
    _build_word_regex,
    _load_rules,
    _strip_codeblocks,
    en_detector,
    score,
)

# ─── Rule data file ─────────────────────────────────────────────────────


def test_rules_json_loads_with_expected_top_level_keys() -> None:
    """``rules.json`` must carry both rule buckets and ``_meta``.
    Catches accidental schema drift without forcing every test to
    know the rule contents.
    """
    rules = _load_rules()
    assert "_meta" in rules
    assert "blacklist_words" in rules
    assert "blacklist_phrases" in rules
    assert rules["_meta"]["version"].startswith(("0.", "1."))


def test_each_rule_declares_required_fields() -> None:
    """Every concrete rule (non-``_`` prefixed) must specify
    ``weight``, ``patterns``, and at least one threshold. A missing
    field would silently zero-out the rule at runtime — catch here.
    """
    rules = _load_rules()
    for bucket in ("blacklist_words", "blacklist_phrases"):
        for name, conf in rules[bucket].items():
            if name.startswith("_") or not isinstance(conf, dict):
                continue
            assert "weight" in conf, f"{bucket}.{name}: missing weight"
            assert "patterns" in conf, f"{bucket}.{name}: missing patterns"
            assert isinstance(conf["patterns"], list)
            assert len(conf["patterns"]) > 0
            has_threshold = (
                "soft_threshold" in conf or "hard_threshold" in conf
            )
            assert has_threshold, f"{bucket}.{name}: needs soft_/hard_threshold"


def test_rule_count_matches_milestone_promise() -> None:
    """README + CHANGELOG promise ~16 rules at M3. If we lose or add
    rules without a CHANGELOG bump this test forces a discussion.
    """
    rules = _load_rules()
    concrete_words = [n for n in rules["blacklist_words"] if not n.startswith("_")]
    concrete_phrases = [n for n in rules["blacklist_phrases"] if not n.startswith("_")]
    total = len(concrete_words) + len(concrete_phrases)
    assert 12 <= total <= 25, (
        f"rule count drifted: got {total} "
        f"({len(concrete_words)} words + {len(concrete_phrases)} phrases). "
        f"Update tests + CHANGELOG together when adding/removing rules."
    )


# ─── Threshold ladder ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "count,weight,soft,hard,expected",
    [
        # No thresholds → full weight per hit.
        (3, 5, None, None, 15.0),
        # Below soft → half weight.
        (2, 4, 3, 10, 4.0),  # 2 * 4 * 0.5 = 4
        # In soft-hard band → full weight.
        (5, 4, 3, 10, 20.0),
        # Above hard → full band + overshoot.
        (12, 4, 3, 10, 10 * 4 + (12 - 10) * 4),  # 48
        # soft=0 means "no soft band, full weight on first hit".
        (1, 8, 0, 1, 8.0),
        # hard=0 means "any hit is overshoot, all extra-weighted".
        (3, 15, 0, 0, 0 * 15 + (3 - 0) * 15),  # 45
    ],
)
def test_apply_threshold_ladder(
    count: int, weight: int, soft: int | None, hard: int | None, expected: float
) -> None:
    """Lock the ladder's mapping. Any change here must be intentional
    and accompanied by a rule re-calibration on HC3-en.
    """
    assert _apply_threshold_ladder(count, weight, soft, hard) == expected


# ─── Regex builders ─────────────────────────────────────────────────────


def test_word_regex_respects_apostrophe_boundary() -> None:
    """``body's`` must match as a complete token in ``the body's
    natural defense``, but not as a fragment of ``somebody'soft``.
    """
    rx = _build_word_regex(["body's", "person's"])
    assert rx.search("the body's natural defense")
    assert not rx.search("somebody'softener")


def test_word_regex_is_case_insensitive() -> None:
    rx = _build_word_regex(["delve", "meticulous"])
    assert rx.search("Delve")
    assert rx.search("METICULOUS")
    assert rx.search("delving") is None  # not in the pattern set


def test_phrase_regex_flexibilises_internal_whitespace() -> None:
    """A pattern ``"it is important to note"`` must still match when
    the input uses double spaces or wraps across a newline.
    """
    rx = _build_phrase_regex(["it is important to note"])
    assert rx.search("It  is  important  to note that")
    assert rx.search("it is important to\nnote that")


# ─── Per-rule behaviour ─────────────────────────────────────────────────


def test_clean_text_produces_zero_score() -> None:
    """A short, naturally-phrased passage with no rule patterns
    must score zero. Regression guard for accidental false positives
    when adding new rules.
    """
    s = score("The cat sat on the mat. Outside, it had started to rain.")
    assert s.total == 0.0
    assert s.violations == []


def test_meta_hedge_phrase_fires_on_single_hit() -> None:
    """``meta_hedge`` has ``hard_threshold=1`` and weight 8 — a single
    'it is important to note' hit must produce a non-zero score and
    show up in the violations list with the right rule name + sample.
    """
    s = score("It is important to note that water is wet.")
    rule_names = {v.rule for v in s.violations}
    assert "meta_hedge" in rule_names
    v = next(v for v in s.violations if v.rule == "meta_hedge")
    assert v.count == 1
    assert v.score > 0
    assert "important" in v.sample.lower()


def test_ai_safety_disclaimer_alone_pushes_into_high_band() -> None:
    """The disclaimer rule has weight 15 with ``hard_threshold=0`` —
    a single hit on a short text must put the score into HIGH /
    VERY_HIGH after length normalisation.
    """
    s = score(
        "As an AI language model, I do not have personal opinions. "
        "However, I can summarize the topic."
    )
    rule_names = {v.rule for v in s.violations}
    assert "ai_safety_disclaimer" in rule_names
    assert s.total >= 25, f"safety disclaimer should hit at least MEDIUM, got {s.total}"


def test_corporate_filler_word_fires() -> None:
    """A sentence dense in Plain-English-Campaign-flagged corporate
    verbs must trip ``corporate_filler``.
    """
    s = score(
        "We will leverage our synergies to optimize and streamline "
        "the workflow and facilitate cross-team utilization."
    )
    rule_names = {v.rule for v in s.violations}
    assert "corporate_filler" in rule_names


def test_liang_2024_tells_fire_on_modern_chatgpt_text() -> None:
    """The Liang-2024 lexical signature — 'delve, meticulous, realm,
    intricate, ecosystem' — must trip ``liang_2024_lexical_tells``.
    """
    s = score(
        "Let us delve into the intricate ecosystem of modern realms, "
        "navigating the multifaceted landscape with meticulous care."
    )
    rule_names = {v.rule for v in s.violations}
    assert "liang_2024_lexical_tells" in rule_names


def test_codeblocks_are_stripped_before_matching() -> None:
    """``utilize()`` inside a fenced code block must not trip
    ``corporate_filler`` — that's the entire reason
    :func:`_strip_codeblocks` exists.
    """
    text = (
        "Here's how to call the API:\n"
        "```python\n"
        "client.utilize(synergy=True)  # facilitates leverage\n"
        "```\n"
        "It's a simple call."
    )
    s = score(text)
    rule_names = {v.rule for v in s.violations}
    assert "corporate_filler" not in rule_names


def test_inline_code_is_stripped() -> None:
    """Same for inline code: ``backtick utilize backtick`` must not
    trip the rule.
    """
    text = "Call `utilize()` — it returns the result."
    s = score(text)
    assert "corporate_filler" not in {v.rule for v in s.violations}


def test_strip_codeblocks_helper() -> None:
    out = _strip_codeblocks("foo ```python\nbar\n``` baz `qux` quux")
    assert "bar" not in out
    assert "qux" not in out
    assert "foo" in out and "baz" in out and "quux" in out


# ─── Discrimination ─────────────────────────────────────────────────────


def test_ai_heavy_paragraph_scores_much_higher_than_natural() -> None:
    """Direction-only smoke: an AI-template-laden paragraph must score
    higher than a personal narrative. Threshold is loose so weight
    re-tuning doesn't break the test.
    """
    ai_heavy = (
        "It is important to note that effective communication is crucial "
        "in modern workplaces. Moreover, clear communication helps to foster "
        "collaboration. Furthermore, it is essential to leverage diverse "
        "perspectives. In conclusion, organizations should optimize their "
        "communication strategies to navigate the multifaceted challenges "
        "of the modern landscape."
    )
    natural = (
        "I learned to ride a bike when I was seven, in the alley behind "
        "our flat. My dad held the seat, jogging alongside until he wasn't "
        "there anymore. I crashed into a bin. He laughed so hard he had to "
        "lean on the wall."
    )
    s_ai = score(ai_heavy)
    s_nat = score(natural)
    assert s_ai.total > s_nat.total
    assert s_ai.total >= 25  # at least MEDIUM band


def test_length_normalization_caps_score_for_long_text() -> None:
    """The length normalisation divides by ``max(1, len/3000)``, so
    texts shorter than ~3000 chars are not penalised. A 12 000-char
    repetition of the same AI-heavy block must yield a score
    *similar* to (not 4× larger than) the 3 000-char version.

    Specifically: 4× the input length with the same per-unit
    density must produce ≤ 25% extra score (the small slack accounts
    for ``min(100, ...)`` saturation and rounding).
    """
    # ~145 chars per block; need ≥ 21 to cross 3000.
    block = (
        "It is important to note that effective communication is crucial. "
        "Moreover, leveraging synergies is essential. "
    )
    base = score(block * 21)         # ~ 3 045 chars (norm_factor ≈ 1.0)
    quadrupled = score(block * 84)   # ~ 12 180 chars (norm_factor ≈ 4.06)
    # With proper normalisation, quadrupled should be similar to base.
    assert quadrupled.total <= base.total * 1.25, (
        f"normalisation failed: base={base.total} → 4x={quadrupled.total}"
    )


# ─── Detector adapter ───────────────────────────────────────────────────


def test_en_detector_version_tracks_rules_meta() -> None:
    """The ``EnDetector.version`` attribute is read from
    ``rules.json::_meta.version`` at construction. Verifying it
    matches the on-disk file catches misaligned import order or
    accidental caching of the M1 stub version.
    """
    on_disk = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    assert en_detector.version == on_disk["_meta"]["version"]


def test_violations_carry_sample_snippets() -> None:
    """Every triggered violation must surface a literal matched
    snippet so the polish prompt can quote it back to the LLM.
    """
    s = score(
        "It is worth noting that the company's transformative paradigm "
        "is incredibly innovative."
    )
    assert s.violations
    for v in s.violations:
        assert isinstance(v, Violation)
        assert v.sample
        assert len(v.sample) > 0
