"""§7.2 — Secondary gate: meaning preservation via BERTScore.

Spec (from ``docs/plan.md`` §7.2)::

    from bert_score import score as bert_score
    P, R, F1 = bert_score(after_texts, before_texts, lang="en")
    assert F1.mean() >= 0.85

Why this gate exists: a polish pass that "wins" the §7.1
Binoculars-drop gate by replacing the article with arbitrary
unrelated prose would still pass §7.1 but be useless. BERTScore
F1 measures semantic similarity between the original and
polished text; ≥ 0.85 is the standard "edit-pass-quality"
threshold reported in the DIPPER paraphrase paper (Krishna et al.,
NeurIPS 2023).

The gate **skip-marks** when:

* ``bert-score`` is not installed (``[bench]`` extra missing).
* No LLM provider is configured — the deterministic cleanup
  fallback rewrites very little, which would inflate F1 and
  hide the real polish-quality question.
"""

from __future__ import annotations

import os

import pytest

from humanize_en import postprocess_humanize
from tests.bench._data import load_samples

F1_THRESHOLD = 0.85
SAMPLE_CAP = 50  # cap to keep CI runtimes reasonable when bert-score is on


def _bert_score_available() -> bool:
    try:
        import bert_score  # noqa: F401
    except ImportError:
        return False
    return True


def _llm_provider_available() -> bool:
    try:
        from humanize_core.llm import has_active
    except ImportError:  # pragma: no cover
        return False
    return has_active()


@pytest.mark.skipif(
    not _bert_score_available(),
    reason="bert-score not installed; install humanize-en[bench]",
)
@pytest.mark.skipif(
    not _llm_provider_available(),
    reason="no LLM provider configured; polish degrades to deterministic "
           "cleanup which would inflate F1 misleadingly",
)
@pytest.mark.skipif(
    os.environ.get("HUMANIZE_EN_SKIP_BENCH") == "1",
    reason="HUMANIZE_EN_SKIP_BENCH=1 set in environment",
)
def test_bertscore_meaning_preservation() -> None:
    """Polished texts must remain semantically close to originals."""
    from bert_score import score as bert_score_fn

    samples = load_samples("bundled")[:SAMPLE_CAP]
    befores: list[str] = []
    afters: list[str] = []
    for s in samples:
        polished, _after, _before = postprocess_humanize(
            s.text, scene=s.scene,
        )
        befores.append(s.text)
        afters.append(polished)

    # bert_score returns three torch tensors (P, R, F1). We care
    # about F1; ``lang="en"`` selects the canonical model
    # (``roberta-large`` per Zhang 2020). ``rescale_with_baseline=False``
    # to match the threshold reported in the plan, which uses raw F1.
    _P, _R, F1 = bert_score_fn(afters, befores, lang="en", verbose=False)
    mean_f1 = float(F1.mean())

    assert mean_f1 >= F1_THRESHOLD, (
        f"§7.2 gate failed: mean BERTScore-F1 = {mean_f1:.3f} "
        f"(threshold {F1_THRESHOLD}). Polish is straying too far from "
        f"the original meaning. Tighten the writer prompt or reduce "
        f"strength."
    )
