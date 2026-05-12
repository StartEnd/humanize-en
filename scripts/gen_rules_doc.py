#!/usr/bin/env python3
"""scripts/gen_rules_doc.py — render ``docs/rules.md`` from ``rules.json``.

plan-M9 deliverable. The detector's rule table is the source of
truth; every rule has a ``_desc`` field, weight, and threshold
ladder defined inline. Reading the JSON to learn what each rule
does is awkward, so this script flattens the table into a
Markdown reference document.

Design choices:

* **Idempotent.** Running the script twice produces byte-identical
  output (the only mutable input is ``rules.json``). Tested in
  ``tests/test_rules_doc_gen.py``.
* **No external deps.** Stdlib only — runs cleanly in CI before
  ``humanize_core`` even imports.
* **Single output file.** Writes ``docs/rules.md`` relative to the
  repo root. Override with ``--out`` for testing.

Usage::

    uv run python scripts/gen_rules_doc.py
    uv run python scripts/gen_rules_doc.py --rules path/to/rules.json --out /tmp/rules.md
    uv run python scripts/gen_rules_doc.py --check    # exit 1 if out of sync

The ``--check`` mode is intended for CI: it regenerates the doc
in memory and exits non-zero if the on-disk copy disagrees, so a
PR that changes ``rules.json`` without refreshing the doc fails
loudly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES = REPO_ROOT / "humanize_en" / "_lang" / "en" / "data" / "rules.json"
DEFAULT_OUT = REPO_ROOT / "docs" / "rules.md"

# Category render order. Mirrors detector.py ``score`` evaluation
# order so readers can predict scoring precedence.
CATEGORY_ORDER = (
    "blacklist_words",
    "blacklist_phrases",
    "structural_rules",
    "rhythm_rules",
    "fake_human",
    "soul_signals",
)

CATEGORY_TITLES = {
    "blacklist_words": "Lexical AI tells (`blacklist_words`)",
    "blacklist_phrases": "Multi-word AI tells (`blacklist_phrases`)",
    "structural_rules": "Document structure (`structural_rules`)",
    "rhythm_rules": "Sentence / paragraph rhythm (`rhythm_rules`)",
    "fake_human": "Manufactured anecdotes (`fake_human`)",
    "soul_signals": "Negative — argument-quality signals (`soul_signals`)",
}


def _is_meta_key(key: str) -> bool:
    """Skip ``_meta`` / ``_desc`` / future ``_*`` housekeeping keys."""
    return key.startswith("_")


def _render_pattern_sample(patterns: list[str], *, n: int = 6) -> str:
    """Render the first ``n`` patterns as inline code, comma-separated.

    Patterns that look like full regex (contain ``\\`` or ``(?``) are
    left raw; literal patterns are shown in code spans. Trailing
    ellipsis when the list is truncated.
    """
    if not patterns:
        return "_(none)_"
    head = patterns[:n]
    rendered = ", ".join(f"`{p}`" for p in head)
    if len(patterns) > n:
        rendered += f", … (**{len(patterns) - n} more**)"
    return rendered


def _render_meta_block(meta: dict[str, Any]) -> list[str]:
    """Top-of-doc YAML-ish block summarising the rule set version."""
    lines = []
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| `version` | `{meta.get('version', '?')}` |")
    if "milestone" in meta:
        lines.append(f"| `milestone` | `{meta['milestone']}` |")
    if "description" in meta:
        lines.append(f"| `description` | {meta['description']} |")
    if sources := meta.get("sources"):
        sources_str = "<br>".join(f"- {s}" for s in sources)
        lines.append(f"| `sources` | {sources_str} |")
    if scoring := meta.get("scoring"):
        for k, v in scoring.items():
            lines.append(f"| `scoring.{k}` | {v} |")
    return lines


def _render_word_or_phrase_rule(rule: str, conf: dict[str, Any]) -> list[str]:
    """Render a ``blacklist_words`` / ``blacklist_phrases`` rule.

    Both categories share the same shape:
    ``{_desc, weight, soft_threshold, hard_threshold, patterns}``.
    """
    lines = []
    lines.append(f"#### `{rule}`")
    lines.append("")
    lines.append(conf.get("_desc", "_(no description)_"))
    lines.append("")
    lines.append(
        f"- **Weight**: `{conf['weight']}`  "
        f"  **Soft threshold**: `{conf.get('soft_threshold', 0)}`  "
        f"  **Hard threshold**: `{conf.get('hard_threshold', 1)}`"
    )
    lines.append(
        f"- **Patterns** ({len(conf['patterns'])}): "
        + _render_pattern_sample(conf["patterns"])
    )
    lines.append("")
    return lines


def _render_structural_rule(rule: str, conf: dict[str, Any]) -> list[str]:
    """Render a structural rule (yes/no gate on document metric)."""
    lines = []
    lines.append(f"#### `{rule}`")
    lines.append("")
    lines.append(conf.get("_desc", "_(no description)_"))
    lines.append("")
    bullets = [f"**Weight**: `{conf['weight']}`"]
    for k in (
        "min_text_length",
        "threshold_per_1000_chars",
        "threshold_ratio",
        "ai_threshold",
    ):
        if k in conf:
            bullets.append(f"**{k}**: `{conf[k]}`")
    lines.append("- " + "  ".join(bullets))
    lines.append("")
    return lines


def _render_rhythm_rule(rule: str, conf: dict[str, Any]) -> list[str]:
    """Render a rhythm rule (numeric gate on sentence/paragraph metric)."""
    lines = []
    lines.append(f"#### `{rule}`")
    lines.append("")
    lines.append(conf.get("_desc", "_(no description)_"))
    lines.append("")
    bullets = [f"**Weight**: `{conf['weight']}`"]
    for k in (
        "min_sentences",
        "min_text_length",
        "ai_threshold",
        "min_threshold",
    ):
        if k in conf:
            bullets.append(f"**{k}**: `{conf[k]}`")
    lines.append("- " + "  ".join(bullets))
    lines.append("")
    return lines


def _render_fake_or_soul_rule(rule: str, conf: dict[str, Any]) -> list[str]:
    """Render a fake_human / soul_signals rule (regex or pattern list).

    ``fake_human`` uses ``hard_threshold`` (fires when count > hard).
    ``soul_signals`` uses ``min_threshold`` (fires when count < min,
    contributing ``(min - count) * weight`` to the score — negative
    signal that *should* be present in human writing).
    """
    lines = []
    lines.append(f"#### `{rule}`")
    lines.append("")
    lines.append(conf.get("_desc", "_(no description)_"))
    lines.append("")
    bullets = [f"**Weight**: `{conf['weight']}`"]
    for k in (
        "hard_threshold",
        "min_threshold",
        "min_text_length",
        "regex",
        "case_insensitive",
    ):
        if k in conf:
            bullets.append(f"**{k}**: `{conf[k]}`")
    lines.append("- " + "  ".join(bullets))

    if patterns := conf.get("patterns"):
        lines.append(
            f"- **Patterns** ({len(patterns)}): "
            + _render_pattern_sample(patterns)
        )
    elif pattern := conf.get("pattern"):
        lines.append(f"- **Pattern**: `{pattern[:120]}`")
    lines.append("")
    return lines


def _render_category(name: str, content: dict[str, Any]) -> list[str]:
    """Render a single rule category section."""
    lines = []
    lines.append(f"## {CATEGORY_TITLES.get(name, name)}")
    lines.append("")
    if desc := content.get("_desc"):
        lines.append(desc)
        lines.append("")

    real_rules = {k: v for k, v in content.items() if not _is_meta_key(k)}
    lines.append(f"_{len(real_rules)} rule(s)._")
    lines.append("")

    renderer = {
        "blacklist_words": _render_word_or_phrase_rule,
        "blacklist_phrases": _render_word_or_phrase_rule,
        "structural_rules": _render_structural_rule,
        "rhythm_rules": _render_rhythm_rule,
        "fake_human": _render_fake_or_soul_rule,
        "soul_signals": _render_fake_or_soul_rule,
    }[name]

    for rule, conf in real_rules.items():
        lines.extend(renderer(rule, conf))

    return lines


def render_rules_doc(rules: dict[str, Any]) -> str:
    """Render the full ``docs/rules.md`` document.

    Pure function — given the parsed ``rules.json`` it returns the
    Markdown string. Useful for in-memory testing without touching
    the filesystem.
    """
    meta = rules.get("_meta", {})
    out: list[str] = []
    out.append("# humanize-en detector rules")
    out.append("")
    out.append(
        "> Auto-generated from "
        "`humanize_en/_lang/en/data/rules.json` by "
        "`scripts/gen_rules_doc.py`. Do **not** edit by hand — your changes "
        "will be overwritten on the next regeneration. Edit the JSON instead."
    )
    out.append("")
    out.append("## Rule-set metadata")
    out.append("")
    out.extend(_render_meta_block(meta))
    out.append("")

    total = sum(
        len({k for k in rules.get(cat, {}) if not _is_meta_key(k)})
        for cat in CATEGORY_ORDER
    )
    out.append(f"Total rules: **{total}** across {len(CATEGORY_ORDER)} categories.")
    out.append("")

    for cat in CATEGORY_ORDER:
        if cat not in rules:
            continue
        out.extend(_render_category(cat, rules[cat]))

    out.append("---")
    out.append("")
    out.append(
        "Regenerate this file with `make rules-doc` or "
        "`uv run python scripts/gen_rules_doc.py`."
    )
    out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--rules", type=Path, default=DEFAULT_RULES,
        help=f"path to rules.json (default: {DEFAULT_RULES})",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"output Markdown path (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="exit non-zero if the on-disk doc is out of sync (CI mode)",
    )
    args = parser.parse_args()

    rules = json.loads(args.rules.read_text(encoding="utf-8"))
    rendered = render_rules_doc(rules)

    if args.check:
        existing = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if existing != rendered:
            print(
                f"error: {args.out} is out of sync with {args.rules}.",
                file=sys.stderr,
            )
            print(
                "  run `make rules-doc` (or "
                "`uv run python scripts/gen_rules_doc.py`) and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"ok: {args.out} is up to date")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.out} ({len(rendered):,} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
