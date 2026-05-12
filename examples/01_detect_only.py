"""Example 1: detect-only — three-layer English scoring with no LLM.

Run::

    uv run python examples/01_detect_only.py

The detect (rule) and ngram (statistical) layers are pure Python and
run in milliseconds. The combined score takes the max of the two —
any layer flagging HIGH (>= 50) triggers the release gate that the
benchmark suite uses as its acceptance bar (see ``docs/plan.md`` §7.1).

Mirrors ``humanize-zh/examples/01_detect_only.py`` modulo language.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from humanize_en import combined_score, ngram_score, score  # noqa: E402

ARTICLE = """
It is important to note that this comprehensive solution will leverage
cutting-edge AI to deliver a paradigm shift in how we approach the problem.

Moreover, by harnessing the power of next-generation technology, we unlock
unprecedented opportunities for our stakeholders. Furthermore, our holistic
methodology ensures that all key aspects are carefully considered.

In conclusion, this transformative initiative will redefine the landscape and
position us for sustained competitive advantage in the years ahead.
"""


def main() -> None:
    rule = score(ARTICLE)
    print(f"Layer 1 (rule):  {rule.total:.1f}/100  ({rule.level})")
    print(f"  fired {len(rule.violations)} violations")
    for v in rule.violations[:5]:
        print(f"    - {v.rule}: sample {v.sample!r} (count {v.count}, +{v.score})")

    ng = ngram_score(ARTICLE)
    if ng.available:
        print(
            f"Layer 2 (ngram): {ng.ai_probability:.1f}/100  ({ng.level})  "
            f"perplexity={ng.metrics.get('perplexity', '?'):.1f}"
        )
    else:
        print("Layer 2 (ngram): unavailable (missing data files)")

    cs = combined_score(ARTICLE)
    print(f"\nCombined: {cs.combined_probability:.1f}/100  ({cs.combined_level})")
    print("  decision:", "BLOCK" if cs.combined_probability >= 50 else "OK")


if __name__ == "__main__":
    main()
