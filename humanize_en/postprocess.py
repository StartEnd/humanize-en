"""humanize_en.postprocess — EN-defaulted thin shim over :mod:`humanize_core.postprocess`.

The polish pipeline (detector → deterministic cleanup → LLM polish →
score delta) lives in humanize-core. This shim pins ``lang="en"``
and threads any caller-supplied ``replacements=`` override through a
profile clone, exactly the way :mod:`humanize_zh.postprocess` does
on the ZH side.

Usage::

    from humanize_en import postprocess_humanize, llm

    llm.autodetect()  # or llm.use("openai", ...)
    polished, after, before = postprocess_humanize(article)

    # Aggressive (legacy flag — equivalent to strength="high"):
    polished, _, _ = postprocess_humanize(article, force_llm=True)

The ``Score`` / ``Violation`` re-exports come from
``humanize_en.detect`` for backward compatibility with
:mod:`humanize_zh.postprocess`'s import surface.
"""

from __future__ import annotations

import dataclasses

from humanize_core.postprocess import (
    _BACKTICK_NUMBER_PATTERNS,  # noqa: F401  (legacy re-export)
    _PROTECTED_SPAN_RE,  # noqa: F401  (legacy re-export)
    _best_candidate,  # noqa: F401  (legacy re-export)
    _build_writer_prompt,  # noqa: F401  (legacy re-export)
    _call_llm,  # noqa: F401  (legacy re-export)
    _protect_spans,  # noqa: F401  (legacy re-export)
    _release_distance,  # noqa: F401  (legacy re-export)
    _resolve_profile,  # noqa: F401  (legacy re-export)
    _restore_spans,  # noqa: F401  (legacy re-export)
    _strip_number_backticks,  # noqa: F401  (legacy re-export)
)
from humanize_core.postprocess import (
    _deterministic_cleanup as _core_deterministic_cleanup,
)
from humanize_core.postprocess import (
    postprocess_humanize as _core_postprocess_humanize,
)
from humanize_core.protocols import ReplacementsTable

from . import llm as _llm_module  # noqa: F401  (legacy import path)
from ._lang.en.profile import en_profile
from ._lang.en.replacements import _load_replacements  # noqa: F401  (legacy re-export)
from .detect import Score, Violation, score  # noqa: F401  (legacy re-export)
from .llm import (  # noqa: F401  (legacy re-export)
    LLMError,
    LLMNotConfiguredError,
    ProviderArg,
    resolve_provider,
)
from .prompt import build_humanize_postprocess_prompt  # noqa: F401  (legacy re-export)


class _EnCodeReplacementsAdapter:
    """Re-stamp a caller-supplied :class:`ReplacementsTable` as ``code="en"``.

    Same purpose as ``humanize_zh.postprocess._ZhCodeReplacementsAdapter``:
    :class:`LanguageProfile.__post_init__` validates that every
    component's ``code`` matches the profile code, otherwise it raises
    ``ValueError`` (catching mismatched plugins early). Test fixtures
    inject stub tables with ``code="stub"`` purely as a sentinel —
    they're *meant* as EN overrides. This adapter wraps the stub so
    the profile clone validates while ``ordered_pairs()`` and any
    other plugin-defined attributes flow through unchanged.
    """

    __slots__ = ("_inner",)

    def __init__(self, inner: ReplacementsTable) -> None:
        self._inner = inner

    @property
    def code(self) -> str:  # noqa: D401 — stub
        return "en"

    def ordered_pairs(self) -> list[tuple[str, str]]:
        return self._inner.ordered_pairs()

    def __getattr__(self, name: str):  # forward any plugin-defined extras
        return getattr(self._inner, name)


def _profile_with_optional_replacements(replacements: ReplacementsTable | None):
    """Return ``en_profile`` or a clone with ``replacements`` swapped.

    Mirrors the ZH shim's helper. Returning the singleton when no
    override is requested keeps the framework dispatcher's
    profile-identity-cached fast path warm. The override path goes
    through :class:`_EnCodeReplacementsAdapter` to pass the
    profile-component code-match check.
    """
    if replacements is None:
        return en_profile
    if replacements.code != "en":
        replacements = _EnCodeReplacementsAdapter(replacements)
    return dataclasses.replace(en_profile, replacements=replacements)


def _deterministic_cleanup(
    text: str,
    *,
    replacements: ReplacementsTable | None = None,
) -> str:
    """Mechanically scrub the highest-confidence EN AI tells.

    Thin wrapper over :func:`humanize_core.postprocess._deterministic_cleanup`
    with the profile defaulted to :data:`en_profile`. Used by tests
    and by callers that want the rule-only cleanup pass without an
    LLM round-trip.
    """
    profile = _profile_with_optional_replacements(replacements)
    return _core_deterministic_cleanup(text, profile=profile)


def postprocess_humanize(
    article: str,
    *,
    scene: str = "analysis",
    violations: list[Violation] | None = None,
    provider: ProviderArg = None,
    detect_first: bool = True,
    force_llm: bool = False,
    replacements: ReplacementsTable | None = None,
) -> tuple[str, Score | None, Score | None]:
    """One-pass de-AI polish, EN-defaulted.

    Args:
        article: Source text.
        scene: EN rule-list scene forwarded to the writer prompt
            (``analysis`` / ``essay`` / ``academic`` / ``blog``).
        violations: Pre-computed violation list. ``None`` triggers
            auto-detection via the EN rule + n-gram pipeline.
        provider: Same conventions as :mod:`humanize_en.llm`.
        detect_first: When ``True`` (default) computes the ``before``
            rule score so callers can show a delta.
        force_llm: Skip the "already publishable" early-return so a
            UI's "polish anyway" button always reaches the LLM.
        replacements: Optional :class:`ReplacementsTable` override.
            When present, runs the polish against a profile clone
            with ``replacements`` swapped — used by tests asserting
            the injection plumbing.

    Returns:
        ``(polished_text, after_score, before_score)``. The two score
        slots track the rule layer's :class:`Score` before and after
        polish; either may be ``None`` if ``detect_first=False`` or
        the LLM short-circuited.
    """
    profile = _profile_with_optional_replacements(replacements)
    return _core_postprocess_humanize(
        article,
        profile=profile,
        lang=None,  # profile wins; passing both would be redundant
        scene=scene,
        violations=violations,
        provider=provider,
        detect_first=detect_first,
        force_llm=force_llm,
    )


__all__ = [
    "Score",
    "Violation",
    "score",
    "postprocess_humanize",
    "_deterministic_cleanup",
    "_load_replacements",
    "build_humanize_postprocess_prompt",
]
