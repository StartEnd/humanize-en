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
from humanize_en import Strength
from humanize_en.prompt import build_humanize_postprocess_prompt

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

    _section("4. writer prompt assembly (M6) — no LLM call")
    builder = profile.prompt_pack.writer_prompt_builder
    if builder is None:
        print("  ⚠ profile.prompt_pack.writer_prompt_builder is None! "
              "M6 wiring missing.")
        return 1
    writer_prompt = builder(
        article=SAMPLE_AI_TEXT,
        violations=raw_violations,
        scene="analysis",
        aggressive=False,
    )
    print(f"writer prompt length  : {len(writer_prompt)} chars")
    has_article = SAMPLE_AI_TEXT[:60] in writer_prompt
    has_violations = "blacklist_words.liang_2024_lexical_tells" in writer_prompt
    has_rules = "Five core rules" in writer_prompt
    print(f"  contains ARTICLE    : {has_article}")
    print(f"  contains VIOLATIONS : {has_violations}")
    print(f"  contains RULES      : {has_rules}")
    if not (has_article and has_violations and has_rules):
        print("\n  ⚠ writer prompt missing one of the three injection points")
        return 1
    print("\n  ✓ writer prompt assembled with all 3 injections "
          "(article + violations + rules)")
    # Aggressive variant smoke test.
    aggr = builder(
        article=SAMPLE_AI_TEXT,
        violations=raw_violations,
        scene="analysis",
        aggressive=True,
    )
    if "AI text deep rewrite pass" not in aggr:
        print("  ⚠ aggressive=True did NOT pick the rewrite template")
        return 1
    print("  ✓ aggressive=True correctly routes to rewrite template")

    _section("5. strength knob (M7) — three-tier prompt rendering")
    lengths: dict[str, int] = {}
    for level in (Strength.LOW, Strength.MEDIUM, Strength.HIGH):
        rendered = build_humanize_postprocess_prompt(
            SAMPLE_AI_TEXT,
            raw_violations,
            scene="analysis",
            strength=level,
        )
        lengths[level.value] = len(rendered)
        print(f"  strength={level.value:6s} -> {len(rendered):>5} chars")

    if not (lengths["low"] < lengths["medium"]):
        print("  ⚠ LOW prompt is not shorter than MEDIUM!")
        return 1
    if "AI text deep rewrite pass" not in build_humanize_postprocess_prompt(
        SAMPLE_AI_TEXT, raw_violations, strength=Strength.HIGH
    ):
        print("  ⚠ HIGH did not pick the rewrite template")
        return 1
    print("\n  ✓ all three strengths produce distinct prompts "
          "(LOW < MEDIUM, HIGH = aggressive template)")

    _section("6. (optional) full LLM polish — three strengths")
    provider_id = None
    if os.getenv("DEEPSEEK_API_KEY"):
        provider_id = "deepseek"
    elif os.getenv("OPENAI_API_KEY"):
        provider_id = "openai"
    elif os.getenv("ANTHROPIC_API_KEY"):
        provider_id = "anthropic"

    if provider_id is None:
        print("no LLM API key in env (DEEPSEEK_API_KEY / OPENAI_API_KEY / "
              "ANTHROPIC_API_KEY). Skipping LLM round-trip.\n"
              "Layers 1-5 above already verify M1-M7 wiring without LLM.")
        return 0

    print(f"using provider: {provider_id}\n")

    from humanize_core.llm._resolve import resolve_provider
    from humanize_core.postprocess import postprocess_humanize

    # Resolve once so we can reuse the same provider instance across all
    # three strength calls (avoids repeated SDK client construction).
    try:
        provider = resolve_provider(provider_id)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ provider {provider_id!r} could not be resolved: {e}")
        return 1

    results: dict[str, dict] = {}

    # MEDIUM: default postprocess_humanize path (aggressive=False ->
    # back-compat mapping in the EN dispatcher picks Strength.MEDIUM).
    # The framework's "already publishable" short-circuit needs
    # rule_score >= 25 OR combined >= 30; our sample scores rule=100
    # so it always proceeds to the LLM call.
    # HIGH: same path with force_llm=True (-> aggressive=True -> HIGH).
    # LOW: direct dispatcher call (postprocess_humanize doesn't expose
    # strength= yet -- documented M7 limitation).

    def _polish_via_postprocess(force_llm: bool) -> tuple[str, float]:
        polished, score_after, _ = postprocess_humanize(
            SAMPLE_AI_TEXT, lang="en", provider=provider,
            violations=raw_violations, force_llm=force_llm,
        )
        rule_after = score_after.total if score_after is not None else 0.0
        return polished, rule_after

    def _polish_via_dispatcher(strength: Strength) -> tuple[str, float]:
        prompt_text = build_humanize_postprocess_prompt(
            SAMPLE_AI_TEXT, raw_violations, strength=strength,
        )
        response = provider.complete(prompt_text, max_tokens=4096, temperature=0.7)
        polished = response.text.strip()
        rule_after = profile.detector.score(polished).total
        return polished, rule_after

    def _report(level: str, polished: str, rule_after: float) -> None:
        combined_after = combined_score(polished, lang="en").combined_probability
        results[level] = {
            "text": polished,
            "rule_after": rule_after,
            "combined_after": combined_after,
        }
        print(f"polished length       : {len(polished)} chars "
              f"(was {len(SAMPLE_AI_TEXT)})")
        print(f"polished rule score   : {rule_after}/100")
        print(f"polished combined     : {combined_after}/100")
        print(f"first 200 chars       : {polished[:200]!r}\n")

    print("--- LOW (3-section trimmed rules) ---")
    polished_lo, rule_lo = _polish_via_dispatcher(Strength.LOW)
    _report("low", polished_lo, rule_lo)

    print("--- MEDIUM (full 8-section rules block) ---")
    polished_med, rule_med = _polish_via_postprocess(force_llm=False)
    _report("medium", polished_med, rule_med)

    print("--- HIGH (aggressive rewrite template) ---")
    polished_hi, rule_hi = _polish_via_postprocess(force_llm=True)
    _report("high", polished_hi, rule_hi)

    _section("7. summary — strength × score-drop matrix")
    print(f"{'':12s}  {'rule':>8s}  {'combined':>10s}  {'rule Δ':>10s}  "
          f"{'combined Δ':>12s}")
    print(f"{'baseline':12s}  {before.rule_probability:>8.1f}  "
          f"{before.combined_probability:>10.1f}  "
          f"{'-':>10s}  {'-':>12s}")
    for level in ("low", "medium", "high"):
        r = results[level]
        rule_delta = before.rule_probability - r["rule_after"]
        comb_delta = before.combined_probability - r["combined_after"]
        print(f"{level:12s}  {r['rule_after']:>8.1f}  "
              f"{r['combined_after']:>10.1f}  "
              f"{rule_delta:>+10.1f}  {comb_delta:>+12.1f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
