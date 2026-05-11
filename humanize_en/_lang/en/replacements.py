"""humanize_en._lang.en.replacements — English replacement table.

**M1 status: stub.** Loader uses the same JSON contract as the ZH
replacements (``data/replacements.json`` with ``_order`` + bucketed
``[old, new]`` pairs) so the M5 milestone only adds data, not code.

Planned content (M5, ~80 pairs across 6 buckets):

- ``safety_disclaimer`` — "It's important to note that " → ""
- ``corporate_filler`` — leverage → use, utilize → use, in order to → to
- ``empty_grand`` — transformative → useful, revolutionary → new
- ``meta_hedge`` — arguably → ∅, crucially → ∅
- ``delve_class`` — delve into → look at, tapestry → mix
- ``filler_opener`` — In conclusion, → ∅

Sources cited in ``_meta.attribution``:

- Plain English Campaign "A to Z of alternative words" (public domain,
  http://www.plainenglish.co.uk/files/alternative.pdf)
- Strunk & White, *Elements of Style* 1918 edition (public domain)
- Selected entries from Humano (MIT-licenced,
  https://github.com/khushiyant/humano)

Ordering rules (same as ZH, see ``humanize_zh._lang.zh.replacements``):

1. Buckets apply in the order declared by ``replacements._order``.
2. Within each bucket, pairs sort by ``len(old)`` descending so longer
   phrases match before shorter substrings.

Failure mode: on JSON parse / IO failure, log and return an empty
tuple so the polish pipeline degrades to a no-op rather than crashing.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

REPLACEMENTS_PATH = Path(__file__).parent / "data" / "replacements.json"


@lru_cache(maxsize=1)
def _load_replacements() -> tuple[tuple[str, str], ...]:
    """Load deterministic replacement pairs from ``replacements.json``.

    At M1 the file is a near-empty stub (only ``_meta`` + ``_order``);
    this returns an empty tuple. Real pairs land in M5.
    """
    try:
        data = json.loads(REPLACEMENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error("[humanize_en] cannot load %s: %s", REPLACEMENTS_PATH, e)
        return ()
    section = data.get("replacements") or {}
    order = section.get("_order") or [
        k for k in section if not k.startswith("_") and isinstance(section[k], list)
    ]
    pairs: list[tuple[str, str]] = []
    for bucket in order:
        items = section.get(bucket)
        if not isinstance(items, list):
            continue
        bucket_pairs: list[tuple[str, str]] = []
        for entry in items:
            if (
                isinstance(entry, list)
                and len(entry) == 2
                and isinstance(entry[0], str)
                and isinstance(entry[1], str)
            ):
                bucket_pairs.append((entry[0], entry[1]))
        bucket_pairs.sort(key=lambda p: -len(p[0]))
        pairs.extend(bucket_pairs)
    return tuple(pairs)


# ─── Protocol adapter ─────────────────────────────────────────────────────


class EnReplacementsTable:
    """:class:`~humanize_core.protocols.ReplacementsTable` adapter."""

    code: str = "en"

    def ordered_pairs(self) -> tuple[tuple[str, str], ...]:
        return _load_replacements()


# Singleton consumed by ``humanize_en._lang.en.profile``.
en_replacements: EnReplacementsTable = EnReplacementsTable()


__all__ = [
    "EnReplacementsTable",
    "REPLACEMENTS_PATH",
    "_load_replacements",
    "en_replacements",
]
