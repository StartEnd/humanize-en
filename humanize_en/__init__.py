"""humanize_en — English AI-text humanizer plugin for humanize-core.

Status: pre-alpha through plan-M7 (Binoculars wrapper). The detector,
n-gram engine, replacements table, prompt pack, strength knob, and
optional Binoculars wrapper are wired in. The dedicated ``humanize-en``
CLI and the §7.1 benchmark gate are still pending (plan-M8/M9). See
``docs/plan.md`` §10 for the full roadmap.

Public surface (mirrors :mod:`humanize_zh` so test fixtures port
across the two plugins with a package-prefix substitution)::

    from humanize_en import (
        score,                    # rule-based detection
        ngram_score,              # statistical detection
        combined_score,           # fused rule + ngram (release gate)
        postprocess_humanize,     # one-pass LLM polish
        judge,                    # LLM final review
        iterative_polish,         # writer/judge ping-pong loop
        build_humanize_prompt,    # rule-list assembler
        llm,                      # LLM provider layer
        en_profile,               # registered LanguageProfile
        Strength,                 # low / medium / high knob
    )

    llm.autodetect()                              # discover from env
    llm.use("openai", api_key="sk-...")
    llm.use_openai_compat(                        # DeepSeek / Groq / OpenRouter / …
        name="deepseek", base_url="...", api_key="...", model="deepseek-chat",
    )

The package auto-registers :data:`en_profile` with
:mod:`humanize_core.language_registry` on import, so
``humanize_core.get_language("en")`` works without an explicit
register call. Auto-registration is wrapped in
``contextlib.suppress(LanguageAlreadyRegistered)`` for re-import
idempotency (the same pattern :mod:`humanize_zh` uses on the ZH side).

Honest about limits: this plugin's detector targets *interpretable*
AI tells (~0.80 AUC class). For raw detection accuracy on un-attacked
English use Binoculars (ICML 2024) — the optional
:mod:`humanize_en.perplexity` wrapper exposes it under
``humanize-en[perplexity]``. See README §"Limitations".
"""

from __future__ import annotations

import contextlib

# ── Framework re-exports (language registry + protocol type) ───────────
#
# We depend on ``humanize-core`` directly (no ``humanize-zh`` dependency)
# so the EN plugin ships independently. Mirrors :mod:`humanize_zh`'s
# pattern but imports framework symbols from their canonical home.
from humanize_core.language_registry import (
    LanguageAlreadyRegistered,
    UnknownLanguage,
    get_language,
    list_languages,
    list_profiles,
    register_language,
    unregister_language,
)
from humanize_core.protocols import LanguageProfile

# ── LLM provider layer (re-export of humanize_core.llm) ────────────────
from . import llm
from ._lang.en.profile import en_profile

# ── Detection / aggregation surfaces ───────────────────────────────────
from .combined import CombinedScore, combined_score
from .detect import Score, Violation, score

# ── Polish / judge / loop surfaces ─────────────────────────────────────
from .iterative import IterativeResult, RoundResult, iterative_polish
from .judge import format_report as format_judge_report
from .judge import judge
from .ngram_check import NgramScore, ngram_score
from .postprocess import postprocess_humanize

# ── Prompt assembly + strength knob ────────────────────────────────────
from .prompt import (
    Strength,
    build_humanize_postprocess_prompt,
    build_humanize_prompt,
)

__version__ = "0.1.0a0"

# ── Auto-register the built-in EN profile on package import ─────────────
#
# Same pattern as :mod:`humanize_zh`: every public entry-point in
# ``humanize-core`` (``judge`` / ``iterative_polish`` /
# ``postprocess_humanize``) can now look up ``"en"`` via
# :func:`get_language` without callers having to hand-register first.
# We swallow :class:`LanguageAlreadyRegistered` because:
#
#   1. ``importlib.reload(humanize_en)`` would otherwise raise.
#   2. Tests sometimes clear + re-register; a double import must no-op.
#
# Any *other* error here is surfaced — a broken built-in profile is a
# packaging bug we want to see immediately, not silently.
with contextlib.suppress(LanguageAlreadyRegistered):
    register_language(en_profile)


__all__ = [
    "__version__",
    # LLM provider layer
    "llm",
    # detection
    "score",
    "Score",
    "Violation",
    "ngram_score",
    "NgramScore",
    "combined_score",
    "CombinedScore",
    # polish / judge / loop
    "postprocess_humanize",
    "judge",
    "format_judge_report",
    "iterative_polish",
    "IterativeResult",
    "RoundResult",
    # prompt assembly
    "build_humanize_prompt",
    "build_humanize_postprocess_prompt",
    "Strength",
    # language registry re-exports
    "LanguageProfile",
    "get_language",
    "list_languages",
    "list_profiles",
    "register_language",
    "unregister_language",
    "LanguageAlreadyRegistered",
    "UnknownLanguage",
    "en_profile",
]
