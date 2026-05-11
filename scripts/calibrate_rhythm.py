#!/usr/bin/env python3
"""scripts/calibrate_rhythm.py — measure sentence/paragraph rhythm
statistics on HC3-en human vs AI sides, so the M4 rhythm_rules
thresholds are grounded in data rather than intuition.

Prints per-side distributions (p25 / p50 / p75) for:

- Sentence-length coefficient of variation (CV)
- Short-sentence ratio (< 6 words)
- Paragraph-length CV
- Paragraph-opening-enumeration ratio (how many paragraphs start
  with ``First,`` / ``Moreover,`` / numbered markers, etc.)

Run from the repo root:

    uv run python scripts/calibrate_rhythm.py
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path
from statistics import mean, pstdev

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from humanize_en._lang.en.data._ngram_engine import (  # noqa: E402
    _paragraphs,
    _sentences,
    _tokens,
)

# Paragraph-opening patterns that scream "AI enumerated scaffold".
_PARA_OPENING_RE = re.compile(
    r"^\s*("
    r"first(?:ly)?,|second(?:ly)?,|third(?:ly)?,|"
    r"finally,|lastly,|"
    r"moreover,|furthermore,|additionally,|in\s+addition,|"
    r"on\s+the\s+other\s+hand,|in\s+contrast,|"
    r"\d+[\.\)]\s+|"
    r"[-*•]\s+"
    r")",
    re.IGNORECASE,
)


def _percentiles(values: list[float], ps: tuple[float, ...] = (0.1, 0.25, 0.5, 0.75, 0.9)) -> dict[float, float]:
    if not values:
        return dict.fromkeys(ps, 0.0)
    s = sorted(values)
    n = len(s)
    return {p: s[min(n - 1, int(p * n))] for p in ps}


def _cv(values: list[int]) -> float:
    if len(values) < 2 or mean(values) == 0:
        return 0.0
    return pstdev(values) / mean(values)


def _collect_stats(answer: str) -> tuple[float | None, float | None, float | None, float | None]:
    """Return (sentence_cv, short_ratio, paragraph_cv, opener_ratio).
    ``None`` for metrics that need more data than the answer has.
    """
    sents = _sentences(answer)
    if len(sents) < 3:
        return (None, None, None, None)
    sent_wc = [len(_tokens(s)) for s in sents]
    sent_wc = [w for w in sent_wc if w > 0]
    if len(sent_wc) < 3:
        return (None, None, None, None)
    s_cv = _cv(sent_wc)
    short_ratio = sum(1 for w in sent_wc if w < 6) / len(sent_wc)

    paras = _paragraphs(answer)
    p_cv = None
    opener_ratio = None
    if len(paras) >= 3:
        para_cc = [len(p) for p in paras]
        p_cv = _cv(para_cc)
        openers = sum(1 for p in paras if _PARA_OPENING_RE.match(p))
        opener_ratio = openers / len(paras)

    return (s_cv, short_ratio, p_cv, opener_ratio)


def main() -> int:
    cands = glob.glob(
        str(
            Path.home()
            / ".cache/huggingface/hub/datasets--Hello-SimpleAI--HC3/"
              "snapshots/*/all.jsonl"
        )
    )
    if not cands:
        raise SystemExit("Run scripts/build_ngram_data.py first.")
    jsonl = cands[0]

    human_stats: list[tuple[float | None, ...]] = []
    ai_stats: list[tuple[float | None, ...]] = []
    with open(jsonl, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            for h in row.get("human_answers") or []:
                if h:
                    human_stats.append(_collect_stats(h))
            for a in row.get("chatgpt_answers") or []:
                if a:
                    ai_stats.append(_collect_stats(a))

    print(f"[calib] {len(human_stats):,} human + {len(ai_stats):,} AI answers\n")

    labels = ["sentence_cv", "short_ratio", "paragraph_cv", "opener_ratio"]
    for i, label in enumerate(labels):
        h = [s[i] for s in human_stats if s[i] is not None]
        a = [s[i] for s in ai_stats if s[i] is not None]
        h_pct = _percentiles(h)
        a_pct = _percentiles(a)
        print(f"=== {label} ===")
        print(f"  human (n={len(h):,}):")
        print(f"    p10={h_pct[0.1]:.3f} p25={h_pct[0.25]:.3f} "
              f"p50={h_pct[0.5]:.3f} p75={h_pct[0.75]:.3f} p90={h_pct[0.9]:.3f}")
        print(f"  ai    (n={len(a):,}):")
        print(f"    p10={a_pct[0.1]:.3f} p25={a_pct[0.25]:.3f} "
              f"p50={a_pct[0.5]:.3f} p75={a_pct[0.75]:.3f} p90={a_pct[0.9]:.3f}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
