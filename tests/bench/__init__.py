"""``humanize-en`` plan-M8 benchmark suite.

Three gates from ``docs/plan.md`` §7:

* §7.1 — Binoculars score drop  (primary gate, requires Falcon-7B)
* §7.2 — BERTScore-F1 ≥ 0.85   (meaning preservation, requires bert-score)
* §7.3 — Flesch-Kincaid ±2     (readability, stdlib only)

Plus structure tests that always run regardless of optional deps:
the *pipeline* must wire up correctly even without GPU/model weights.

Optional deps: install via ``pip install humanize-en[bench]`` plus
the upstream Binoculars install (see ``humanize_en.perplexity``).
Without them, the gate tests skip-mark elegantly and the
:mod:`scripts.run_benchmarks` driver writes the structural rows
to ``docs/benchmarks.md`` with ``skipped`` placeholders.
"""

from __future__ import annotations
