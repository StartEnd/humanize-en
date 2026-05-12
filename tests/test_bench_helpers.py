"""Unit tests for the plan-M8 benchmark helper modules.

Pin behavioural contracts on the two stdlib-only helpers
(``tests/bench/_data.py``, ``tests/bench/_readability.py``) so
the gate tests above them can rely on documented inputs and
outputs. These run in CI even when no optional benchmark deps
are installed.
"""

from __future__ import annotations

import pytest

from tests.bench._data import BenchSample, load_samples
from tests.bench._readability import (
    count_sentences,
    count_syllables,
    count_words,
    flesch_kincaid_grade,
)

# ─── _data.py ──────────────────────────────────────────────────────────


class TestLoadSamples:
    def test_bundled_returns_bench_samples(self) -> None:
        samples = load_samples("bundled")
        assert all(isinstance(s, BenchSample) for s in samples)

    def test_each_sample_has_required_fields(self) -> None:
        for s in load_samples("bundled"):
            assert s.id
            assert s.text
            assert s.domain in {"news", "blog", "academic", "business"}
            assert s.source == "bundled"
            assert s.length_chars == len(s.text)

    def test_unknown_source_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="unknown sample source"):
            load_samples("not_a_source")  # type: ignore[arg-type]

    def test_n_cap_does_not_pad(self) -> None:
        """Asking for more samples than the corpus has returns the corpus,
        not a padded sequence."""
        all_samples = load_samples("bundled")
        big = load_samples("bundled", n=10_000)
        assert len(big) == len(all_samples)

    def test_domain_filter_returns_subset(self) -> None:
        academic = load_samples("bundled", domain="academic")
        assert academic
        assert all(s.domain == "academic" for s in academic)

    def test_domain_filter_for_unknown_returns_empty(self) -> None:
        out = load_samples("bundled", domain="zzz_no_such_domain")
        assert out == []

    def test_sample_dataclass_is_frozen(self) -> None:
        s = load_samples("bundled", n=1)[0]
        with pytest.raises((AttributeError, TypeError)):
            s.id = "mutated"  # type: ignore[misc]


# ─── _readability.py ───────────────────────────────────────────────────


class TestReadabilityHelpers:
    def test_word_count(self) -> None:
        assert count_words("The quick brown fox.") == 4
        assert count_words("") == 0
        assert count_words("don't worry") == 2  # contraction stays as one

    def test_sentence_count_minimum_one(self) -> None:
        """Empty / unterminated text counts as one sentence (avoids
        divide-by-zero in the FKGL formula)."""
        assert count_sentences("") == 1
        assert count_sentences("no terminator here") == 1
        assert count_sentences("One. Two. Three.") == 3
        assert count_sentences("Question? Yes! Done.") == 3

    def test_syllable_count(self) -> None:
        # "the" is one syllable; vowel-group catches it.
        assert count_syllables("the") == 1
        # "the cat" is two syllables.
        assert count_syllables("the cat") == 2
        # Silent-e: "make" = 1 (not 2).
        assert count_syllables("make") == 1
        # 'le' suffix exception: "table" = 2.
        assert count_syllables("table") == 2
        # Empty.
        assert count_syllables("") == 0

    def test_fkgl_returns_zero_for_empty(self) -> None:
        assert flesch_kincaid_grade("") == 0.0
        assert flesch_kincaid_grade("   \n\n  ") == 0.0

    @pytest.mark.parametrize(
        "text,grade_floor,grade_ceiling",
        [
            ("See spot run. See spot jump.", -10, 5),  # very simple
            (
                "The quick brown fox jumps over the lazy dog. "
                "Pack my box with five dozen liquor jugs.",
                0, 8,
            ),
            (
                "The proliferation of large language models has "
                "fundamentally transformed natural language processing.",
                12, 25,  # academic
            ),
        ],
    )
    def test_fkgl_in_expected_range(
        self, text: str, grade_floor: int, grade_ceiling: int,
    ) -> None:
        """FKGL is a heuristic; we don't pin exact numbers, just plausible
        ranges. If a refactor of the syllable counter pushes one of these
        out of range, the test catches it."""
        grade = flesch_kincaid_grade(text)
        assert grade_floor <= grade <= grade_ceiling, (
            f"text {text[:40]!r} produced FKGL {grade}, expected "
            f"[{grade_floor}, {grade_ceiling}]"
        )

    def test_fkgl_increases_with_complexity(self) -> None:
        """Longer words / longer sentences should move FKGL up. This is
        the core monotonicity property of Flesch-Kincaid; any
        off-by-one in the formula breaks it."""
        simple = flesch_kincaid_grade("Cat sat. Dog ran.")
        complex_ = flesch_kincaid_grade(
            "The aforementioned phenomenon necessitates "
            "interdisciplinary collaboration among stakeholders."
        )
        assert complex_ > simple
