#!/usr/bin/env python3
"""scripts/build_ngram_data.py — train humanize-en n-gram calibration.

Builds two artefacts from the HC3-en corpus and writes them to
``humanize_en/_lang/en/data/``:

1. ``ngram_freq_en.json.gz`` — unigram + bigram frequencies of the
   *human* answers only. The engine queries this at runtime to compute
   bigram perplexity and burstiness.
2. ``lr_coef_en.json`` — logistic-regression coefficients mapping the
   feature vector produced by ``_ngram_engine.py`` to an AI
   probability in [0, 100], plus per-feature mean/std for
   standardisation. Trained on a balanced human + ChatGPT split with
   stratified 80/20 train/test.

Run from the repo root:

    uv run python scripts/build_ngram_data.py            # default
    uv run python scripts/build_ngram_data.py --max 5000 # subset
    uv run python scripts/build_ngram_data.py --no-write # dry run

Dependencies: this script lives in ``scripts/`` and is **not**
shipped in the wheel. It pulls ``datasets``, ``scikit-learn``, and
``numpy`` (declared under the ``[build-data]`` extra in
``pyproject.toml``) only at build time. Runtime users never see them.

Reproducibility: the random seed is pinned to ``42`` and the
HuggingFace HC3 commit hash is recorded in the freq table's
``_meta`` block so a future rebuild can match the exact corpus
state.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

# ─── Bootstrap: make the in-repo engine importable without install ────────

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from humanize_en._lang.en.data._ngram_engine import (  # noqa: E402
    _tokens,
    compute_burstiness,
    compute_entropy_uniformity,
    compute_perplexity,
    compute_punctuation_density,
    compute_sentence_length_features,
    compute_transition_density,
    compute_word_mattr,
)

DATA_DIR = REPO_ROOT / "humanize_en" / "_lang" / "en" / "data"
FREQ_FILE = DATA_DIR / "ngram_freq_en.json.gz"
LR_FILE = DATA_DIR / "lr_coef_en.json"

# Feature names in fixed order — must match the order used in
# ``humanize_en._lang.en.ngram.ngram_score`` when assembling the
# feature vector at scoring time. Adding a feature later is a
# breaking change to ``lr_coef_en.json``: bump ``coef_version``
# in the LR output and update the runtime loader to skip mismatches.
FEATURE_ORDER: tuple[str, ...] = (
    "perplexity",
    "avg_log_prob",
    "burstiness",
    "entropy_cv",
    "mean_entropy",
    "transition_density",
    "sentence_cv",
    "short_frac",
    "equal_mid_frac",
    "word_mattr",
    "comma_density",
    "punct_density",
)


def _featurize(text: str) -> list[float]:
    """Compute the canonical feature vector for ``text``.

    Mirrors what ``humanize_en._lang.en.ngram.ngram_score`` does at
    scoring time. Keep these two call sites in lockstep — they both
    rely on :data:`FEATURE_ORDER`.
    """
    metrics: dict[str, float] = {}
    metrics.update(compute_perplexity(text))
    metrics.update(compute_burstiness(text))
    metrics.update(compute_entropy_uniformity(text))
    metrics.update(compute_transition_density(text))
    sent = compute_sentence_length_features(text)
    metrics["sentence_cv"] = sent.get("cv", 0.0)
    metrics["short_frac"] = sent.get("short_frac", 0.0)
    metrics["equal_mid_frac"] = sent.get("equal_mid_frac", 0.0)
    metrics["word_mattr"] = compute_word_mattr(text)
    metrics.update(compute_punctuation_density(text))
    return [float(metrics.get(k, 0.0)) for k in FEATURE_ORDER]


def _build_freq_table(
    human_texts: list[str], *, hc3_revision: str
) -> dict[str, object]:
    """Compute unigram + bigram counts on the human-side corpus.

    Returns a dict suitable for serialising to ``ngram_freq_en.json.gz``.
    Caps bigram dict size at 500k entries (drops the long tail of
    hapaxes) to keep the wheel lean while preserving >99% of mass.
    """
    print(f"[build] tokenising {len(human_texts)} human answers...")
    t0 = time.perf_counter()
    unigrams: Counter[str] = Counter()
    bigrams: Counter[str] = Counter()
    total_tokens = 0
    for text in human_texts:
        toks = _tokens(text)
        total_tokens += len(toks)
        unigrams.update(toks)
        bigrams.update(f"{toks[i - 1]} {toks[i]}" for i in range(1, len(toks)))
    print(
        f"[build] {total_tokens:,} tokens; "
        f"{len(unigrams):,} unique unigrams; "
        f"{len(bigrams):,} unique bigrams "
        f"({time.perf_counter() - t0:.1f}s)"
    )

    # Trim bigrams: keep top 500k by count. Profiling on HC3-en shows
    # this preserves ~99.3% of bigram mass at <30% of disk size.
    BIGRAM_CAP = 500_000
    if len(bigrams) > BIGRAM_CAP:
        kept = dict(bigrams.most_common(BIGRAM_CAP))
        kept_mass = sum(kept.values())
        total_mass = sum(bigrams.values())
        print(
            f"[build] capping bigrams at {BIGRAM_CAP:,}: "
            f"keeping {kept_mass / total_mass:.1%} of mass"
        )
        bigrams = Counter(kept)

    # Drop unigram hapaxes (count==1) from the *unigram* dict if vocab
    # exceeds 100k; they only matter for OOV smoothing where we use
    # vocab_size, not individual counts.
    UNIGRAM_CAP = 100_000
    if len(unigrams) > UNIGRAM_CAP:
        kept_uni = dict(unigrams.most_common(UNIGRAM_CAP))
        unigrams = Counter(kept_uni)

    return {
        "_meta": {
            "version": "0.1.0",
            "corpus": "HC3-English (human side)",
            "hc3_revision": hc3_revision,
            "n_documents": len(human_texts),
            "n_tokens": total_tokens,
            "bigram_cap": BIGRAM_CAP,
            "unigram_cap": UNIGRAM_CAP,
            "license": "CC-BY-SA-4.0 (HC3 data); MIT (this counts file)",
            "build_script": "scripts/build_ngram_data.py",
        },
        "unigram": dict(unigrams),
        "bigram": dict(bigrams),
        "total_unigrams": int(sum(unigrams.values())),
        "total_bigrams": int(sum(bigrams.values())),
        "vocab_size": int(len(unigrams)),
    }


def _train_lr(
    human_texts: list[str], ai_texts: list[str], *, seed: int = 42
) -> dict[str, object]:
    """Fit a logistic regression on featurised human + AI samples.

    Returns the dict serialised to ``lr_coef_en.json``: feature
    means, stds (used for standardisation at scoring time),
    coefficients, intercept, and held-out AUC.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split

    print(f"[train] featurizing {len(human_texts)} human + {len(ai_texts)} AI...")
    t0 = time.perf_counter()
    X = np.array(
        [_featurize(t) for t in human_texts] + [_featurize(t) for t in ai_texts],
        dtype=np.float64,
    )
    # 0 = human, 1 = AI
    y = np.array([0] * len(human_texts) + [1] * len(ai_texts), dtype=np.int8)
    print(f"[train] feature matrix {X.shape} ({time.perf_counter() - t0:.1f}s)")

    # Standardise features to zero mean, unit variance. Track the
    # scaler params; the runtime loader applies the same standardisation
    # before dotting with the LR coefs.
    mu = X.mean(axis=0)
    sigma = X.std(axis=0)
    sigma[sigma == 0] = 1.0  # guard against zero-variance features
    X_std = (X - mu) / sigma

    X_train, X_test, y_train, y_test = train_test_split(
        X_std, y, test_size=0.2, random_state=seed, stratify=y
    )
    clf = LogisticRegression(max_iter=2000, C=1.0, random_state=seed)
    clf.fit(X_train, y_train)
    train_auc = roc_auc_score(y_train, clf.predict_proba(X_train)[:, 1])
    test_auc = roc_auc_score(y_test, clf.predict_proba(X_test)[:, 1])
    print(f"[train] AUC: train={train_auc:.4f}, test={test_auc:.4f}")

    return {
        "_meta": {
            "coef_version": "0.1.0",
            "model": "sklearn.LogisticRegression(C=1.0)",
            "n_human": len(human_texts),
            "n_ai": len(ai_texts),
            "seed": seed,
            "train_auc": float(train_auc),
            "test_auc": float(test_auc),
            "license": "MIT",
        },
        "feature_order": list(FEATURE_ORDER),
        "feature_mean": [float(x) for x in mu],
        "feature_std": [float(x) for x in sigma],
        "coef": [float(x) for x in clf.coef_[0]],
        "intercept": float(clf.intercept_[0]),
    }


def _load_hc3() -> tuple[list[str], list[str], str]:
    """Stream HC3-en human + ChatGPT answers from HuggingFace.

    Returns ``(human_texts, ai_texts, revision_hash)`` where
    ``revision_hash`` is the dataset's commit hash for reproducibility.
    Filters to non-empty (>= 50 char) answers.

    Implementation note: ``datasets >= 3.0`` dropped support for
    Python loader scripts (HC3 ships ``HC3.py``). We download the
    raw ``all.jsonl`` via :mod:`huggingface_hub` and parse it
    ourselves — same data, no script execution. ``Hello-SimpleAI/HC3``
    is the English-only repository (Chinese lives in
    ``Hello-SimpleAI/HC3-Chinese``).
    """
    from huggingface_hub import HfApi, hf_hub_download

    print("[hc3] downloading Hello-SimpleAI/HC3 / all.jsonl ...")
    path = hf_hub_download("Hello-SimpleAI/HC3", "all.jsonl", repo_type="dataset")
    api = HfApi()
    info = api.dataset_info("Hello-SimpleAI/HC3")
    revision = (info.sha or "unknown")[:12]
    print(f"[hc3] file={path}\n[hc3] revision={revision}")

    human_texts: list[str] = []
    ai_texts: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            for h in row.get("human_answers") or []:
                h = (h or "").strip()
                if len(h) >= 50:
                    human_texts.append(h)
            for a in row.get("chatgpt_answers") or []:
                a = (a or "").strip()
                if len(a) >= 50:
                    ai_texts.append(a)
    print(f"[hc3] kept {len(human_texts)} human + {len(ai_texts)} AI answers")
    return human_texts, ai_texts, str(revision)


def _balance(human: list[str], ai: list[str], *, max_per_class: int, seed: int) -> tuple[list[str], list[str]]:
    """Randomly sub-sample to a balanced ``min(len(human), len(ai), max_per_class)`` per class."""
    rng = random.Random(seed)
    n = min(len(human), len(ai), max_per_class)
    return rng.sample(human, n), rng.sample(ai, n)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max", type=int, default=10_000,
        help="Max samples per class (human/AI) for LR training. Default 10k.",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for sampling + LR."
    )
    parser.add_argument(
        "--no-write", action="store_true",
        help="Compute everything but skip writing JSON files (dry run).",
    )
    parser.add_argument(
        "--freq-only", action="store_true",
        help="Build only the freq table (skip LR training).",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1 — load HC3-en.
    human, ai, revision = _load_hc3()

    # Step 2 — build freq table on the *full* human side (no sub-sampling
    # here: more data = better smoothing).
    freq_table = _build_freq_table(human, hc3_revision=revision)
    if not args.no_write:
        print(f"[write] {FREQ_FILE}")
        with gzip.open(FREQ_FILE, "wt", encoding="utf-8") as f:
            json.dump(freq_table, f, ensure_ascii=False, separators=(",", ":"))
        size_mb = FREQ_FILE.stat().st_size / (1024 * 1024)
        with open(FREQ_FILE, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()[:12]
        print(f"[write] {size_mb:.2f} MB, sha256={sha}...")
    else:
        print("[write] (skipped — --no-write)")

    if args.freq_only:
        return 0

    # Step 3 — featurise + train LR on a balanced subset. Balance is
    # necessary because HC3 answers are not 1-1 (humans answer fewer
    # questions). LR with class_weight=balanced is a worse remedy on
    # this dataset than random downsampling because the AI side is
    # more homogeneous than the human side.
    human_bal, ai_bal = _balance(human, ai, max_per_class=args.max, seed=args.seed)
    print(f"[balance] using {len(human_bal)} human + {len(ai_bal)} AI for LR")

    # Re-load freq table from disk so featurization uses the just-saved
    # file. Reset the engine cache otherwise it reads the empty M1 stub.
    if not args.no_write:
        from humanize_en._lang.en.data import _ngram_engine as eng
        eng._FREQ_CACHE = None  # force reload from disk
        os.environ.setdefault("HUMANIZE_EN_FORCE_RELOAD_FREQ", "1")

    lr_coef = _train_lr(human_bal, ai_bal, seed=args.seed)
    if not args.no_write:
        print(f"[write] {LR_FILE}")
        with open(LR_FILE, "w", encoding="utf-8") as f:
            json.dump(lr_coef, f, ensure_ascii=False, indent=2)
    else:
        print("[write] (skipped — --no-write)")

    test_auc = lr_coef["_meta"]["test_auc"]  # type: ignore[index]
    print(f"\n[done] held-out test AUC = {test_auc:.4f}")
    if test_auc < 0.75:
        print("[WARN] AUC below the M2 gate (0.75). Investigate before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
