"""humanize_en._lang.en.detector — English rule-based AI-style detector.

**M3 status**: lexical + phrase rules live (~16 rules, ~150 patterns).
M4 will add structural / rhythm / fake_human / soul_signals checks
on top of the same scoring pipeline.

The rule data lives in ``humanize_en/_lang/en/data/rules.json`` and
is loaded once per process. See that file's ``_meta`` block for the
sources behind each rule and the scoring scheme.

Scoring bands (calibration source: HC3-en human + ChatGPT, validated
against held-out RAID samples in P1.12; bands are the canonical
0-100 cutoffs used across all humanize-* plugins):

- 0–24   LOW        looks human-written
- 25–49  MEDIUM     some AI traces
- 50–74  HIGH       likely AI-generated
- 75–100 VERY_HIGH  almost certainly AI

Algorithm (per call to :func:`score`):

1. Strip fenced + inline code blocks (code keywords shouldn't count).
2. For each ``blacklist_words`` rule, sum hits across patterns
   (literal, case-insensitive). Apply the threshold ladder: half
   weight under ``soft_threshold``, full weight in the soft-hard
   band, and an extra ``(count - hard) * weight`` overshoot penalty.
3. Same for ``blacklist_phrases`` — patterns are matched as
   word-boundary-anchored substrings (no regex compilation needed
   in the hot path).
4. Length-normalise: ``total = min(100, raw / max(1, len/3000))``
   so a 12k-word essay isn't auto-flagged just for being long.

Public surface (preserved across M3-M4):

    from humanize_en._lang.en.detector import score, Score, Violation, en_detector
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ._labels import en_level_label as level_label

# Path to the rule data file. The Detector adapter reads the
# ``_meta.version`` from here at construction so the runtime version
# tracks the data file (not the package version) — important when
# operators ship a hot-patched rules.json without bumping the wheel.
RULES_PATH = Path(__file__).parent / "data" / "rules.json"


@dataclass
class Violation:
    """One triggered rule. Same shape as humanize_zh's Violation so the
    Web UI can render EN and ZH violations with identical code paths.
    """

    category: str
    """Rule bucket: ``blacklist_words`` / ``blacklist_phrases`` /
    ``structural_rules`` / ``rhythm_rules`` / ``fake_human`` /
    ``soul_signals``."""

    rule: str
    """Rule key inside its bucket, e.g. ``"delve_class"``."""

    weight: int
    count: int
    sample: str
    """One literal matched snippet (~30 chars) for human review."""

    threshold: int | None = None
    score: float = 0.0
    """Contribution this violation makes to the total score."""

    def __str__(self) -> str:  # pragma: no cover — pretty-print only
        thr = f" (threshold {self.threshold})" if self.threshold is not None else ""
        return (
            f"  [{self.score:+5.1f}] {self.category}.{self.rule}: "
            f"hit {self.count} times{thr} | sample: \"{self.sample[:30]}\""
        )


@dataclass
class Score:
    """Aggregate rule-detector verdict. Mirrors humanize_zh.detect.Score."""

    total: float
    level: str
    violations: list[Violation] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    text_length: int = 0

    def __str__(self) -> str:  # pragma: no cover — pretty-print only
        lines = [
            f"AI-score: {self.total:.1f}/100  ({self.level})",
            f"Text length: {self.text_length} chars",
            "",
            "Triggered rules:",
        ]
        if not self.violations:
            lines.append("  (none)")
        else:
            for v in sorted(self.violations, key=lambda v: -v.score):
                lines.append(str(v))
        if self.stats:
            lines += ["", "Stats:"]
            for k, v in self.stats.items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)


@lru_cache(maxsize=1)
def _load_rules() -> dict:
    """Load and cache the rule data file.

    ``lru_cache(maxsize=1)`` means we read the JSON once per process.
    Tests that need to swap rules at runtime should call
    ``_load_rules.cache_clear()`` then mutate ``RULES_PATH``.

    Returns the parsed dict verbatim — callers iterate over the
    ``blacklist_words`` and ``blacklist_phrases`` sub-dicts.
    """
    try:
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        # Fail open: empty rule set. The Detector's ``version`` will
        # advertise ``0.0.0-unloadable`` so callers can detect the
        # degradation in their telemetry.
        return {
            "_meta": {"version": "0.0.0-unloadable", "error": str(e)},
            "blacklist_words": {},
            "blacklist_phrases": {},
        }


# Code-block stripper — code samples contain `utilize`, `factors`, etc.
# legitimately, so we excise them before rule matching.
_CODE_FENCED_RE = re.compile(r"```.*?```", re.DOTALL)
_CODE_INLINE_RE = re.compile(r"`[^`\n]+`")


def _strip_codeblocks(text: str) -> str:
    """Remove fenced (```...```) and inline (`...`) code blocks.

    Mirrors humanize_zh._lang.zh.detector._strip_codeblocks. Without
    this step a Python tutorial discussing ``utilize()`` would trip
    the ``corporate_filler`` rule on every code example.
    """
    text = _CODE_FENCED_RE.sub("", text)
    text = _CODE_INLINE_RE.sub("", text)
    return text


def _apply_threshold_ladder(
    count: int, weight: int, soft: int | None, hard: int | None
) -> float:
    """Translate a hit count into a rule score using the (soft, hard)
    threshold ladder.

    The ladder design (shared with humanize-zh):

    - ``count <= soft_threshold``  → ``count * weight * 0.5`` (soft penalty)
    - ``soft < count <= hard``     → ``count * weight``        (full penalty)
    - ``count > hard``             → ``(count - hard) * weight`` plus the full
                                     band penalty up to ``hard``.

    A ``None`` threshold disables that band — most rules set one
    or both. ``soft_threshold=0`` means "any hit counts at full
    weight" (no soft band), which is what the AI-safety-disclaimer
    rule uses.
    """
    if hard is not None and count > hard:
        # Once hard exceeded: full-weight for hits up to hard, plus
        # extra-weight (count - hard) for the overshoot. This keeps
        # the scoring monotonic — more hits never decreases the score.
        return hard * weight + (count - hard) * weight
    if soft is not None and count <= soft:
        return count * weight * 0.5
    return count * weight


def _build_word_regex(patterns: list[str]) -> re.Pattern[str]:
    """Compile a single regex that matches any of ``patterns`` as a
    case-insensitive word-bounded literal.

    Sorted longest-first so e.g. ``utilization`` matches before
    ``utilize`` (re.IGNORECASE alternation is left-to-right greedy).
    Apostrophes are kept literal because ``body's`` must match as a
    word — our tokenisation already treats apostrophe-bound
    contractions as single tokens.
    """
    if not patterns:
        return re.compile(r"(?!)")  # match-nothing sentinel
    escaped = sorted((re.escape(p) for p in patterns), key=len, reverse=True)
    # `\b` doesn't fire on the right of an apostrophe — switch to a
    # negative-lookahead/lookbehind that excludes word chars + apostrophe.
    # Otherwise `body's` would match inside `body'so` (unlikely but possible).
    body = "|".join(escaped)
    return re.compile(rf"(?<![\w']){body}(?![\w'])", re.IGNORECASE)


def _build_phrase_regex(patterns: list[str]) -> re.Pattern[str]:
    """Same shape as :func:`_build_word_regex` but for multi-word
    phrases. Internal whitespace in a pattern is treated as flexible
    (``\\s+``) so trailing newlines / double spaces don't suppress
    a match.
    """
    if not patterns:
        return re.compile(r"(?!)")
    bits: list[str] = []
    for p in sorted(patterns, key=len, reverse=True):
        # Escape, then relax inner whitespace.
        parts = [re.escape(w) for w in p.split()]
        bits.append(r"\s+".join(parts))
    return re.compile(rf"(?<![\w']){'|'.join(bits)}(?![\w'])", re.IGNORECASE)


def _check_word_rule(text: str, rule: str, conf: dict) -> Violation | None:
    """Run one ``blacklist_words`` rule and return a Violation if it
    fires (or ``None`` for no hits).
    """
    patterns = conf.get("patterns", [])
    weight = int(conf.get("weight", 1))
    regex = _build_word_regex(patterns)
    matches = list(regex.finditer(text))
    if not matches:
        return None
    count = len(matches)
    sample = matches[0].group(0)
    soft = conf.get("soft_threshold")
    hard = conf.get("hard_threshold")
    s = _apply_threshold_ladder(count, weight, soft, hard)
    return Violation(
        category="blacklist_words",
        rule=rule,
        weight=weight,
        count=count,
        sample=sample,
        threshold=hard if hard is not None else soft,
        score=s,
    )


def _check_phrase_rule(text: str, rule: str, conf: dict) -> Violation | None:
    """Same as :func:`_check_word_rule` but for ``blacklist_phrases``."""
    patterns = conf.get("patterns", [])
    weight = int(conf.get("weight", 1))
    regex = _build_phrase_regex(patterns)
    matches = list(regex.finditer(text))
    if not matches:
        return None
    count = len(matches)
    sample = matches[0].group(0)
    soft = conf.get("soft_threshold")
    hard = conf.get("hard_threshold")
    s = _apply_threshold_ladder(count, weight, soft, hard)
    return Violation(
        category="blacklist_phrases",
        rule=rule,
        weight=weight,
        count=count,
        sample=sample,
        threshold=hard if hard is not None else soft,
        score=s,
    )


def score(
    text: str, *, has_notes: bool = False, skip_codeblocks: bool = True
) -> Score:
    """Score ``text`` against the English rule library.

    Args:
        text: The text to score.
        has_notes: Reserved for M4's ``fake_human`` rules — when the
            author has a real ``notes.md`` they're allowed to use
            first-person experience phrasing the rule would otherwise
            penalise. M3 doesn't enforce ``fake_human`` so the flag
            currently affects nothing.
        skip_codeblocks: Strip fenced + inline code before matching.
            ON by default so a tutorial that legitimately discusses
            ``utilize()`` doesn't get penalised.
    """
    if not text or not text.strip():
        return Score(total=0.0, level=level_label(0.0), text_length=0)
    body = _strip_codeblocks(text) if skip_codeblocks else text
    rules = _load_rules()

    violations: list[Violation] = []

    for rule_name, conf in rules.get("blacklist_words", {}).items():
        if rule_name.startswith("_") or not isinstance(conf, dict):
            continue
        v = _check_word_rule(body, rule_name, conf)
        if v is not None:
            violations.append(v)

    for rule_name, conf in rules.get("blacklist_phrases", {}).items():
        if rule_name.startswith("_") or not isinstance(conf, dict):
            continue
        v = _check_phrase_rule(body, rule_name, conf)
        if v is not None:
            violations.append(v)

    raw = sum(v.score for v in violations)
    # Length-normalise: every 3 000 characters is one "unit" of text.
    # Without this a 12 000-char essay would be ~4x as likely to trip
    # the score for the same per-unit AI density as a 3 000-char post.
    norm_factor = max(1.0, len(body) / 3000)
    total = min(100.0, raw / norm_factor)

    stats = {
        "rule_set_version": str(rules.get("_meta", {}).get("version", "unknown")),
        "rule_count_evaluated": len(violations),
    }
    if has_notes:
        # M4 will use this to relax fake_human checks; meanwhile we
        # surface the flag so debugging output is self-documenting.
        stats["has_notes"] = True

    return Score(
        total=round(total, 1),
        level=level_label(total),
        violations=violations,
        stats=stats,
        text_length=len(body),
    )


# ─── Protocol adapter ─────────────────────────────────────────────────────


class EnDetector:
    """Thin :class:`~humanize_core.protocols.Detector` adapter around
    :func:`score`.

    Stateless apart from the LRU-cached rule data. Thread-safe.
    The ``version`` attribute is sourced from ``rules.json::_meta.version``
    at construction so swapping rule files is a one-restart change.
    """

    code: str = "en"

    def __init__(self) -> None:
        self.version: str = str(
            _load_rules().get("_meta", {}).get("version", "0.0.0")
        )

    def score(self, text: str, *, has_notes: bool = False) -> Score:
        return score(text, has_notes=has_notes)


# Singleton consumed by ``humanize_en._lang.en.profile``.
en_detector: EnDetector = EnDetector()


__all__ = [
    "EnDetector",
    "Score",
    "Violation",
    "en_detector",
    "score",
]
