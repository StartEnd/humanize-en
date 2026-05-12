"""Example 2: polish — call an LLM to rewrite English AI tells out.

Run (after exporting one of ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY``
/ ``DEEPSEEK_API_KEY`` / …)::

    uv run python examples/02_polish_with_llm.py

If you use a local OpenAI-compatible relay, set ``OPENAI_API_KEY``
plus ``OPENAI_BASE_URL=http://127.0.0.1:8080/v1``; the SDK picks up
``base_url`` automatically.

Mirrors ``humanize-zh/examples/02_polish_with_llm.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from humanize_en import postprocess_humanize  # noqa: E402

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
    polished, after, before = postprocess_humanize(
        ARTICLE,
        scene="analysis",  # essay / academic / blog also supported
        # provider=None  # auto-detect from env (OPENAI_API_KEY / ...).
        # provider="deepseek"  # or pin a specific provider name.
    )
    if before is not None:
        print(f"before: {before.total:.1f}/100  ({before.level})")
    if after is not None:
        print(f"after:  {after.total:.1f}/100  ({after.level})")
    print()
    print("--- polished article ---")
    print(polished)


if __name__ == "__main__":
    if not any(os.environ.get(k) for k in (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
        "GROQ_API_KEY", "OPENROUTER_API_KEY", "MOONSHOT_API_KEY",
        "GLM_API_KEY", "DASHSCOPE_API_KEY", "OLLAMA_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
    )):
        print(
            "warning: no LLM provider env vars detected — postprocess_humanize "
            "will fall back to deterministic cleanup only."
        )
    main()
