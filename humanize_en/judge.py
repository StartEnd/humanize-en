#!/usr/bin/env python3
"""humanize_en.judge — EN-defaulted thin shim over :mod:`humanize_core.judge`.

The LLM final-review pass itself lives in humanize-core. This module:

- delegates :func:`judge` to the framework with ``lang="en"`` defaulted;
- ships an **English-localized** :func:`format_report` so CLI output
  and saved ``*.judge.md`` files match the README's English voice
  (humanize-zh keeps its own Chinese version on the ZH side — same
  pattern, different language);
- preserves a ``python -m humanize_en.judge`` CLI entry point.

Re-exports (``JUDGE_PROMPT``, ``_call_llm``, ``_parse_json``,
``_resolve_profile``) point at the canonical homes so downstream
tests / scripts that imported through ``humanize_en.judge`` keep
working without a path change.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from humanize_core.judge import _call_llm, _parse_json, _resolve_profile  # noqa: F401
from humanize_core.judge import judge as _core_judge
from humanize_core.protocols import LanguageProfile

from . import llm as _llm_module
from ._lang.en.prompts import JUDGE_PROMPT  # noqa: F401  (legacy re-export)
from .llm import (  # noqa: F401  (legacy re-exports)
    LLMError,
    LLMNotConfiguredError,
    LLMProvider,
    ProviderArg,
    provider_id,
    resolve_provider,
)

logger = logging.getLogger(__name__)


def judge(
    article: str,
    *,
    profile: LanguageProfile | None = None,
    writer_provider: ProviderArg = None,
    judge_provider: ProviderArg = None,
    allow_self_judge: bool = False,
) -> dict[str, Any]:
    """Run the LLM final-review pass on ``article`` with the EN profile.

    Thin wrapper over :func:`humanize_core.judge.judge`. The only
    behavioral difference vs the framework function is that
    ``lang="en"`` is locked in: there is no ``lang=`` kwarg here
    because callers who want to switch language should reach for
    ``humanize_core.judge.judge`` directly (or import the other
    plugin's ``judge``).

    Args:
        article: Source text to review.
        profile: Pre-resolved :class:`LanguageProfile`. ``None``
            (default) uses the registered EN profile.
        writer_provider: LLM provider responsible for the writer
            side of the collusion-detection check (the framework
            cross-checks the writer's commit against the judge's
            verdict).
        judge_provider: LLM provider running the actual judgement.
            Must differ from ``writer_provider`` unless
            ``allow_self_judge=True``.
        allow_self_judge: Override the collusion check.

    Returns:
        Dict with the judge's structured verdict plus an internal
        ``_meta`` envelope (provider ids + article length). On error,
        ``_error`` / ``_parse_error`` is set and the function returns
        rather than raising.
    """
    return _core_judge(
        article,
        profile=profile,
        lang="en",
        writer_provider=writer_provider,
        judge_provider=judge_provider,
        allow_self_judge=allow_self_judge,
    )


def format_report(result: dict[str, Any]) -> str:
    """Render :func:`judge`'s JSON output as an English Markdown report.

    Symmetric to :func:`humanize_zh.judge.format_report` but emits
    English section headers (``## Final verdict``, ``### Strongest
    judgements``, ``⚠️ High risk``) so the EN-side CLI and saved
    ``*.judge.md`` files read naturally without translation.

    Why a local copy rather than calling
    :func:`humanize_core.judge.format_report`? The framework version
    aims at language-agnostic field labels and skips the high-risk /
    rewrite-brief sections; the plugin-local copy is the place to
    make the report polished for English readers.
    """
    if "_error" in result:
        return f"[judge] error: {result['_error']}"
    if "_parse_error" in result:
        return (
            f"[judge] JSON parse failure: {result['_parse_error']}\n\n"
            f"raw:\n{result.get('_raw', '')}"
        )

    lines: list[str] = []
    publishable = bool(result.get("publishable", False))
    lines.append(
        f"## Final verdict: {'✅ publishable' if publishable else '❌ needs revision'}"
    )
    lines.append("")

    if best := result.get("best_theses"):
        lines.append(f"### Strongest judgements ({len(best)})")
        for t in best:
            lines.append(f"- {t}")
        lines.append("")

    if worst := result.get("worst_ai_sections"):
        lines.append(f"### Most AI-flavoured passages ({len(worst)})")
        for w in worst:
            if isinstance(w, dict):
                lines.append(f"- “{w.get('para', '?')}…” — {w.get('reason', '?')}")
            else:
                lines.append(f"- {w}")
        lines.append("")

    if claims := result.get("unsupported_claims"):
        lines.append(f"### Unsupported claims ({len(claims)})")
        for c in claims:
            if isinstance(c, dict):
                lines.append(
                    f"- “{c.get('claim', '?')}” missing: "
                    f"{c.get('missing_evidence', '?')}"
                )
            else:
                lines.append(f"- {c}")
        lines.append("")

    if smell := result.get("template_smell"):
        lines.append(f"### Template-smell issues ({len(smell)})")
        for s in smell:
            lines.append(f"- {s}")
        lines.append("")

    if fake := result.get("fake_human_details"):
        lines.append(f"### Fabricated human details ({len(fake)}) ⚠️ High risk")
        for f in fake:
            lines.append(f"- {f}")
        lines.append("")

    if brief := result.get("rewrite_brief"):
        lines.append("### Rewrite brief")
        lines.append(brief)

    if meta := result.get("_meta"):
        lines.append("")
        lines.append(
            f"---\n*judge: {meta.get('judge_provider')} | "
            f"writer: {meta.get('writer_provider')} | "
            f"article: {meta.get('article_length'):,} chars*"
        )
    return "\n".join(lines)


def main() -> None:
    """Lightweight CLI for ``python -m humanize_en.judge``.

    The fully-featured EN CLI lands with M9 (see ``docs/plan.md`` §10).
    This entry point exists so the README's documented command works
    in the meantime; it mirrors :func:`humanize_zh.judge.main` line-
    for-line modulo English copy.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 2:
        print(
            "usage: python -m humanize_en.judge <file> "
            "[--writer <provider>] [--judge <provider>] "
            "[--json] [--allow-self-judge]"
        )
        print()
        print(
            "Provider names: openai | anthropic | deepseek | groq | openrouter | "
            "moonshot | glm | qwen | ollama"
        )
        print(
            "Omit both --writer and --judge to use the active / "
            "autodetected provider for judging."
        )
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"error: file not found: {path}")
        sys.exit(1)

    writer = None
    judge_p = None
    allow_self = "--allow-self-judge" in sys.argv
    out_json = "--json" in sys.argv
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--writer" and i + 1 < len(args):
            writer = args[i + 1]
            i += 2
        elif a == "--judge" and i + 1 < len(args):
            judge_p = args[i + 1]
            i += 2
        else:
            i += 1

    if (
        judge_p is None
        and not _llm_module.has_active()
        and _llm_module.autodetect() is None
    ):
        print(
            "error: no LLM provider configured. Set one of "
            "OPENAI_API_KEY / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY / ..."
        )
        sys.exit(2)

    article = path.read_text(encoding="utf-8")
    result = judge(
        article,
        writer_provider=writer,
        judge_provider=judge_p,
        allow_self_judge=allow_self,
    )

    if out_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))

    if not out_json:
        report_path = path.with_suffix(".judge.md")
        report_path.write_text(format_report(result), encoding="utf-8")
        print(f"\nreport saved: {report_path}")


if __name__ == "__main__":
    main()


__all__ = ["judge", "format_report", "main", "JUDGE_PROMPT"]
