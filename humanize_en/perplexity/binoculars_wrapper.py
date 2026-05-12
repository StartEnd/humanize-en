"""Thin wrapper around the upstream Binoculars detector.

This module is the implementation behind :mod:`humanize_en.perplexity`.
It is deliberately separated from ``__init__.py`` so the package's
import-time surface stays small and predictable: importing
``humanize_en.perplexity`` only pulls these four symbols, and *none*
of them touch ``binoculars`` / ``transformers`` / ``torch`` until a
user explicitly calls :func:`score` or constructs a
:class:`BinocularsScorer`.

Design notes
------------
* **Why a class _and_ a free function?**
  :class:`BinocularsScorer` is the supported public API for tests,
  benchmark scripts, or callers that need their own (non-singleton)
  detector — e.g. a different ``device_map`` or a different model
  pair. :func:`score` is the 90%-case convenience wrapper that
  silently re-uses one global instance, because each instance allocates
  ~14 GB of Falcon weights.

* **Why subclass ``ImportError``?**
  Callers in higher layers (the §7.1 humanization gate, benchmark
  loaders) typically wrap their detector loads in
  ``try: ... except ImportError:``. Inheriting from ``ImportError``
  means they can ignore our error transparently, while still
  surfacing a useful ``str(exc)`` with the two install commands
  when it bubbles up.

* **Why ``is_available()`` uses ``importlib.util.find_spec``?**
  ``find_spec`` checks whether the module *can* be imported without
  executing it. That matters because ``import binoculars`` at the
  top of the upstream package itself imports ``transformers`` and
  may trigger a HF token check / network probe. We want availability
  detection to be a pure file-system / sys.path operation, free of
  side effects.

* **Why expose the upstream score un-inverted?**
  Binoculars' polarity (lower = AI, higher = human) is the opposite
  of every other detector in this repo. We resist the temptation to
  "normalise" because (a) it would silently disagree with the paper
  and the released CLI, and (b) every consumer of this wrapper is a
  benchmark or gate that needs to compare against published numbers.
  Polarity correction happens in the *caller* (the gate), not here.
"""

from __future__ import annotations

import importlib
import importlib.util
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Type-only import; never resolved at runtime. Lets mypy/IDEs
    # understand the upstream ``Binoculars`` shape if the user has
    # the package installed, without forcing it as a runtime dep.
    from binoculars import Binoculars  # noqa: F401


_INSTALL_HINT = (
    "Binoculars is an optional dependency of humanize-en. "
    "Install both extras:\n"
    "    pip install 'humanize-en[perplexity]'\n"
    "    pip install git+https://github.com/ahans30/Binoculars\n"
    "See https://github.com/ahans30/Binoculars for licence and model details "
    "(downloads ~14 GB of Falcon-7B weights on first use)."
)


class PerplexityNotInstalledError(ImportError):
    """Raised when Binoculars is requested but not installed.

    Subclasses :class:`ImportError` so callers wrapping detector loads
    in a broad ``except ImportError`` clause continue to work. The
    error message always carries the two install commands so the user
    can copy-paste a fix from the traceback.
    """

    def __init__(self, message: str | None = None) -> None:
        full = (message + "\n\n" + _INSTALL_HINT) if message else _INSTALL_HINT
        super().__init__(full)


def is_available() -> bool:
    """Return True if the ``binoculars`` package can be imported.

    Uses :func:`importlib.util.find_spec` so the check is **side-effect
    free**: it never actually imports the upstream module, never
    triggers a HF Hub token lookup, and never warms the model cache.
    Safe to call from health endpoints or test collection hooks.
    """
    try:
        return importlib.util.find_spec("binoculars") is not None
    except (ImportError, ValueError):
        # find_spec can itself raise on a half-installed parent package.
        # Treat any failure as "not available" — the wrapper is optional
        # by design and must never explode at availability-check time.
        return False


class BinocularsScorer:
    """Lazy, reusable wrapper around :class:`binoculars.Binoculars`.

    The constructor records configuration but does **not** import or
    instantiate the upstream detector. Loading happens on first
    :meth:`score` call, so:

    * constructing a scorer is cheap and never raises
      :class:`PerplexityNotInstalledError` (instantiation may still
      fail later if the dep is missing — that's intentional);
    * test code can freely create scorers and decide whether to
      exercise the heavy path or stub :meth:`_load` out.

    Parameters
    ----------
    observer_name_or_path:
        Override for the upstream ``observer_name_or_path`` arg
        (the base Falcon-7B). ``None`` uses Binoculars' default.
    performer_name_or_path:
        Override for the upstream ``performer_name_or_path`` arg
        (Falcon-7B-instruct). ``None`` uses Binoculars' default.
    use_bfloat16:
        Whether to load weights in bf16 (half the VRAM, no measurable
        accuracy hit per the paper). Forwarded to the upstream
        constructor when not ``None``.
    mode:
        Either ``"accuracy"`` (paper default) or ``"low-fpr"`` (the
        high-precision threshold). Forwarded only when set.
    """

    def __init__(
        self,
        *,
        observer_name_or_path: str | None = None,
        performer_name_or_path: str | None = None,
        use_bfloat16: bool | None = None,
        mode: str | None = None,
    ) -> None:
        self._observer = observer_name_or_path
        self._performer = performer_name_or_path
        self._use_bfloat16 = use_bfloat16
        self._mode = mode
        # The actual detector instance, lazily populated by :meth:`_load`.
        # Typed as ``Any`` because the runtime type lives in an optional
        # dep and we don't want to leak it into our public type surface.
        self._detector: Any | None = None
        # Guard concurrent first-call loads. Without this, two threads
        # hitting :meth:`score` simultaneously would each load 14 GB of
        # weights. Per-instance lock — multiple ``BinocularsScorer``
        # objects can warm up independently.
        self._lock = threading.Lock()

    # ── lifecycle ────────────────────────────────────────────────────

    def _load(self) -> Any:
        """Import and instantiate the upstream Binoculars detector.

        Separate from :meth:`score` so tests can override it
        (``scorer._load = lambda: stub``) without touching the public
        API. Raises :class:`PerplexityNotInstalledError` if the
        ``binoculars`` package is not importable.
        """
        try:
            module = importlib.import_module("binoculars")
        except ImportError as exc:
            raise PerplexityNotInstalledError(
                f"Could not import 'binoculars' (underlying error: {exc})."
            ) from exc

        try:
            cls = module.Binoculars
        except AttributeError as exc:  # pragma: no cover — upstream API change
            raise PerplexityNotInstalledError(
                "The installed 'binoculars' package does not expose a "
                "Binoculars class. This usually means the install is "
                "broken or an incompatible fork was installed."
            ) from exc

        # Forward only the kwargs the caller actually customised.
        # Avoids fighting the upstream constructor's evolving defaults
        # (it has gained / dropped kwargs across releases).
        kwargs: dict[str, Any] = {}
        if self._observer is not None:
            kwargs["observer_name_or_path"] = self._observer
        if self._performer is not None:
            kwargs["performer_name_or_path"] = self._performer
        if self._use_bfloat16 is not None:
            kwargs["use_bfloat16"] = self._use_bfloat16
        if self._mode is not None:
            kwargs["mode"] = self._mode
        return cls(**kwargs)

    def _ensure_loaded(self) -> Any:
        """Return the cached detector, loading it under a lock if needed."""
        if self._detector is None:
            with self._lock:
                # Double-checked locking: another thread may have
                # finished loading while we were waiting on the lock.
                if self._detector is None:
                    self._detector = self._load()
        return self._detector

    @property
    def loaded(self) -> bool:
        """True iff the underlying Binoculars detector has been instantiated."""
        return self._detector is not None

    # ── scoring ──────────────────────────────────────────────────────

    def score(self, text: str) -> float:
        """Return the upstream Binoculars score for ``text``.

        Polarity matches the paper: **lower = more AI-like**,
        higher = more human-like. We do not invert.

        Raises
        ------
        PerplexityNotInstalledError
            If ``binoculars`` cannot be imported.
        TypeError
            If ``text`` is not a string. We surface this early because
            the upstream :meth:`compute_score` on some versions returns
            a list when given a list, which would silently break
            single-text callers.
        """
        if not isinstance(text, str):
            raise TypeError(
                f"BinocularsScorer.score expects a single string, "
                f"got {type(text).__name__}. Use .score_batch for lists."
            )
        detector = self._ensure_loaded()
        return float(detector.compute_score(text))

    def score_batch(self, texts: list[str]) -> list[float]:
        """Score a batch of strings in one upstream call.

        Falls back to a Python-level loop if the installed Binoculars
        version doesn't accept a list (older releases were single-text
        only). Kept tolerant rather than version-gated because the
        upstream API surface drifts faster than we can pin it.
        """
        if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
            raise TypeError("score_batch expects a list[str].")
        detector = self._ensure_loaded()
        try:
            raw = detector.compute_score(texts)
        except (TypeError, ValueError):
            # Upstream rejected the list — score one-by-one.
            return [float(detector.compute_score(t)) for t in texts]
        # Some versions return a numpy array; coerce element-wise to float
        # so callers get a plain ``list[float]`` regardless.
        return [float(x) for x in raw]


# ── module-level singleton + convenience function ──────────────────────

# Single shared detector across the process so repeated ``score()``
# calls don't each pay the ~14 GB / multi-minute warm-up. Tests that
# need isolation should instantiate :class:`BinocularsScorer` directly.
_GLOBAL_SCORER: BinocularsScorer | None = None
_GLOBAL_LOCK = threading.Lock()


def _get_global_scorer() -> BinocularsScorer:
    """Return the lazily-constructed module-level scorer.

    Visible for tests (``humanize_en.perplexity.binoculars_wrapper._get_global_scorer``)
    so they can assert singleton semantics without reaching into the
    private module global directly.
    """
    global _GLOBAL_SCORER
    if _GLOBAL_SCORER is None:
        with _GLOBAL_LOCK:
            if _GLOBAL_SCORER is None:
                _GLOBAL_SCORER = BinocularsScorer()
    return _GLOBAL_SCORER


def _reset_global_scorer() -> None:
    """Test-only hook: drop the cached singleton so the next call rebuilds.

    Underscore-prefixed because production code should never need this:
    tearing down 14 GB of weights and re-loading them is purely a unit
    test concern (e.g. asserting that ``score`` recovers after a
    config change). Not exported in :data:`__all__`.
    """
    global _GLOBAL_SCORER
    with _GLOBAL_LOCK:
        _GLOBAL_SCORER = None


def score(text: str) -> float:
    """Score ``text`` with the process-wide Binoculars singleton.

    Convenience equivalent of::

        humanize_en.perplexity.BinocularsScorer().score(text)

    but reuses one detector across calls. Same polarity as the paper:
    lower = AI, higher = human. Raises
    :class:`PerplexityNotInstalledError` if the optional dep is missing.
    """
    return _get_global_scorer().score(text)


__all__ = [
    "BinocularsScorer",
    "PerplexityNotInstalledError",
    "is_available",
    "score",
]
