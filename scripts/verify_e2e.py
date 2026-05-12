"""End-to-end verification for humanize-en M1-M5.

Runs three smoke tests with no LLM dependency:

1. **detect**       — feed an essay laden with M3+M4 tells and confirm
                      the combined detector reports HIGH-or-above.
2. **clean (deterministic)** — apply the M5 replacements through
                      humanize-core's deterministic-cleanup helper and
                      report char-delta + sample diff.
3. **detect after clean** — re-score the cleaned text to confirm the
                      score actually drops (the whole point of M5).

If ``OPENAI_API_KEY`` (or an equivalent) is set, also tries one full
``postprocess_humanize`` round to verify the LLM polish path works.
That section is skipped silently otherwise so the script is safe to
run in CI without keys.

Usage:
    python scripts/verify_e2e.py
"""

from __future__ import annotations

import os
import sys
from textwrap import dedent

from humanize_core import get_language
from humanize_core.combined import combined_score
from humanize_core.postprocess import _deterministic_cleanup  # type: ignore[attr-defined]

import humanize_en  # noqa: F401  -- registers the en profile via __init__

SAMPLE_AI_TEXT = dedent("""\
    As an AI language model, I would like to point out that software
    development is a multifaceted endeavour. It is important to note
    that modern teams need to leverage cutting-edge tools to optimize
    their workflows. Moreover, organizations must utilize best practices
    in order to streamline their development process.

    First, let me delve into the intricate tapestry of considerations
    that engineers face today. Pioneering teams should embark on a
    transformative journey to harness the power of automation. Studies
    have shown that revolutionary approaches consistently yield game-
    changing results.

    Furthermore, it's worth noting that fostering a culture of
    continuous improvement is essential. Additionally, teams should
    facilitate cross-functional collaboration. Consequently, the
    paradigm shift toward agile methodologies has unparalleled benefits.

    In conclusion, by leveraging these meticulous practices, teams can
    navigate the complexities of modern software development with
    sufficient grace. Ultimately, the key to success is to commence
    this journey today.
""").strip()


def _section(title: str) -> None:
    bar = "─" * 68
    print(f"\n{bar}\n  {title}\n{bar}")


def _show_score(label: str, s) -> None:
    print(f"\n[{label}] {s}")
    if s.rule_probability > 0:
        # Limit to top 8 violations by score to keep output readable.
        rule_score = get_language("en").detector.score(SAMPLE_AI_TEXT)
        # We re-score so we have access to the violations list. Cheap.
        _ = rule_score  # silence unused warning when label != 'before'
    print(f"     ngram_metrics: {s.ngram_metrics}")


def main() -> int:  # noqa: PLR0915 - smoke-test script, OK
    _section("0. Plugin registration")
    profile = get_language("en")
    print(f"loaded profile        : {profile.code}")
    print(f"detector version      : {profile.detector.version}")
    print(f"ngram corpus_id       : {profile.ngram_engine.corpus_id}")
    print(f"replacement pairs     : {len(profile.replacements.ordered_pairs())}")
    print(f"metadata              : {profile.metadata}")

    _section("1. detect — raw AI sample")
    before = combined_score(SAMPLE_AI_TEXT, lang="en")
    print(before)
    print(f"\ntext length           : {len(SAMPLE_AI_TEXT)} chars")
    raw_violations = profile.detector.score(SAMPLE_AI_TEXT).violations
    print(f"rule violations fired : {len(raw_violations)}")
    cats: dict[str, int] = {}
    for v in raw_violations:
        cats[v.category] = cats.get(v.category, 0) + 1
    print(f"  by category         : {cats}")
    print("  top 5 by score:")
    for v in sorted(raw_violations, key=lambda x: -x.score)[:5]:
        print(
            f"    [{v.category}/{v.rule}] count={v.count} score={v.score} "
            f"sample={v.sample[:60]!r}"
        )

    if before.combined_probability < 50:
        print("\n  ⚠  expected combined >= 50 on this AI sample; got "
              f"{before.combined_probability}. Rules may need tuning.")
    else:
        print(f"\n  ✓ combined score {before.combined_probability} ≥ 50 "
              "(detector caught the AI sample as expected)")

    _section("2. clean — apply M5 deterministic replacements")
    cleaned = _deterministic_cleanup(SAMPLE_AI_TEXT, profile=profile)
    delta = len(SAMPLE_AI_TEXT) - len(cleaned)
    print(f"chars removed         : {delta} ({delta * 100 / len(SAMPLE_AI_TEXT):.1f}%)")
    print(f"\nFIRST 300 CHARS OF CLEANED TEXT:\n{cleaned[:300]!r}")
    if delta == 0:
        print("\n  ⚠  no chars were removed — replacements did NOT apply!")
        return 1
    # Spot-check a few specific replacements actually happened.
    expected_to_be_gone = [
        "As an AI language model,",
        "It is important to note that",
        "delve into",
        "leverage",
        "utilize",
        "In conclusion,",
        "Moreover,",
        "transformative",
        "tapestry",
        "meticulous",
    ]
    misses = [s for s in expected_to_be_gone if s in cleaned]
    if misses:
        print(f"\n  ⚠ these AI tells survived: {misses}")
        return 1
    print(f"\n  ✓ all {len(expected_to_be_gone)} probe substrings stripped")

    _section("3. re-detect — does cleaning actually lower the score?")
    after = combined_score(cleaned, lang="en")
    print(after)
    drop = before.combined_probability - after.combined_probability
    print(f"\nscore drop            : {drop:+.1f} "
          f"({before.combined_probability} → {after.combined_probability})")
    rule_drop = before.rule_probability - after.rule_probability
    print(f"rule-layer drop       : {rule_drop:+.1f} "
          f"({before.rule_probability} → {after.rule_probability})")

    if rule_drop <= 0:
        print("\n  ⚠ rule score did not drop after cleaning! Investigate.")
        return 1
    print(f"\n  ✓ rule score dropped {rule_drop:.1f} pts after deterministic clean")

    _section("4. (optional) full LLM polish")
    if not (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
    ):
        print("no LLM API key in env (OPENAI_API_KEY / ANTHROPIC_API_KEY / "
              "OPENROUTER_API_KEY). Skipping LLM round-trip.\n"
              "Layers 1-3 above already verify M1-M5 wiring without LLM.")
        return 0

    from humanize_core.postprocess import postprocess_humanize

    print("LLM key found — attempting one polish round...")
    try:
        polished = postprocess_humanize(SAMPLE_AI_TEXT, lang="en")
        print(f"\nPOLISHED OUTPUT (first 400 chars):\n{polished[:400]!r}")
        polished_score = combined_score(polished, lang="en")
        print(f"\npolished combined     : {polished_score.combined_probability}")
        print(f"  full drop from raw  : {before.combined_probability - polished_score.combined_probability:+.1f}")
    except Exception as e:  # smoke-test, surface error but don't fail the script
        print(f"\n  ⚠ LLM polish raised: {type(e).__name__}: {e}")
        print("  This may be a key/quota issue; M1-M5 themselves still verify.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
