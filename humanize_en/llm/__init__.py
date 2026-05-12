"""humanize_en.llm — backward-compat re-export of :mod:`humanize_core.llm`.

The EN plugin owns no LLM client code; every provider lives in
``humanize_core.llm``. This module forwards the public surface
(``use``, ``autodetect``, ``LLMProvider``, error classes, …) plus
each submodule (``humanize_en.llm.openai_provider`` and friends)
so that:

* the README's ``from humanize_en import llm; llm.use("openai", ...)``
  pattern works without callers having to know about ``humanize_core``;
* test helpers that imported from ``humanize_zh.llm.<sub>`` translate
  one-to-one to ``humanize_en.llm.<sub>`` while still resolving to the
  *same module object*. That last point matters because providers
  carry mutable singleton state (``humanize_core.llm.registry._ACTIVE``,
  autodetect locks). Two parallel copies of those globals would let
  ``llm.use(...)`` write into one and ``llm.get_active()`` read from
  another, silently breaking the active-provider invariant.

Pattern mirrors :mod:`humanize_zh.llm` byte-for-byte — see the comment
block there for the full rationale.
"""

from __future__ import annotations

import sys as _sys

from humanize_core import llm as _core_llm
from humanize_core.llm import (
    LLMAuthError,
    LLMConfigError,
    LLMContextLimitError,
    LLMError,
    LLMNotConfiguredError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    ProviderArg,
    autodetect,
    clear,
    get_active,
    has_active,
    list_providers,
    provider_id,
    required_env_keys_hint,
    resolve_provider,
    set_active,
    use,
    use_callable,
    use_openai_compat,
)

# Re-bind every submodule so ``humanize_en.llm.<name>`` resolves to
# the *same module object* as ``humanize_core.llm.<name>``. Without
# this, ``from humanize_en.llm.openai_provider import OpenAIProvider``
# would either fail (no file here) or trigger a fresh import that
# ships its own provider class — breaking ``isinstance`` checks that
# compare against the canonical class.
for _name in (
    "_resolve",
    "anthropic_provider",
    "base",
    "callable_provider",
    "openai_compat",
    "openai_provider",
    "registry",
):
    _submod = getattr(_core_llm, _name, None)
    if _submod is None:
        # Force-import; some providers lazy-load their SDK and are not
        # auto-bound on the package namespace.
        import importlib

        _submod = importlib.import_module(f"humanize_core.llm.{_name}")
    _sys.modules[f"{__name__}.{_name}"] = _submod

del _sys, _core_llm, _name, _submod

__all__ = [
    # Public API functions
    "use",
    "use_openai_compat",
    "use_callable",
    "autodetect",
    "set_active",
    "get_active",
    "has_active",
    "clear",
    "list_providers",
    "required_env_keys_hint",
    "resolve_provider",
    "provider_id",
    # Types
    "LLMProvider",
    "LLMResponse",
    "ProviderArg",
    # Exceptions
    "LLMError",
    "LLMConfigError",
    "LLMAuthError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMContextLimitError",
    "LLMProviderError",
    "LLMNotConfiguredError",
]
