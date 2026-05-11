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
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from statistics import mean, pstdev

from ._labels import en_level_label as level_label

# Reuse the ngram engine's tokeniser + sentence/paragraph splitters so
# rhythm rules see exactly the same structure the ngram engine sees.
# Keeps rhythm + ngram in lock-step and avoids a parallel splitter that
# might drift at the next tokenisation tweak (see M3 "\\n" bug fix).
from .data._ngram_engine import _paragraphs, _sentences, _tokens

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


# ─── M4: structural / rhythm / fake_human / soul_signals ─────────────────


_MD_HEADING_RE = re.compile(r"(?:^|\n)#{1,6}\s+\S", re.MULTILINE)
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*\u2022]\s+|\d+[\.\)]\s+)", re.MULTILINE)


def _check_structural(text: str, rules: dict) -> list[Violation]:
    """Run the ``structural_rules`` block.

    Two rules at M4 — ``heading_density`` and ``list_density``. Each
    fires at most once per text (pass/fail gate, no count-based
    escalation). Both skip if the text is below ``min_text_length``
    so short answers aren't penalised for being answer-shaped.
    """
    out: list[Violation] = []
    n_chars = len(text)

    hd = rules.get("heading_density")
    if isinstance(hd, dict):
        min_len = int(hd.get("min_text_length", 500))
        if n_chars >= min_len:
            headings = len(_MD_HEADING_RE.findall(text))
            per_1k = headings * 1000 / max(n_chars, 1)
            threshold = float(hd.get("threshold_per_1000_chars", 3))
            if per_1k > threshold:
                weight = int(hd.get("weight", 5))
                out.append(Violation(
                    category="structural_rules", rule="heading_density",
                    weight=weight, count=headings,
                    sample=f"{headings} markdown headings ({per_1k:.1f}/1k chars > {threshold})",
                    threshold=int(threshold), score=weight,
                ))

    ld = rules.get("list_density")
    if isinstance(ld, dict):
        min_len = int(ld.get("min_text_length", 500))
        if n_chars >= min_len:
            lines = [ln for ln in text.split("\n") if ln.strip()]
            if lines:
                list_lines = sum(
                    1 for ln in lines if _LIST_ITEM_RE.match(ln)
                )
                ratio = list_lines / len(lines)
                threshold = float(ld.get("threshold_ratio", 0.5))
                if ratio > threshold:
                    weight = int(ld.get("weight", 5))
                    out.append(Violation(
                        category="structural_rules", rule="list_density",
                        weight=weight, count=list_lines,
                        sample=f"{list_lines}/{len(lines)} lines are list items ({ratio:.0%} > {threshold:.0%})",
                        threshold=int(threshold * 100), score=weight,
                    ))
    return out


def _coef_of_variation(values: Sequence[float]) -> float:
    """Population CV, with a zero-mean guard that returns 0.0 so the
    caller's threshold comparison never divides by zero.
    """
    if len(values) < 2:
        return 0.0
    m = mean(values)
    if m == 0:
        return 0.0
    return pstdev(values) / m


def _check_rhythm(text: str, rules: dict) -> tuple[list[Violation], dict]:
    """Run the four ``rhythm_rules`` metrics.

    Returns ``(violations, stats)`` — stats always populated (sent_cv,
    short_ratio, para_cv, opener_ratio) regardless of whether the
    metric crossed a threshold, so callers can show the numbers even
    when no rule fired.
    """
    out: list[Violation] = []
    stats: dict = {}

    sents = _sentences(text)
    sent_wc = [len(_tokens(s)) for s in sents]
    sent_wc = [w for w in sent_wc if w > 0]

    # sentence_length_cv + short_sentence_ratio share the sentence list.
    if len(sent_wc) >= 5:
        s_cv = _coef_of_variation(sent_wc)
        stats["sentence_cv"] = round(s_cv, 3)
        cv_conf = rules.get("sentence_length_cv")
        if isinstance(cv_conf, dict):
            ai_thr = float(cv_conf.get("ai_threshold", 0.35))
            min_sents = int(cv_conf.get("min_sentences", 5))
            if len(sent_wc) >= min_sents and s_cv < ai_thr:
                weight = int(cv_conf.get("weight", 10))
                out.append(Violation(
                    category="rhythm_rules", rule="sentence_length_cv",
                    weight=weight, count=1,
                    sample=f"sentence CV={s_cv:.2f} < {ai_thr} (uniform sentence lengths)",
                    threshold=int(ai_thr * 100), score=weight,
                ))

        sr_conf = rules.get("short_sentence_ratio")
        if isinstance(sr_conf, dict) and len(text) >= int(
            sr_conf.get("min_text_length", 300)
        ):
            short_ratio = sum(1 for w in sent_wc if w < 6) / len(sent_wc)
            stats["short_sentence_ratio"] = round(short_ratio, 3)
            ai_thr = float(sr_conf.get("ai_threshold", 0.02))
            if short_ratio < ai_thr:
                weight = int(sr_conf.get("weight", 4))
                out.append(Violation(
                    category="rhythm_rules", rule="short_sentence_ratio",
                    weight=weight, count=1,
                    sample=f"short-sentence ratio={short_ratio:.1%} < {ai_thr:.1%}",
                    threshold=int(ai_thr * 100), score=weight,
                ))

    paras = _paragraphs(text)
    # paragraph_uniformity + para_opening_enumeration share the paragraph list.
    pu_conf = rules.get("paragraph_uniformity")
    if (
        isinstance(pu_conf, dict)
        and len(paras) >= int(pu_conf.get("min_paragraphs", 3))
    ):
        plens = [len(p) for p in paras]
        p_cv = _coef_of_variation(plens)
        stats["paragraph_cv"] = round(p_cv, 3)
        ai_thr = float(pu_conf.get("ai_threshold", 0.3))
        if p_cv < ai_thr:
            weight = int(pu_conf.get("weight", 6))
            out.append(Violation(
                category="rhythm_rules", rule="paragraph_uniformity",
                weight=weight, count=1,
                sample=f"paragraph-length CV={p_cv:.2f} < {ai_thr} (uniform paragraphs)",
                threshold=int(ai_thr * 100), score=weight,
            ))

    po_conf = rules.get("para_opening_enumeration")
    if isinstance(po_conf, dict) and paras:
        try:
            pat = re.compile(po_conf.get("pattern", r"(?!)"), re.IGNORECASE)
        except re.error:
            pat = re.compile(r"(?!)")
        opener_hits = sum(1 for p in paras if pat.match(p))
        stats["para_opener_count"] = opener_hits
        hard = int(po_conf.get("hard_threshold", 2))
        if opener_hits > hard:
            weight = int(po_conf.get("weight", 5))
            overshoot = opener_hits - hard
            out.append(Violation(
                category="rhythm_rules", rule="para_opening_enumeration",
                weight=weight, count=opener_hits,
                sample=f"{opener_hits} paragraphs open with enumeration/transition markers (>{hard})",
                threshold=hard, score=overshoot * weight,
            ))

    return out, stats


def _check_fake_human(text: str, rules: dict) -> list[Violation]:
    """Run ``fake_human`` regex rules. Each rule is independent; each
    hit adds ``weight`` to the score up to the ``hard_threshold``,
    then ``(count - hard) * weight`` for overshoot.
    """
    out: list[Violation] = []
    for rule_name, conf in rules.items():
        if rule_name.startswith("_") or not isinstance(conf, dict):
            continue
        patterns = conf.get("patterns", [])
        if not patterns:
            continue
        weight = int(conf.get("weight", 1))
        total_count = 0
        sample = ""
        for pat in patterns:
            try:
                matches = list(re.finditer(pat, text, re.IGNORECASE))
            except re.error:
                continue
            if matches and not sample:
                sample = matches[0].group(0)
            total_count += len(matches)
        if total_count == 0:
            continue
        hard = conf.get("hard_threshold")
        soft = conf.get("soft_threshold")
        s = _apply_threshold_ladder(total_count, weight, soft, hard)
        out.append(Violation(
            category="fake_human", rule=rule_name, weight=weight,
            count=total_count, sample=sample,
            threshold=hard if hard is not None else soft, score=s,
        ))
    return out


def _check_soul_signals(text: str, rules: dict) -> list[Violation]:
    """Penalty for *missing* human fingerprints.

    Unlike every other rule category, soul_signals fires when the
    matched count is BELOW ``min_threshold``. The penalty is
    ``(min_threshold - count) * weight`` — so fully-absent signals
    score proportionally higher than just-under-threshold ones.

    Case-sensitivity is per-rule via the ``case_insensitive`` conf
    flag (default ``True``). ``concrete_specifics`` keeps it ``False``
    because its regex genuinely relies on Title-Case matching to find
    proper nouns — with IGNORECASE it would match every lowercase
    word pair and never fire.
    """
    out: list[Violation] = []
    n_chars = len(text)
    for rule_name, conf in rules.items():
        if rule_name.startswith("_") or not isinstance(conf, dict):
            continue
        min_len = int(conf.get("min_text_length", 0))
        if n_chars < min_len:
            continue
        pattern = conf.get("pattern", "")
        if not pattern:
            continue
        flags = re.IGNORECASE if conf.get("case_insensitive", True) else 0
        try:
            hits = len(re.findall(pattern, text, flags))
        except re.error:
            continue
        min_thr = int(conf.get("min_threshold", 1))
        if hits >= min_thr:
            continue
        weight = int(conf.get("weight", 5))
        deficit = min_thr - hits
        out.append(Violation(
            category="soul_signals", rule=rule_name, weight=weight,
            count=hits, sample=f"found {hits} signal(s), need >= {min_thr}",
            threshold=min_thr, score=deficit * weight,
        ))
    return out


def score(
    text: str, *, has_notes: bool = False, skip_codeblocks: bool = True
) -> Score:
    """Score ``text`` against the English rule library.

    Runs in six passes (M3 + M4):

    1. ``blacklist_words``      — lexical tells (M3)
    2. ``blacklist_phrases``    — multi-word tells (M3)
    3. ``structural_rules``     — heading + list density (M4)
    4. ``rhythm_rules``         — sentence/paragraph CV + opener enumeration (M4)
    5. ``fake_human``           — pseudo-personal-experience regexes (M4)
    6. ``soul_signals``         — penalty for MISSING human fingerprints (M4)

    Args:
        text: The text to score.
        has_notes: When ``True``, the ``fake_human`` pass is skipped
            (we trust that a writer with a real ``notes.md`` is
            reporting genuine first-person experience). The rhythm /
            structural / soul_signals passes still run.
        skip_codeblocks: Strip fenced + inline code before matching.
            ON by default so a tutorial that legitimately discusses
            ``utilize()`` doesn't get penalised.
    """
    if not text or not text.strip():
        return Score(total=0.0, level=level_label(0.0), text_length=0)
    body = _strip_codeblocks(text) if skip_codeblocks else text
    rules = _load_rules()

    violations: list[Violation] = []

    # 1. Lexical
    for rule_name, conf in rules.get("blacklist_words", {}).items():
        if rule_name.startswith("_") or not isinstance(conf, dict):
            continue
        v = _check_word_rule(body, rule_name, conf)
        if v is not None:
            violations.append(v)

    # 2. Phrases
    for rule_name, conf in rules.get("blacklist_phrases", {}).items():
        if rule_name.startswith("_") or not isinstance(conf, dict):
            continue
        v = _check_phrase_rule(body, rule_name, conf)
        if v is not None:
            violations.append(v)

    # 3. Structural (heading_density, list_density)
    violations.extend(_check_structural(body, rules.get("structural_rules", {})))

    # 4. Rhythm (sentence + paragraph CV, short-ratio, opener enumeration)
    rhythm_vios, rhythm_stats = _check_rhythm(body, rules.get("rhythm_rules", {}))
    violations.extend(rhythm_vios)

    # 5. Fake-human — skipped when has_notes=True (author's first-person
    #    claims are corroborated by their notes.md in that case).
    fake_skipped = False
    if not has_notes:
        violations.extend(_check_fake_human(body, rules.get("fake_human", {})))
    else:
        fake_skipped = True

    # 6. Soul signals — penalty for missing human fingerprints.
    violations.extend(_check_soul_signals(body, rules.get("soul_signals", {})))

    raw = sum(v.score for v in violations)
    # Length-normalise: every 3 000 characters is one "unit" of text.
    # Without this a 12 000-char essay would be ~4x as likely to trip
    # the score for the same per-unit AI density as a 3 000-char post.
    norm_factor = max(1.0, len(body) / 3000)
    total = min(100.0, raw / norm_factor)

    stats: dict = {
        "rule_set_version": str(rules.get("_meta", {}).get("version", "unknown")),
        "rule_count_evaluated": len(violations),
    }
    stats.update(rhythm_stats)
    if fake_skipped:
        stats["fake_human_check"] = "skipped (has_notes=True)"
    if has_notes:
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
