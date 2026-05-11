#!/usr/bin/env python3
"""scripts/mine_rule_candidates.py — discover AI tells from HC3-en.

Computes per-word and per-phrase frequency ratios between the
ChatGPT and human sides of HC3-en, surfaces the top candidates,
and writes a TSV summary that the human curator (us) consults
when authoring ``data/rules.json``.

This is a *discovery* tool, not a build step. The output is
informational; rules are still hand-curated and cross-referenced
against published prior art (Liang et al. 2024, Plain English
Campaign, GPTZero methodology) before going into the rule file.

Run from the repo root:

    uv run python scripts/mine_rule_candidates.py
    uv run python scripts/mine_rule_candidates.py --top 80 --min-count 100
    uv run python scripts/mine_rule_candidates.py --phrases-only

Outputs (gitignored under ``scripts/_mining/``):

- ``word_candidates.tsv``   — single-word AI/human ratios.
- ``phrase_candidates.tsv`` — bigram/trigram ratios for words
  already overrepresented in AI text.
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "scripts" / "_mining"


# Tokenisation MUST match :mod:`humanize_en._lang.en.data._ngram_engine`.
# Imported lazily so a missing engine module doesn't break the script's
# argparse / help output.
def _engine_tokenize(text: str) -> list[str]:
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from humanize_en._lang.en.data._ngram_engine import _tokens
    return _tokens(text)


def _hc3_path() -> str:
    """Locate the HC3 ``all.jsonl`` cached by ``hf_hub_download``.

    Falls back to a clear error if the file is missing — run
    ``scripts/build_ngram_data.py`` once first to populate the cache.
    """
    cands = glob.glob(
        str(
            Path.home()
            / ".cache/huggingface/hub/datasets--Hello-SimpleAI--HC3/"
              "snapshots/*/all.jsonl"
        )
    )
    if not cands:
        raise SystemExit(
            "HC3 cache not found. Run scripts/build_ngram_data.py first "
            "to download Hello-SimpleAI/HC3 / all.jsonl."
        )
    return cands[0]


def _load(jsonl: str) -> tuple[list[list[str]], list[list[str]]]:
    """Return ``(human_token_lists, ai_token_lists)``.

    Splits per-answer so phrase mining can later compute
    document-frequency (DF) ratios in addition to corpus counts —
    a single very long AI answer using "moreover" 50 times shouldn't
    dominate the ratio.
    """
    human: list[list[str]] = []
    ai: list[list[str]] = []
    with open(jsonl, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            for h in row.get("human_answers") or []:
                if h:
                    human.append(_engine_tokenize(h))
            for a in row.get("chatgpt_answers") or []:
                if a:
                    ai.append(_engine_tokenize(a))
    return human, ai


def _ratios_words(
    human: list[list[str]], ai: list[list[str]], *, min_count: int
) -> list[tuple[str, float, float, float, int, int]]:
    """Per-word AI/human ratios.

    Returns a list of ``(word, ratio, ai_per_M, h_per_M, ai_count, h_count)``.
    Ratio uses ``max(h_per_M, 1)`` denominator to keep AI-only words
    finite (otherwise rare-but-AI-distinctive tells like "delve" would
    silently pin to inf and confuse the sort).
    """
    h_count: Counter[str] = Counter()
    a_count: Counter[str] = Counter()
    for toks in human:
        h_count.update(toks)
    for toks in ai:
        a_count.update(toks)
    h_total = sum(h_count.values()) or 1
    a_total = sum(a_count.values()) or 1
    out: list[tuple[str, float, float, float, int, int]] = []
    for w, ac in a_count.items():
        if ac < min_count:
            continue
        hc = h_count.get(w, 0)
        a_pm = ac * 1e6 / a_total
        h_pm = hc * 1e6 / h_total
        ratio = a_pm / max(h_pm, 1.0)
        out.append((w, ratio, a_pm, h_pm, ac, hc))
    out.sort(key=lambda x: -x[1])
    return out


def _ratios_phrases(
    human: list[list[str]],
    ai: list[list[str]],
    *,
    n: int,
    min_count: int,
) -> list[tuple[str, float, float, float, int, int]]:
    """N-gram (n=2,3) AI/human ratios.

    Counts on a per-document basis to compute *document frequency*
    (one hit per answer) — phrase tells are interesting because they
    appear across *many* AI answers, not because one answer used them
    a lot.
    """
    h_df: Counter[str] = Counter()
    a_df: Counter[str] = Counter()

    def _ngrams(toks: list[str]) -> set[str]:
        return {" ".join(toks[i : i + n]) for i in range(len(toks) - n + 1)}

    for toks in human:
        h_df.update(_ngrams(toks))
    for toks in ai:
        a_df.update(_ngrams(toks))
    h_docs = max(len(human), 1)
    a_docs = max(len(ai), 1)

    out: list[tuple[str, float, float, float, int, int]] = []
    for ph, ac in a_df.items():
        if ac < min_count:
            continue
        hc = h_df.get(ph, 0)
        a_pct = ac * 100 / a_docs  # % of AI answers using this phrase
        h_pct = hc * 100 / h_docs
        ratio = a_pct / max(h_pct, 0.05)  # 0.05% floor to avoid div by 0
        out.append((ph, ratio, a_pct, h_pct, ac, hc))
    out.sort(key=lambda x: -x[1])
    return out


def _write_tsv(rows: list[tuple[str, float, float, float, int, int]], path: Path, header: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\t".join(header) + "\n")
        for row in rows:
            f.write("\t".join(str(x) for x in row) + "\n")


def _print_table(
    title: str,
    rows: list[tuple[str, float, float, float, int, int]],
    *,
    top: int,
    rate_label: str,
) -> None:
    print(f"\n=== {title} (top {top}) ===")
    print(f"{'term':<32} {rate_label + '_AI':>10} {rate_label + '_H':>10} {'ratio':>7} {'ai#':>6} {'h#':>6}")
    print("-" * 80)
    for term, ratio, a_rate, h_rate, ac, hc in rows[:top]:
        print(f"{term:<32} {a_rate:>10.2f} {h_rate:>10.2f} {ratio:>7.1f} {ac:>6} {hc:>6}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--top", type=int, default=60, help="Rows to print per table.")
    p.add_argument("--min-count", type=int, default=200, help="Min AI corpus count for words.")
    p.add_argument("--min-phrase-count", type=int, default=80, help="Min AI document-frequency for phrases.")
    p.add_argument("--phrases-only", action="store_true")
    p.add_argument("--no-write", action="store_true", help="Skip writing TSVs.")
    args = p.parse_args()

    jsonl = _hc3_path()
    print(f"[mine] loading {jsonl}")
    human, ai = _load(jsonl)
    print(f"[mine] {len(human):,} human + {len(ai):,} AI answers")

    if not args.phrases_only:
        words = _ratios_words(human, ai, min_count=args.min_count)
        _print_table("word ratios", words, top=args.top, rate_label="per_M")
        if not args.no_write:
            _write_tsv(
                words, OUT_DIR / "word_candidates.tsv",
                ["word", "ratio", "ai_per_M", "h_per_M", "ai_count", "h_count"],
            )
            print(f"\n[mine] wrote {OUT_DIR / 'word_candidates.tsv'}")

    for n in (2, 3):
        phrases = _ratios_phrases(human, ai, n=n, min_count=args.min_phrase_count)
        _print_table(f"{n}-gram phrase ratios (DF-based)", phrases, top=args.top, rate_label="pct_docs")
        if not args.no_write:
            out = OUT_DIR / f"phrase{n}_candidates.tsv"
            _write_tsv(
                phrases, out,
                ["phrase", "ratio", "ai_pct_docs", "h_pct_docs", "ai_doc_freq", "h_doc_freq"],
            )
            print(f"[mine] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
