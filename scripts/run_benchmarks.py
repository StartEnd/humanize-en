#!/usr/bin/env python3
"""scripts/run_benchmarks.py — drive the plan-M8 benchmark suite.

Runs the three §7 gates and writes the results to
``docs/benchmarks.md``. Each gate degrades gracefully when its
optional dependency (Binoculars / bert-score) is missing — the
output records ``skipped: <reason>`` instead of crashing.

Usage::

    uv run python scripts/run_benchmarks.py
    uv run python scripts/run_benchmarks.py --source raid --n 100
    uv run python scripts/run_benchmarks.py --source bundled --out /tmp/bench.md
    uv run python scripts/run_benchmarks.py --skip-llm   # readability only

The "ground truth" gate runner is :mod:`pytest` (each gate is also
a pytest test under ``tests/bench/``). This script is the
human-facing renderer — it produces the report that goes into
``docs/benchmarks.md``. Both paths share the same gate logic
through helper functions in ``tests.bench``; we don't reimplement.

Output format is pinned by ``tests/test_run_benchmarks_smoke.py``
so changes here that break the report shape fail loudly.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Imports below depend on ``REPO_ROOT`` being on ``sys.path``.
from tests.bench._data import BenchSample, load_samples  # noqa: E402
from tests.bench._readability import flesch_kincaid_grade  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "docs" / "benchmarks.md"


@dataclass
class GateResult:
    """One §7.x gate's outcome."""

    name: str          # "binoculars_drop" / "bertscore_f1" / "readability"
    spec_section: str  # "§7.1" / "§7.2" / "§7.3"
    status: str        # "pass" / "fail" / "skipped"
    metric: float | None = None       # primary number (or None when skipped)
    threshold: float | None = None    # gate threshold for context
    notes: str = ""
    per_sample: list[dict[str, Any]] = field(default_factory=list)


def run_binoculars_drop(
    samples: list[BenchSample],
) -> GateResult:
    """§7.1 — Binoculars score drop. Returns ``status="skipped"`` when
    the optional dep or LLM provider is missing; never raises."""
    from humanize_en.perplexity import is_available as binoculars_available

    if not binoculars_available():
        return GateResult(
            name="binoculars_drop", spec_section="§7.1", status="skipped",
            threshold=0.3,
            notes="Binoculars not installed. Install humanize-en[perplexity] "
                  "AND `pip install git+https://github.com/ahans30/Binoculars`.",
        )
    try:
        from humanize_core.llm import has_active
    except ImportError:  # pragma: no cover
        return GateResult(
            name="binoculars_drop", spec_section="§7.1", status="skipped",
            notes="humanize_core import failed (should not happen).",
        )
    if not has_active():
        return GateResult(
            name="binoculars_drop", spec_section="§7.1", status="skipped",
            threshold=0.3,
            notes="No LLM provider configured. Set OPENAI_API_KEY (or "
                  "another supported provider env var) and rerun.",
        )

    from humanize_en import postprocess_humanize
    from humanize_en.perplexity import score as binoculars_score

    deltas: list[float] = []
    rows: list[dict[str, Any]] = []
    for s in samples:
        before = binoculars_score(s.text)
        polished, _after, _before = postprocess_humanize(
            s.text, scene=s.scene,
        )
        after = binoculars_score(polished)
        delta = after - before
        deltas.append(delta)
        rows.append({
            "id": s.id, "domain": s.domain,
            "binoculars_before": round(before, 4),
            "binoculars_after": round(after, 4),
            "delta": round(delta, 4),
        })

    pass_threshold = 0.3
    pass_fraction = 0.80
    passed = sum(1 for d in deltas if d >= pass_threshold)
    pct = passed / len(deltas) if deltas else 0.0
    return GateResult(
        name="binoculars_drop", spec_section="§7.1",
        status="pass" if pct >= pass_fraction else "fail",
        metric=round(pct, 4), threshold=pass_fraction,
        notes=(
            f"{passed}/{len(deltas)} samples cleared per-sample threshold "
            f"≥ {pass_threshold}. Mean delta: "
            f"{(sum(deltas)/len(deltas)) if deltas else 0:.3f}."
        ),
        per_sample=rows,
    )


def run_bertscore(samples: list[BenchSample]) -> GateResult:
    """§7.2 — BERTScore F1 ≥ 0.85. Skips when bert-score is missing."""
    try:
        from bert_score import score as bert_score_fn
    except ImportError:
        return GateResult(
            name="bertscore_f1", spec_section="§7.2", status="skipped",
            threshold=0.85,
            notes="bert-score not installed. Install humanize-en[bench].",
        )
    try:
        from humanize_core.llm import has_active
    except ImportError:  # pragma: no cover
        return GateResult(
            name="bertscore_f1", spec_section="§7.2", status="skipped",
            notes="humanize_core import failed.",
        )
    if not has_active():
        return GateResult(
            name="bertscore_f1", spec_section="§7.2", status="skipped",
            threshold=0.85,
            notes="No LLM provider configured.",
        )

    from humanize_en import postprocess_humanize

    befores: list[str] = []
    afters: list[str] = []
    rows: list[dict[str, Any]] = []
    for s in samples:
        polished, _after, _before = postprocess_humanize(
            s.text, scene=s.scene,
        )
        befores.append(s.text)
        afters.append(polished)
        rows.append({"id": s.id, "domain": s.domain})

    _P, _R, F1 = bert_score_fn(afters, befores, lang="en", verbose=False)
    f1_list = [float(x) for x in F1]
    for row, f1 in zip(rows, f1_list, strict=True):
        row["bertscore_f1"] = round(f1, 4)
    mean_f1 = sum(f1_list) / len(f1_list)
    return GateResult(
        name="bertscore_f1", spec_section="§7.2",
        status="pass" if mean_f1 >= 0.85 else "fail",
        metric=round(mean_f1, 4), threshold=0.85,
        notes=f"mean F1 over {len(f1_list)} samples.",
        per_sample=rows,
    )


def run_readability(samples: list[BenchSample]) -> GateResult:
    """§7.3 — Mean |ΔFKGL| ≤ 2. Always runnable; only skips when the
    polish path is offline (no LLM provider)."""
    try:
        from humanize_core.llm import has_active
    except ImportError:  # pragma: no cover
        return GateResult(
            name="readability", spec_section="§7.3", status="skipped",
            notes="humanize_core import failed.",
        )
    if not has_active():
        return GateResult(
            name="readability", spec_section="§7.3", status="skipped",
            threshold=2.0,
            notes="No LLM provider configured. Deterministic cleanup "
                  "barely changes readability — gate would be trivial.",
        )

    from humanize_en import postprocess_humanize

    deltas: list[float] = []
    rows: list[dict[str, Any]] = []
    for s in samples:
        polished, _after, _before = postprocess_humanize(
            s.text, scene=s.scene,
        )
        before_grade = flesch_kincaid_grade(s.text)
        after_grade = flesch_kincaid_grade(polished)
        delta = abs(after_grade - before_grade)
        deltas.append(delta)
        rows.append({
            "id": s.id, "domain": s.domain,
            "fkgl_before": round(before_grade, 2),
            "fkgl_after": round(after_grade, 2),
            "abs_delta": round(delta, 2),
        })

    mean_abs_delta = sum(deltas) / len(deltas) if deltas else 0.0
    return GateResult(
        name="readability", spec_section="§7.3",
        status="pass" if mean_abs_delta <= 2.0 else "fail",
        metric=round(mean_abs_delta, 4), threshold=2.0,
        notes=f"mean |Δ FKGL| over {len(deltas)} samples.",
        per_sample=rows,
    )


# ─── Markdown rendering ────────────────────────────────────────────────


def render_report(
    results: list[GateResult],
    *,
    source: str,
    n_samples: int,
    timestamp: str,
) -> str:
    """Render the gate results as ``docs/benchmarks.md``.

    Pinned format — see ``tests/test_run_benchmarks_smoke.py``.
    Don't break the headings / table shape without updating the
    test together.
    """
    lines: list[str] = []
    lines.append("# humanize-en benchmark results")
    lines.append("")
    lines.append(
        "> Generated by `scripts/run_benchmarks.py` against the "
        "plan-M8 §7 gate suite. Do **not** edit by hand — rerun the "
        "driver. Each gate degrades to ``skipped`` (rather than "
        "failing) when its optional dependency is missing; check "
        "the *Notes* column for the install command."
    )
    lines.append("")
    lines.append("## Run metadata")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| `timestamp` | `{timestamp}` |")
    lines.append(f"| `sample_source` | `{source}` |")
    lines.append(f"| `n_samples` | `{n_samples}` |")
    lines.append("")

    # Headline summary.
    lines.append("## Gate summary")
    lines.append("")
    lines.append("| Spec | Gate | Status | Metric | Threshold | Notes |")
    lines.append("|------|------|--------|--------|-----------|-------|")
    for r in results:
        metric_str = (
            f"`{r.metric:.3f}`" if isinstance(r.metric, float) else "—"
        )
        threshold_str = (
            f"`{r.threshold}`" if r.threshold is not None else "—"
        )
        status_emoji = {
            "pass": "✅ pass",
            "fail": "❌ fail",
            "skipped": "⏭ skipped",
        }.get(r.status, r.status)
        lines.append(
            f"| {r.spec_section} | `{r.name}` | {status_emoji} | "
            f"{metric_str} | {threshold_str} | {r.notes} |"
        )
    lines.append("")

    # Per-gate detail (only when there's per-sample data — skipped gates
    # have empty rows).
    for r in results:
        if not r.per_sample:
            continue
        lines.append(f"## {r.spec_section} `{r.name}` — per-sample")
        lines.append("")
        cols = list(r.per_sample[0].keys())
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join("---" for _ in cols) + "|")
        for row in r.per_sample:
            lines.append(
                "| " + " | ".join(str(row.get(c, "")) for c in cols) + " |"
            )
        lines.append("")

    # Always-shown footer with the install / run instructions for
    # each gate. Useful when every gate skips (the v0.1 alpha
    # default state) — the report is otherwise just three
    # "skipped" rows, which leaves the reader without a next
    # step. Static; not dependent on per-run state.
    lines.append("## Enabling each gate")
    lines.append("")
    lines.append(
        "- **§7.1 Binoculars drop** — install the optional extra "
        "and the upstream package:\n"
        "    ```bash\n"
        "    pip install humanize-en[perplexity]\n"
        "    pip install git+https://github.com/ahans30/Binoculars\n"
        "    ```\n"
        "    Requires a CUDA / MPS device and ~14 GB of Falcon-7B "
        "weights on first use."
    )
    lines.append(
        "- **§7.2 BERTScore-F1** — install the bench extra:\n"
        "    ```bash\n"
        "    pip install humanize-en[bench]\n"
        "    ```\n"
        "    Pulls `bert-score`, which downloads `roberta-large` "
        "(~1.4 GB) on first use."
    )
    lines.append(
        "- **§7.3 Flesch-Kincaid** — stdlib only; no install. "
        "Skips only when no LLM provider is configured (the "
        "polish pass collapses to deterministic cleanup, which "
        "barely shifts readability)."
    )
    lines.append(
        "- **All gates** — set one of `OPENAI_API_KEY` / "
        "`ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY` (etc.) to "
        "exercise the LLM polish path."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Regenerate with `make bench` or `uv run python scripts/run_benchmarks.py`.")
    lines.append("")
    return "\n".join(lines)


# ─── CLI ───────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source", choices=("bundled", "raid"), default="bundled",
        help="sample source (default: bundled)",
    )
    parser.add_argument("--n", type=int, default=None, help="cap samples")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"output path (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--json", type=Path, default=None,
        help="also write structured results to this JSON path",
    )
    parser.add_argument(
        "--skip-llm", action="store_true",
        help="skip §7.1 / §7.2 (run only readability + structure)",
    )
    parser.add_argument(
        "--no-autodetect", action="store_true",
        help="don't autodetect LLM providers from env. Forces all "
             "LLM-bound gates to skip with a clean reason — used to "
             "produce the deterministic committed docs/benchmarks.md.",
    )
    args = parser.parse_args()

    samples = load_samples(args.source, n=args.n)
    if not samples:
        print("error: no samples loaded", file=sys.stderr)
        return 2

    # Trigger LLM autodetect once upfront. ``postprocess_humanize``
    # would do this lazily on first call, but our gate runners do a
    # ``has_active()`` preflight check *before* calling polish; without
    # this autodetect, env-configured providers would be mis-reported
    # as "not configured" and §7.1 / §7.2 / §7.3 would all skip.
    #
    # Skipped when ``--no-autodetect`` is passed — used to produce
    # the deterministic committed ``docs/benchmarks.md`` (independent
    # of whatever provider keys the committer happens to have).
    if not args.no_autodetect:
        try:
            from humanize_core import llm as _core_llm
            if not _core_llm.has_active():
                with __import__("contextlib").suppress(Exception):
                    _core_llm.autodetect()
        except ImportError:  # pragma: no cover
            pass

    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")

    results: list[GateResult] = []
    if args.skip_llm:
        # Skip §7.1 / §7.2 with explicit notes — useful when running
        # locally without weights, to still get §7.3 numbers.
        results.append(GateResult(
            name="binoculars_drop", spec_section="§7.1", status="skipped",
            threshold=0.3, notes="--skip-llm passed",
        ))
        results.append(GateResult(
            name="bertscore_f1", spec_section="§7.2", status="skipped",
            threshold=0.85, notes="--skip-llm passed",
        ))
    else:
        results.append(run_binoculars_drop(samples))
        results.append(run_bertscore(samples))
    results.append(run_readability(samples))

    report = render_report(
        results,
        source=args.source,
        n_samples=len(samples),
        timestamp=timestamp,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"wrote {args.out} ({len(report):,} chars)")

    if args.json is not None:
        payload = {
            "timestamp": timestamp,
            "source": args.source,
            "n_samples": len(samples),
            "results": [asdict(r) for r in results],
        }
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")

    # Exit non-zero if any gate failed (skipped does NOT count as failure).
    if any(r.status == "fail" for r in results):
        print("at least one gate FAILED — see report", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
