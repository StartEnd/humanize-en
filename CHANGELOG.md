# Changelog

All notable changes to `humanize-en` are documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Pre-1.0 alpha tags use the form `0.x.y-aN` where `N` increments per
milestone (M1, M2, ...).

## [Unreleased]

### M3 — Lexical + phrase rules (in progress)

- Added ``humanize_en/_lang/en/data/rules.json`` (v0.3.0) with
  **16 concrete rules** across two buckets:
  - ``blacklist_words`` (7 rules, ~70 patterns):
    ``abstract_possessives``, ``ai_hedging_adverbs``,
    ``ai_categorical_nouns``, ``liang_2024_lexical_tells``,
    ``corporate_filler``, ``ai_amplifiers``,
    ``hollow_grand_claims``.
  - ``blacklist_phrases`` (9 rules, ~80 patterns):
    ``meta_hedge``, ``structural_summary``,
    ``structural_transitions``, ``ai_safety_disclaimer``,
    ``reflexive_helpers``, ``exemplar_padding``,
    ``generic_caveat``, ``enumeration_padding``,
    ``important_to_X``.
  - ``structural_rules`` / ``rhythm_rules`` / ``fake_human`` /
    ``soul_signals`` — scaffolded with ``_desc`` markers for M4.
- Added mining script ``scripts/mine_rule_candidates.py`` that reuses
  the engine tokeniser, computes per-word AI/human ratios and per-
  document 2-/3-gram ratios on the shipped HC3-en cache, and
  writes TSV candidate tables to ``scripts/_mining/`` (gitignored).
  Every concrete M3 rule is backed by either a measured HC3 ratio
  or a cited published prior-art list.
- Rewrote ``humanize_en/_lang/en/detector.py`` from the M1 stub into
  the real implementation:
  - ``_load_rules()`` lru-caches the JSON; fail-open with a
    ``0.0.0-unloadable`` marker if the file is absent / malformed.
  - ``_strip_codeblocks()`` — fenced and inline code stripped before
    matching so a tutorial discussing ``utilize()`` isn't penalised.
  - ``_build_word_regex`` / ``_build_phrase_regex`` — compile one
    case-insensitive alternation per rule with apostrophe-aware
    boundaries (``body's`` matches as a word; internal whitespace
    in phrase patterns is flexibilised to ``\s+``).
  - ``_apply_threshold_ladder`` — monotonic (soft, hard) ladder
    identical to humanize-zh's so cross-language weight tuning
    transfers.
  - ``score()`` — length-normalised total (divisor = max(1, len/3000))
    capped at 100. Returns a ``Score`` with per-rule ``Violation``
    entries that carry a sample snippet for prompt-pack injection.
  - ``EnDetector.version`` now reads from
    ``rules.json::_meta.version`` at construction.
- **Bug fix: tokeniser ignored HC3's literal ``\n`` escape artefacts.**
  HC3-en ships answers with 2413 occurrences of the two-character
  string ``\n`` (backslash + letter ``n``, not real newlines), a
  legacy double-encoding in the raw dump. Our tokeniser emitted bogus
  tokens like ``nthe``, ``nin``, ``noverall`` that polluted the freq
  table and leaked into the n-gram features. Added ``_normalize()``
  in ``_ngram_engine.py`` that replaces the literal escapes with real
  newlines before tokenisation — used by both build-time and runtime.
  **Effect**: re-running ``scripts/build_ngram_data.py`` with the
  fix lifted held-out test AUC from **0.8597 → 0.8847** (+0.025).
- Added 24 detector tests (``tests/test_detector.py``): rule-data
  shape, threshold-ladder parametrised cases, regex builders (word
  boundaries + apostrophes + case-insensitivity + whitespace flex),
  per-rule firing behaviour, code-block stripping, AI-vs-natural
  discrimination, and length-normalisation invariants.
- Updated ``tests/test_protocols.py``: flipped M1 "stub" assertion
  to M3 "clean text → zero score with populated stats".
- Total test count: **54** (16 protocol + 14 ngram + 24 detector),
  90% coverage, ruff/mypy clean.

### M2 — HC3-en n-gram engine (in progress)

- Added stdlib-only feature engine
  (`humanize_en/_lang/en/data/_ngram_engine.py`, ~390 lines): bigram
  perplexity with unigram backoff, burstiness CV, paragraph entropy
  uniformity, transition-phrase density, sentence-length stats,
  word MATTR, and comma/punctuation density. Each function is
  independently testable; runtime imports zero third-party deps.
- Added build script (`scripts/build_ngram_data.py`) that downloads
  HC3-en via `huggingface_hub` (raw `all.jsonl`, ~74 MB), counts
  unigrams + bigrams on the human side (57 638 answers, 6.9 M
  tokens), trims to top 500 k bigrams (preserves 85.1 % of mass),
  fits sklearn LogisticRegression on a balanced 10 k human / 10 k AI
  subset with stratified 80/20 split, and writes:
  - `humanize_en/_lang/en/data/ngram_freq_en.json.gz` (3.04 MB)
  - `humanize_en/_lang/en/data/lr_coef_en.json` (~3 KB)
- Replaced the M1 stub `humanize_en/_lang/en/ngram.py` with a real
  loader that combines the engine + LR. Honours the
  `NgramEngine` protocol contract: `available` is `True` only when
  both calibration files load; `score()` always returns a valid
  `NgramScore` (never raises).
- Added `[build-data]` extra (`huggingface-hub`, `scikit-learn`,
  `numpy`) — declared *outside* runtime deps so wheel users never
  pull HF / sklearn.
- Added 14 new tests (`tests/test_ngram.py`): calibration provenance,
  per-feature engine sanity, end-to-end scoring, and direction-only
  discrimination between AI-tell-laden and natural-prose paragraphs.
- Updated `tests/test_protocols.py`: flipped M1 "engine unavailable"
  assertion to M2 "engine available with shipped calibration"; added
  AUC ≥ 0.75 gate and corpus-id assertion.

**Calibration provenance** (recorded in `lr_coef_en.json::_meta`):
- corpus: `Hello-SimpleAI/HC3` revision `4d0ff18143b5`
- features: 12 (see `FEATURE_ORDER` in build script)
- model: `sklearn.LogisticRegression(C=1.0)`, seed=42
- training set: 8 000 human + 8 000 AI (stratified train split)
- **held-out test AUC = 0.8847** ✅ (M2 gate: ≥ 0.75) — was 0.8597
  before the M3 ``\\n`` tokeniser fix; see M3 bug-fix note.

**Calibration limitations** (documented for honesty):
- HC3-en human answers skew toward formal QA (Reddit ELI5, finance,
  medicine, wiki). Single-text scoring on out-of-distribution input
  (e.g. personal narrative) shows higher false-positive rates than
  the corpus-level AUC suggests. Direction-of-effect remains correct;
  M4 (per-domain rules) and M8 (RAID validation) will quantify and
  improve OOD generalisation.

### M1 — Scaffold

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
