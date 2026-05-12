"""Example 3: iterative — writer ↔ judge closed loop, multi-round to target.

Run (needs two distinct providers — writer ≠ judge by default, to
prevent the same model from grading its own output)::

    DEEPSEEK_API_KEY=... ANTHROPIC_API_KEY=... \\
        uv run python examples/03_iterative_loop.py

For a single-provider sanity check, pass ``allow_self_judge=True`` —
useful for local debugging, but the collusion risk is real (a model
will gladly approve its own paragraphs).

Mirrors ``humanize-zh/examples/03_iterative_loop.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from humanize_en import iterative_polish  # noqa: E402

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
    result = iterative_polish(
        ARTICLE,
        rounds=3,
        target_ai_score=30,
        scene="analysis",
        writer_provider="deepseek",     # autodetected from DEEPSEEK_API_KEY
        judge_provider="anthropic",     # different model = no collusion
        allow_self_judge=False,
    )
    print(f"stopped: {result.stopped_reason}")
    print(f"writer: {result.writer_provider}, judge: {result.judge_provider}")
    print(f"rounds: {len(result.rounds)}")
    for r in result.rounds:
        print(
            f"  round {r.round}: ai_score={r.ai_score} verdict={r.verdict} "
            f"polished_len={r.polished_len}"
        )
    print()
    print("--- final ---")
    print(result.final_text)


if __name__ == "__main__":
    main()
