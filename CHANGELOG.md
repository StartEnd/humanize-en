# Changelog

All notable changes to `humanize-en` are documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Pre-1.0 alpha tags use the form `0.x.y-aN` where `N` increments per
milestone (M1, M2, ...).

## [Unreleased]

### M1 — Scaffold (in progress)

- Initial repository scaffold under `Humanize/humanize-en/`.
- `pyproject.toml` declares the `humanize_core.languages` entry point
  pointing at `humanize_en._lang.en.profile:en_profile`.
- `humanize_en/__init__.py` auto-registers `en_profile` on import,
  mirroring the humanize-zh pattern.
- `humanize_en._lang.en` ships stub implementations of the four
  protocol components (Detector, NgramEngine, ReplacementsTable,
  PromptPack):
  - `detector.py`: rule-based detector skeleton; `score()` returns
    `total=0.0` with a `detector_status: "M1 stub"` marker in stats.
  - `ngram.py`: advertises `available=False` with a clear reason;
    real frequency table + LR calibration land in M2.
  - `replacements.py`: loader honours the same JSON contract as
    humanize-zh; `data/replacements.json` is an empty stub. Real
    pairs (~80) land in M5.
  - `prompts.py`: re-exports the framework-shipped EN placeholder
    prompts (`humanize_core.prompt.POSTPROCESS_PROMPT_EN` etc.) so
    `polish(text, lang="en")` works out of the box even at M1.
- `tests/test_protocols.py` (16 tests): contract validation for the
  assembled `LanguageProfile`, auto-registration, entry-point string,
  and honest stub status of each component.
- `docs/plan.md` (rev 2): prior-art-grounded Phase 3 plan with
  comparison tables of Binoculars / Ghostbuster / Fast-DetectGPT /
  RAID / Humano / DIPPER, evaluation gates, and milestone breakdown.
- `README.md` carries the verbatim limitations block agreed in
  `docs/plan.md` §9.

### Planned

- **M2** — HC3-en n-gram engine + LR calibration.
- **M3** — Lexical + phrase rules (~15 rules).
- **M4** — Structural + rhythm + fake_human + soul_signals rules.
- **M5** — Replacement table + EN writer/judge prompts.
- **M6** — Strength knob (low/medium/high, Humano-inspired).
- **M7** — Optional `[perplexity]` extra wrapping Binoculars.
- **M8** — Humanization gates (Binoculars-drop ≥0.3 + BERTScore-F1 ≥0.85).
- **M9** — Examples + auto-generated `docs/rules.md`.
- **M10** — PyPI release (`humanize-en 0.1.0a1`).
