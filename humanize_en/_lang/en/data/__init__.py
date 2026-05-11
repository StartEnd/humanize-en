"""humanize_en._lang.en.data — JSON / gzipped data files for the EN plugin.

Files (planned, see ``docs/plan.md``):

- ``rules.json`` (M3-M4)
- ``replacements.json`` (M5)
- ``ngram_freq_en.json.gz`` (M2)
- ``lr_coef_en.json`` (M2)
- ``lr_coef_by_domain/{news,academic,casual}.json`` (M4)

The package contains only ``__init__.py`` and small stub JSON files
at M1. The frequency table is the largest planned artifact (~3 MB
gzipped) and ships in the wheel via the ``[tool.hatch.build]``
force-include rule in ``pyproject.toml``.
"""
