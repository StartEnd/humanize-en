"""humanize_en._lang.en — the bundled English LanguageProfile.

The plugin's four components live here:

- :mod:`humanize_en._lang.en.detector` — rule-based detector
- :mod:`humanize_en._lang.en.ngram` — n-gram statistical detector
- :mod:`humanize_en._lang.en.replacements` — deterministic-cleanup pairs
- :mod:`humanize_en._lang.en.prompts` — writer / judge / loop-judge templates

and :mod:`humanize_en._lang.en.profile` assembles them into the
``en_profile`` :class:`~humanize_core.protocols.LanguageProfile`
singleton that ``humanize_en/__init__.py`` auto-registers.

At M1 every component is a minimal stub — see the per-module
docstrings for what they currently do (and don't).
"""
