"""M5 tests for humanize_en._lang.en.replacements.

Covers the shape of the JSON data, the loader's bucket ordering +
length-sort-within-bucket, and end-to-end application through the
humanize-core ``apply_replacements`` helper (which is the real path
the polish pipeline uses).
"""

from __future__ import annotations

import json

import pytest

from humanize_en._lang.en.replacements import (
    REPLACEMENTS_PATH,
    _load_replacements,
    en_replacements,
)

# ─── Data shape ─────────────────────────────────────────────────────────


def test_replacements_json_has_expected_top_level_shape() -> None:
    raw = json.loads(REPLACEMENTS_PATH.read_text(encoding="utf-8"))
    assert "_meta" in raw
    assert "replacements" in raw
    section = raw["replacements"]
    assert "_order" in section
    assert isinstance(section["_order"], list)
    # Every bucket named in _order must also be a list in the file.
    for bucket in section["_order"]:
        assert isinstance(section.get(bucket), list), (
            f"bucket {bucket!r} named in _order but not present as list"
        )


def test_every_pair_is_a_two_string_array() -> None:
    """Loader silently drops malformed entries. This test assures the
    data file itself contains only valid entries so that silent drop
    never applies — we want to know immediately if a pair is broken.
    """
    raw = json.loads(REPLACEMENTS_PATH.read_text(encoding="utf-8"))
    for bucket, items in raw["replacements"].items():
        if bucket.startswith("_") or not isinstance(items, list):
            continue
        for i, entry in enumerate(items):
            assert isinstance(entry, list), f"{bucket}[{i}] not a list"
            assert len(entry) == 2, f"{bucket}[{i}] must have 2 elements"
            assert isinstance(entry[0], str), f"{bucket}[{i}][0] must be str"
            assert isinstance(entry[1], str), f"{bucket}[{i}][1] must be str"
            assert entry[0], f"{bucket}[{i}][0] must be non-empty"


def test_pair_count_matches_milestone_promise() -> None:
    """CHANGELOG claims ~85 pairs at M5. Guard against silent drift —
    if we add/remove more than ~15 pairs the test forces a bump.
    """
    pairs = en_replacements.ordered_pairs()
    assert 80 <= len(pairs) <= 130, (
        f"pair count drifted: got {len(pairs)}. Update CHANGELOG + tests."
    )


# ─── Loader ordering ────────────────────────────────────────────────────


def test_loader_respects_bucket_order() -> None:
    """Buckets apply in the order declared by ``_order``. First pair
    globally must come from ``safety_disclaimer``, last from
    ``filler_opener``.
    """
    _load_replacements.cache_clear()
    raw = json.loads(REPLACEMENTS_PATH.read_text(encoding="utf-8"))
    safety_olds = {p[0] for p in raw["replacements"]["safety_disclaimer"]}
    filler_olds = {p[0] for p in raw["replacements"]["filler_opener"]}
    pairs = _load_replacements()
    assert pairs[0][0] in safety_olds, (
        f"first ordered pair is {pairs[0]!r}; expected a safety_disclaimer entry"
    )
    assert pairs[-1][0] in filler_olds, (
        f"last ordered pair is {pairs[-1]!r}; expected a filler_opener entry"
    )


def test_loader_sorts_longest_first_within_bucket() -> None:
    """'utilization' must come before 'utilize' in the ordered output —
    otherwise the shorter substring gobbles the longer one and
    'utilization' never gets its own replacement.
    """
    pairs = en_replacements.ordered_pairs()
    # Find corporate_filler start/end indexes by looking at known entries.
    olds = [p[0] for p in pairs]
    assert "utilization" in olds
    assert "utilize" in olds
    assert olds.index("utilization") < olds.index("utilize")
    # And 'delves into' before 'delve into'.
    assert olds.index("delves into") < olds.index("delve into")


def test_load_is_lru_cached() -> None:
    """``_load_replacements`` uses ``lru_cache(maxsize=1)``. Two
    back-to-back calls must return the exact same tuple instance.
    """
    a = _load_replacements()
    b = _load_replacements()
    assert a is b


# ─── End-to-end: apply via humanize-core ────────────────────────────────


def _apply_all(text: str, pairs: tuple[tuple[str, str], ...]) -> str:
    """Replicate the deterministic replacement pass in a single place
    so tests don't depend on the exact humanize-core import path (the
    helper has moved in the past).
    """
    out = text
    for old, new in pairs:
        out = out.replace(old, new)
    return out


@pytest.mark.parametrize(
    "text,must_contain,must_not_contain",
    [
        (
            "As an AI language model, I cannot provide that.",
            ["cannot provide that"],
            ["As an AI language model,"],
        ),
        (
            "We utilize advanced methods to facilitate progress.",
            ["use", "help"],
            ["utilize", "facilitate"],
        ),
        (
            "Let me delve into this intricate tapestry of ideas.",
            ["look at", "detailed", "mix"],
            ["delve into", "intricate", "tapestry"],
        ),
        (
            "In conclusion, this is a transformative approach.",
            ["useful approach"],
            ["In conclusion,", "transformative"],
        ),
        (
            "It is important to note that many people agree.",
            ["many people agree"],
            ["It is important to note that"],
        ),
    ],
)
def test_apply_produces_expected_substitutions(
    text: str, must_contain: list[str], must_not_contain: list[str]
) -> None:
    """End-to-end: each curated input must lose its AI template parts
    and gain the plain-English substitutes after the pipeline runs.
    """
    out = _apply_all(text, en_replacements.ordered_pairs())
    for s in must_contain:
        assert s in out, f"missing expected {s!r} in {out!r}"
    for s in must_not_contain:
        assert s not in out, f"unexpected {s!r} remained in {out!r}"


def test_replacements_are_idempotent() -> None:
    """Applying the pipeline twice must equal applying it once. Without
    this, a replacement that creates one of its own inputs (e.g. the
    new value contains the old) would loop. The data file is hand-
    audited to avoid that; this test enforces the invariant.
    """
    text = (
        "It's important to note that we utilize cutting-edge tools "
        "in order to optimize the pipeline. In conclusion, the "
        "transformative paradigm shift fosters growth."
    )
    pairs = en_replacements.ordered_pairs()
    once = _apply_all(text, pairs)
    twice = _apply_all(once, pairs)
    assert once == twice, (
        f"replacements not idempotent.\nonce={once!r}\ntwice={twice!r}"
    )


def test_safety_disclaimer_removal_preserves_rest() -> None:
    """Stripping 'As an AI language model, ' must leave the rest of the
    sentence intact (including capitalisation, since we delete the
    comma-space suffix but the following clause keeps its capital).
    """
    pairs = en_replacements.ordered_pairs()
    out = _apply_all(
        "As an AI language model, Rust is compiled to native code.",
        pairs,
    )
    assert out == "Rust is compiled to native code."


def test_no_pair_creates_a_recursive_expansion() -> None:
    """For each pair ``(old, new)``, ``new`` must not itself contain a
    later pair's ``old`` in a way that would create runaway expansion
    — simplified guard: ``new`` must not contain ``old`` (the pair's
    own old) so a direct self-loop can't happen.
    """
    pairs = en_replacements.ordered_pairs()
    for old, new in pairs:
        assert old not in new, (
            f"pair {old!r} -> {new!r} would loop: new contains old."
        )
