"""humanize_en._lang.en.detector — English rule-based AI-style detector.

**M1 status: stub.** This module satisfies the
:class:`~humanize_core.protocols.Detector` contract so the EN profile
can be assembled and registered, but :func:`score` always returns
``total=0.0`` and an empty violations list. M3 (lexical + phrase
rules) and M4 (structural + rhythm + fake-human + soul-signals)
replace this stub with the real implementation specified in
``docs/plan.md`` §3.

Scoring scheme (planned, calibrated against HC3-en in M2):

- 0–24   LOW        looks human-written
- 25–49  MEDIUM     some AI traces
- 50–74  HIGH       likely AI-generated
- 75–100 VERY_HIGH  almost certainly AI

The level labels live on :data:`humanize_en._lang.en.profile.EN_LEVEL_LABELS`
and are looked up via :func:`humanize_core._format.level_label`.

Public surface (will grow in M3+):

    from humanize_en._lang.en.detector import score, Score, Violation, en_detector
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ._labels import en_level_label as level_label

# Rule-set version of *the data file* (not the package). Bumped each
# time we ship a non-additive change to rules.json so calibration
# drift across versions is auditable. Stub data: 0.0.0-m1.
_RULESET_VERSION = "0.0.0-m1"


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


def score(text: str, *, has_notes: bool = False) -> Score:
    """Score ``text`` against the English rule library.

    **M1 stub** — always returns ``total=0.0``. Implementations land
    in M3 (lexical + phrase rules) and M4 (structural + rhythm +
    fake_human + soul_signals).

    The signature matches humanize_zh's :func:`score` so callers can
    swap languages without changing argument names. ``has_notes`` will
    suppress ``fake_human`` checks once those rules are implemented.
    """
    if not text or not text.strip():
        return Score(total=0.0, level=level_label(0.0), text_length=0)
    return Score(
        total=0.0,
        level=level_label(0.0),
        violations=[],
        stats={"detector_status": "M1 stub — rules not yet implemented"},
        text_length=len(text),
    )


# ─── Protocol adapter ─────────────────────────────────────────────────────


class EnDetector:
    """Thin :class:`~humanize_core.protocols.Detector` adapter around
    :func:`score`.

    Stateless. Thread-safe (the underlying function does not touch
    shared mutable state at M1).
    """

    code: str = "en"
    version: str = _RULESET_VERSION

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
