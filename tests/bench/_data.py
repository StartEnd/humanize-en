"""Sample-loading helpers for the plan-M8 benchmark suite.

Two source kinds:

* ``"bundled"`` (default) — 12 hand-written AI-flavoured essays
  shipped in :mod:`tests.bench._samples_json`. Always available;
  no network or dataset download. Intended for *structure* tests
  (does the pipeline wire up?), not for accuracy claims.
* ``"raid"`` — RAID held-out (Dugan et al., ACL 2024,
  ``raid-bench`` PyPI package). Optional; gated behind the
  ``[bench]`` extra. Use this for the §7.1 gate's honest 100-sample
  ≥0.3 drop measurement.

The bundled samples were each verified to fire ≥ 5 detector
violations and score ≥ 50 on the rule layer (see
``tests/bench/test_pipeline_structure.py::test_bundled_samples_fire_detector``);
that's sufficient signal for the polish pass to have observable
work to do, but **not** sufficient evidence that the rule + n-gram
detector generalises. For real benchmark numbers point the
driver at ``source="raid"``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SamplesSource = Literal["bundled", "raid"]
DEFAULT_SAMPLES_JSON = Path(__file__).resolve().parent / "_samples.json"


@dataclass(frozen=True)
class BenchSample:
    """One labelled benchmark sample.

    Frozen so they hash and so we never accidentally mutate the
    bundled corpus while running comparisons. ``id`` is unique
    within a source.
    """

    id: str
    domain: str          # news / blog / academic / business / ...
    scene: str           # analysis / blog / academic / essay (humanize-en scene tag)
    text: str
    source: str          # "bundled" / "raid:news/none/0001" / ...

    @property
    def length_chars(self) -> int:
        return len(self.text)


def load_samples(
    source: SamplesSource = "bundled",
    *,
    n: int | None = None,
    domain: str | None = None,
) -> list[BenchSample]:
    """Load benchmark samples from the requested source.

    Args:
        source: ``"bundled"`` for the in-repo stub set;
            ``"raid"`` for the RAID held-out (requires the
            ``raid-bench`` PyPI package, gated by the ``[bench]``
            extra).
        n: Optional cap on the number of samples returned. ``None``
            means all available.
        domain: Optional domain filter (``news``, ``blog``,
            ``academic``, ``business``). Applied after loading.

    Returns:
        A list of :class:`BenchSample` instances. Order is stable
        (insertion order in ``_samples.json`` for ``"bundled"``;
        whatever the upstream loader returns for ``"raid"``).

    Raises:
        NotImplementedError: ``source="raid"`` is requested but the
            ``raid-bench`` package isn't importable. We deliberately
            don't fall back to the bundled set — silent degradation
            would conceal the missing dep and yield meaningless
            "RAID" numbers in ``docs/benchmarks.md``.
    """
    if source == "bundled":
        samples = _load_bundled()
    elif source == "raid":
        samples = _load_raid()
    else:
        raise ValueError(f"unknown sample source: {source!r}")

    if domain is not None:
        samples = [s for s in samples if s.domain == domain]
    if n is not None:
        samples = samples[:n]
    return samples


def _load_bundled() -> list[BenchSample]:
    """Read the in-repo stub set."""
    payload = json.loads(DEFAULT_SAMPLES_JSON.read_text(encoding="utf-8"))
    return [
        BenchSample(
            id=row["id"],
            domain=row["domain"],
            scene=row["scene"],
            text=row["text"],
            source="bundled",
        )
        for row in payload["samples"]
    ]


def _load_raid() -> list[BenchSample]:
    """Load the RAID held-out via the ``raid-bench`` package.

    Not implemented at the v0.1 cut — we want this slot wired up
    so callers learn about it, but the actual mapping from
    ``raid-bench``'s schema to :class:`BenchSample` will land
    alongside the first GPU-equipped benchmark run that produces
    honest §7.1 numbers (see ``docs/benchmarks.md``). Until then,
    callers get a clear ``NotImplementedError`` rather than a
    silent fallback to the stub set.
    """
    try:
        import raid  # noqa: F401  (presence check only)
    except ImportError as exc:  # pragma: no cover — depends on optional extra
        raise NotImplementedError(
            "RAID loader requires the [bench] extra. "
            "Install with `pip install humanize-en[bench]`. "
            "Until the loader implementation lands, point the "
            "benchmark driver at source='bundled' for "
            "structure-only verification."
        ) from exc
    raise NotImplementedError(
        "raid-bench loader is not yet wired (plan-M8 follow-up). "
        "Use source='bundled' for now, or contribute the loader "
        "in tests/bench/_data.py::_load_raid."
    )
