"""Tests for :mod:`humanize_en.perplexity` (M8 Binoculars wrapper).

The Binoculars detector is a heavyweight optional dependency (~14 GB
of Falcon-7B weights, multi-minute warm-up on CPU). We never load
real weights in CI; every test either:

* exercises the **availability / error path** with the dep absent
  (this is the common case — the test machine doesn't have
  binoculars installed), or
* exercises the **happy path** against a *mock* ``binoculars``
  module injected into ``sys.modules`` so the wrapper's lazy import
  picks it up.

This keeps the suite < 1s while still covering both branches of
:func:`humanize_en.perplexity.score`.
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any
from unittest.mock import MagicMock

import pytest

from humanize_en import perplexity
from humanize_en.perplexity import (
    BinocularsScorer,
    PerplexityNotInstalledError,
    binoculars_wrapper,
    is_available,
    score,
)

# ─── helpers ────────────────────────────────────────────────────────────


class _FakeBinoculars:
    """Stand-in for ``binoculars.Binoculars``.

    Returns a deterministic score so tests can assert it bubbles
    through ``BinocularsScorer.score`` unchanged. Records constructor
    kwargs so tests can verify forwarding behaviour.
    """

    instances: list[_FakeBinoculars] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.call_log: list[Any] = []
        _FakeBinoculars.instances.append(self)

    def compute_score(self, text: Any) -> Any:
        self.call_log.append(text)
        if isinstance(text, list):
            # Mirror the upstream batch behaviour for one path; another
            # test forces this to raise so we hit the per-item fallback.
            return [0.42 + i * 0.01 for i, _ in enumerate(text)]
        # Lower = AI in the paper; pick a mid-range number.
        return 0.7331


@pytest.fixture
def fake_binoculars_module(monkeypatch: pytest.MonkeyPatch):
    """Inject a fake ``binoculars`` module into ``sys.modules``.

    Resets the wrapper's singleton afterwards so each test starts
    from a clean slate. Yields the fake module so tests can poke at it.
    """
    _FakeBinoculars.instances.clear()
    fake_mod = types.ModuleType("binoculars")
    fake_mod.Binoculars = _FakeBinoculars  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "binoculars", fake_mod)
    # Force ``importlib.util.find_spec`` to see the injected module.
    # Inserting into sys.modules is enough for ``importlib.import_module``,
    # but ``find_spec`` consults the import machinery directly. Patch it
    # at the wrapper level so we don't disturb other tests.
    monkeypatch.setattr(
        binoculars_wrapper.importlib.util,
        "find_spec",
        lambda name: types.SimpleNamespace() if name == "binoculars" else None,
    )
    binoculars_wrapper._reset_global_scorer()
    yield fake_mod
    binoculars_wrapper._reset_global_scorer()


@pytest.fixture
def no_binoculars_module(monkeypatch: pytest.MonkeyPatch):
    """Guarantee ``binoculars`` is *not* importable for the test.

    Important even if the test machine doesn't have binoculars
    installed: a future developer might install it locally and we
    don't want the "missing dep" tests to silently switch to the
    happy path. We force the absence by removing any cached entry
    and intercepting :func:`importlib.import_module`.
    """
    monkeypatch.delitem(sys.modules, "binoculars", raising=False)
    real_import = importlib.import_module

    def fake_import(name: str, package: str | None = None) -> Any:
        if name == "binoculars":
            raise ImportError("No module named 'binoculars' (forced absent)")
        return real_import(name, package)

    monkeypatch.setattr(binoculars_wrapper.importlib, "import_module", fake_import)
    monkeypatch.setattr(
        binoculars_wrapper.importlib.util,
        "find_spec",
        lambda name: None if name == "binoculars" else importlib.util.find_spec(name),
    )
    binoculars_wrapper._reset_global_scorer()
    yield
    binoculars_wrapper._reset_global_scorer()


# ─── public surface ─────────────────────────────────────────────────────


class TestPublicSurface:
    """``humanize_en.perplexity`` exposes exactly four public symbols."""

    def test_module_all(self) -> None:
        assert set(perplexity.__all__) == {
            "BinocularsScorer",
            "PerplexityNotInstalledError",
            "is_available",
            "score",
        }

    def test_symbols_are_reexports(self) -> None:
        """Re-exports point at the wrapper module, not a stale copy."""
        assert perplexity.BinocularsScorer is binoculars_wrapper.BinocularsScorer
        assert perplexity.score is binoculars_wrapper.score
        assert perplexity.is_available is binoculars_wrapper.is_available
        assert (
            perplexity.PerplexityNotInstalledError
            is binoculars_wrapper.PerplexityNotInstalledError
        )

    def test_error_is_importerror(self) -> None:
        """Subclassing ImportError matters — gate callers rely on it."""
        assert issubclass(PerplexityNotInstalledError, ImportError)

    def test_error_message_includes_install_hint(self) -> None:
        exc = PerplexityNotInstalledError()
        msg = str(exc)
        assert "humanize-en[perplexity]" in msg
        assert "git+https://github.com/ahans30/Binoculars" in msg

    def test_error_message_includes_user_context(self) -> None:
        exc = PerplexityNotInstalledError("Custom reason: foo bar")
        msg = str(exc)
        assert "Custom reason: foo bar" in msg
        # Hint must still be present, not replaced.
        assert "humanize-en[perplexity]" in msg


# ─── is_available ───────────────────────────────────────────────────────


class TestIsAvailable:
    def test_false_when_module_absent(self, no_binoculars_module: None) -> None:
        assert is_available() is False

    def test_true_when_module_present(self, fake_binoculars_module: types.ModuleType) -> None:
        assert is_available() is True

    def test_swallows_find_spec_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``find_spec`` can itself raise on half-installed parents.

        We treat any failure as "not available" rather than letting it
        bubble — availability checks must be safe to call from health
        probes.
        """

        def boom(name: str) -> None:
            raise ValueError("half-installed parent package")

        monkeypatch.setattr(binoculars_wrapper.importlib.util, "find_spec", boom)
        assert is_available() is False


# ─── BinocularsScorer ──────────────────────────────────────────────────


class TestBinocularsScorerConstructor:
    """Construction is cheap and never touches the optional dep."""

    def test_construction_does_not_load(self) -> None:
        scorer = BinocularsScorer()
        assert scorer.loaded is False

    def test_construction_succeeds_without_dep(self, no_binoculars_module: None) -> None:
        """Even with no binoculars installed, the constructor must succeed."""
        scorer = BinocularsScorer()
        assert scorer.loaded is False

    def test_constructor_records_overrides(self) -> None:
        scorer = BinocularsScorer(
            observer_name_or_path="my/observer",
            performer_name_or_path="my/performer",
            use_bfloat16=False,
            mode="low-fpr",
        )
        assert scorer._observer == "my/observer"
        assert scorer._performer == "my/performer"
        assert scorer._use_bfloat16 is False
        assert scorer._mode == "low-fpr"


class TestBinocularsScorerLoading:
    def test_missing_dep_raises_typed_error(self, no_binoculars_module: None) -> None:
        scorer = BinocularsScorer()
        with pytest.raises(PerplexityNotInstalledError) as exc_info:
            scorer.score("hello")
        # Original cause is preserved (chained, not swallowed).
        assert isinstance(exc_info.value.__cause__, ImportError)

    def test_load_forwards_only_set_kwargs(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        scorer = BinocularsScorer(use_bfloat16=True, mode="accuracy")
        scorer.score("hello world")
        assert len(_FakeBinoculars.instances) == 1
        instance = _FakeBinoculars.instances[0]
        # Only the kwargs we explicitly set were forwarded.
        assert instance.kwargs == {"use_bfloat16": True, "mode": "accuracy"}

    def test_load_forwards_no_kwargs_when_all_defaults(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        scorer = BinocularsScorer()
        scorer.score("hello")
        assert _FakeBinoculars.instances[0].kwargs == {}

    def test_load_forwards_model_path_overrides(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        """All four kwarg slots reach the upstream constructor."""
        scorer = BinocularsScorer(
            observer_name_or_path="tiiuae/falcon-7b",
            performer_name_or_path="tiiuae/falcon-7b-instruct",
        )
        scorer.score("hi")
        assert _FakeBinoculars.instances[0].kwargs == {
            "observer_name_or_path": "tiiuae/falcon-7b",
            "performer_name_or_path": "tiiuae/falcon-7b-instruct",
        }

    def test_load_is_cached_per_instance(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        scorer = BinocularsScorer()
        scorer.score("first")
        scorer.score("second")
        scorer.score("third")
        # One detector, three scoring calls.
        assert len(_FakeBinoculars.instances) == 1
        assert _FakeBinoculars.instances[0].call_log == ["first", "second", "third"]

    def test_loaded_property_flips_after_first_score(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        scorer = BinocularsScorer()
        assert scorer.loaded is False
        scorer.score("x")
        assert scorer.loaded is True


class TestBinocularsScorerScore:
    def test_returns_upstream_value_uninverted(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        """Polarity must match the paper: we do not invert."""
        scorer = BinocularsScorer()
        result = scorer.score("any text")
        assert result == pytest.approx(0.7331)

    def test_coerces_to_float(self, fake_binoculars_module: types.ModuleType) -> None:
        """Numpy / torch scalars must come back as plain floats."""

        class WeirdNumeric:
            def __float__(self) -> float:
                return 0.5

        fake = MagicMock()
        fake.compute_score.return_value = WeirdNumeric()

        scorer = BinocularsScorer()
        scorer._detector = fake  # bypass loading entirely

        out = scorer.score("hello")
        assert isinstance(out, float)
        assert out == 0.5

    def test_rejects_non_string(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        scorer = BinocularsScorer()
        with pytest.raises(TypeError, match="single string"):
            scorer.score(["a", "b"])  # type: ignore[arg-type]
        # Detector must not even have been loaded.
        assert scorer.loaded is False


class TestBinocularsScorerScoreBatch:
    def test_happy_path_returns_floats(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        scorer = BinocularsScorer()
        out = scorer.score_batch(["one", "two", "three"])
        assert out == [pytest.approx(0.42), pytest.approx(0.43), pytest.approx(0.44)]
        assert all(isinstance(x, float) for x in out)

    def test_falls_back_when_upstream_rejects_list(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        """Older Binoculars releases were single-text only; we must cope."""
        scorer = BinocularsScorer()
        # Force the loaded detector to a stub that rejects lists once.
        list_calls = {"n": 0}

        def picky_compute_score(text: Any) -> float:
            if isinstance(text, list):
                list_calls["n"] += 1
                raise TypeError("this version only takes a single str")
            return 0.123

        stub = MagicMock()
        stub.compute_score.side_effect = picky_compute_score
        scorer._detector = stub

        out = scorer.score_batch(["a", "b"])
        assert list_calls["n"] == 1
        assert out == [pytest.approx(0.123), pytest.approx(0.123)]

    def test_rejects_non_list(self, fake_binoculars_module: types.ModuleType) -> None:
        scorer = BinocularsScorer()
        with pytest.raises(TypeError, match="list"):
            scorer.score_batch("not a list")  # type: ignore[arg-type]

    def test_rejects_list_with_non_strings(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        scorer = BinocularsScorer()
        with pytest.raises(TypeError):
            scorer.score_batch(["ok", 42])  # type: ignore[list-item]


# ─── module-level singleton + score() ──────────────────────────────────


class TestModuleScore:
    def test_score_reuses_singleton(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        s1 = score("first call")
        s2 = score("second call")
        s3 = score("third call")
        assert s1 == s2 == s3 == pytest.approx(0.7331)
        # One scorer, one detector — singleton across module-level calls.
        assert len(_FakeBinoculars.instances) == 1

    def test_score_raises_typed_error_when_missing(
        self, no_binoculars_module: None
    ) -> None:
        with pytest.raises(PerplexityNotInstalledError):
            score("hello")

    def test_reset_global_scorer_rebuilds(
        self, fake_binoculars_module: types.ModuleType
    ) -> None:
        score("warm")
        first = binoculars_wrapper._get_global_scorer()
        binoculars_wrapper._reset_global_scorer()
        second = binoculars_wrapper._get_global_scorer()
        assert first is not second
