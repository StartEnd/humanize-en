"""Example 4: inject the humanize rules section into your own writing prompt.

Run::

    uv run python examples/04_inject_rules_into_prompt.py

This is the cheapest integration mode: pull the rules block at
template build time, splice it into *your* writing prompt, and let
the LLM avoid the AI tells during generation rather than have to
fix them afterward.

Mirrors ``humanize-zh/examples/04_inject_rules_into_prompt.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from humanize_en import build_humanize_prompt  # noqa: E402

MY_TEMPLATE = """\
You are a senior tech essayist. Write an in-depth analysis of {topic},
800-1200 words. You MUST follow the writing discipline below:

{HUMANIZE_RULES}

Begin writing now:
"""


def main() -> None:
    rules = build_humanize_prompt(scene="analysis")  # or essay / academic / blog
    full_prompt = MY_TEMPLATE.format(
        topic="indie-developer SaaS growth playbooks",
        HUMANIZE_RULES=rules,
    )
    print(f"final prompt length: {len(full_prompt):,} chars")
    print()
    print(full_prompt[:600] + "\n... (truncated for display) ...")


if __name__ == "__main__":
    main()
