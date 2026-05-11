"""humanize_en — English AI-text humanizer plugin for humanize-core.

This package is **pre-alpha (M1 scaffold)**. The detector, n-gram
engine, replacement table, and prompt pack currently ship as stubs
that satisfy the :mod:`humanize_core.protocols` contracts but do
*not* produce useful scores or rewrites yet.

Implementation roadmap (see ``Humanize/humanize-en/docs/plan.md``):

- **M1** ✅ scaffold (this commit)
- M2 — n-gram engine trained on HC3-en
- M3-M4 — rule library (25+ EN AI tells)
- M5 — replacement table + EN writer/judge prompts
- M6 — strength knob (low/medium/high, Humano-inspired)
- M7 — optional Binoculars wrapper (``humanize-en[perplexity]``)
- M8 — humanization gates (Binoculars-drop + BERTScore)

Public API surface (planned, mirrors humanize-zh):

    from humanize_en import (
        score,                    # rule-based detection
        ngram_score,              # statistical detection (M2+)
        combined_score,
        postprocess_humanize,     # LLM polish
        judge,                    # LLM final review
        build_humanize_prompt,
        llm,                      # LLM provider layer
        en_profile,               # the registered LanguageProfile
    )

At M1, only :data:`en_profile`, :func:`get_language` re-exports,
and ``humanize_core.get_language("en")`` work. The detection /
polish surfaces will be wired in M3+.

Honest about limits: this plugin's detector targets *interpretable*
AI tells and ships a 0.80-AUC-class rule + ngram pipeline. For raw
detection accuracy use Binoculars (ICML 2024) — see README.
"""

from __future__ import annotations

import contextlib

# We depend on humanize-core directly (no humanize-zh dependency) so
# the EN plugin can ship independently. Mirrors humanize-zh's pattern
# but imports the framework symbols from their canonical home.
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

from ._lang.en.profile import en_profile

__version__ = "0.1.0a0"

# ── Auto-register the built-in EN profile on package import ─────────────
#
# Same pattern as ``humanize_zh``: every public entry-point in
# ``humanize-core`` (judge / iterative_polish / postprocess_humanize)
# can now look up "en" via :func:`get_language` without callers having
# to hand-register first. We swallow ``LanguageAlreadyRegistered``
# because:
#   1. ``importlib.reload(humanize_en)`` would otherwise raise.
#   2. Tests sometimes clear+re-register; double-import must no-op.
# Any *other* error here is surfaced — a broken built-in profile is a
# packaging bug we want loud, not silent.
with contextlib.suppress(LanguageAlreadyRegistered):
    register_language(en_profile)


__all__ = [
    "__version__",
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
