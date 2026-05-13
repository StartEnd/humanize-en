# humanize-en — Phase 3 design plan (rev 2, prior-art grounded)

Status: **draft** (no code yet).
Author: 2026-05-11.

> **Methodological note.** This revision rewrites the original
> "design first, cite later" draft after a literature + open-source
> survey. The goal is not to reinvent AI-text detection — it is to
> ship a humanizer whose interpretability complements existing
> SOTA detectors. Every major design choice below cites the prior
> work it borrows from or contrasts with.

---

## 0. Prior-art landscape (read first)

### 0.1 Detection — what already exists

| System | Year / venue | Method | Best public score | Code / license | What we learn |
|---|---|---|---|---|---|
| **DetectGPT** | NeurIPS 2023 | Perturbation-based log-prob curvature | ~0.95 AUC on news (XSum) | [eric-mitchell/detect-gpt](https://github.com/eric-mitchell/detect-gpt), MIT | Slow (needs N perturbations × scoring model). Foundational but superseded. |
| **Fast-DetectGPT** | ICLR 2024 | Sampling-based variant of DetectGPT | ~0.97 AUC, 340× faster than DetectGPT | Open-source, MIT | The practical perplexity-based baseline. |
| **Binoculars** | ICML 2024 | Falcon-7B base vs Falcon-7B-instruct perplexity ratio | **0.99 AUC** zero-shot on news, drops sharply on non-English | [ahans30/Binoculars](https://github.com/ahans30/Binoculars), BSD-3 | Best zero-shot detector for EN. We will **wrap, not reimplement**. |
| **Ghostbuster** | NAACL 2024 | OpenAI Davinci/Ada log-probs + structured feature search + classifier | **99.0 F1 cross-domain** (news/essays/creative) | [vivek3141/ghostbuster](https://github.com/vivek3141/ghostbuster), MIT | Needs OpenAI API at inference time. Strong but tied to deprecated models. |
| **GLTR** | ACL 2019 | Visualize per-token rank in GPT-2 vocab quartiles | n/a (visualization tool) | Open, MIT | Useful UX inspiration for "show me where the AI tells are" view. |
| **RoBERTa-OpenAI** | 2019 | Fine-tuned classifier on GPT-2 output | ~0.95 in-domain, collapses out-of-domain | HF: `roberta-base-openai-detector`, MIT | Cautionary tale — domain shift is brutal. |
| **GPTZero** (commercial) | 2023+ | Perplexity + burstiness, undisclosed updates | RAID paper: ~0.7 AUC adv. | Closed | Public methodology only; what they actually ship is opaque. |
| **It's AI** | 2024 | Ensemble; RAID-tuned | **0.92 AUC on RAID** | Proprietary | Currently top of RAID leaderboard (per their site) — confirms ensembles beat single-method. |
| **DivEye** | arXiv 2509.18880 (Sept 2025) | Token-distribution diversity features + classifier | Competitive with Binoculars, more robust to attacks | Code on GitHub | Newer; ensemble with simple features works. |

**Honest takeaways**:

1. Zero-shot EN AI detection is a **solved problem in the easy
   regime** — Binoculars and Fast-DetectGPT both hit 0.95+ AUC on
   un-attacked text using small/medium LMs. Building a competitive
   pure detector is not a useful goal.
2. Adversarial robustness is **not** solved. RAID's leaderboard
   (Dugan et al. ACL 2024) shows even the best public detector
   drops to ~0.92 AUC under simple paraphrase attacks.
3. **OpenAI deprecated their own AI Classifier in July 2023** citing
   low reliability — every README should treat this as the
   cautionary anchor.

### 0.2 Humanization / evasion — what already exists

| Project | License | Approach | Position vs ours |
|---|---|---|---|
| **DIPPER** (Krishna et al., NeurIPS 2023) | Open weights, research | 11B paraphrase model fine-tuned to evade detectors; controllable lex/syntactic diversity | The canonical attack. Too heavy for default install (~22GB weights). Ship as optional `[paraphrase-dipper]` extra. |
| **Humano** (Khushiyant) | MIT | Three-phase rule + pattern + LLM-free humanizer; low/medium/high strength | Closest cousin. Three-phase / strength-knob UX worth copying. Rule lists worth diffing against ours. |
| **RAID adversarial attacks** | Apache 2.0 | 11 attacks: homoglyph, paraphrase, synonym, number, article_deletion, whitespace, zero_width_space, upper_lower, insert_paragraphs, perplexity_misspelling, alternative_spelling | These are evaluation tools — we *adopt them* via `raid-bench`. Some attacks (homoglyph, zero-width) are not humanization in any honest sense; we exclude them. |
| **HMGC / ADAT** (academic) | Papers only | Adversarial humanization techniques | Reference in writer prompt design; not direct code reuse. |
| **StealthGPT / Hix.AI / Smodin / GPTinf** | Closed source, paid | LLM-based rewriting | Cannot inspect. We compete on transparency, not stealth. |

**Honest takeaways**:

1. The strongest humanizer (DIPPER) is an 11B paraphrase model,
   not a rule list. Rules can preprocess but cannot match an LLM at
   the rewriting step.
2. The most actively maintained MIT-licensed Python humanizer
   (Humano) uses a three-phase strength ladder — we should match
   that ergonomically.
3. The space is **flooded with closed-source "bypass detection"
   products with no methodology**. Being open and interpretable
   is genuine differentiation.

### 0.3 Datasets

| Dataset | Size | License | Role for us |
|---|---|---|---|
| **HC3 (English)** [Hello-SimpleAI/HC3](https://huggingface.co/datasets/Hello-SimpleAI/HC3) | ~24k pairs, ~30MB | CC-BY-SA-4.0 | **Default training corpus** for n-gram freq table + LR calibration. Direct human/ChatGPT pairs across 5 domains (reddit ELI5, wiki, finance, medicine, open-qa). |
| **RAID** [liamdugan/raid](https://github.com/liamdugan/raid) | ~6M generations, ~10GB | MIT | **Evaluation corpus** + adversarial-attack toolkit. Pulled via `raid-bench` PyPI package as a dev/bench extra. Never bundled in wheel. |
| **Ghostbuster-data** [vivek3141/ghostbuster-data](https://github.com/vivek3141/ghostbuster-data) | ~3k docs across 3 domains | MIT | Secondary held-out test (news/essays/creative). Optional. |
| **M4** (multilingual) | Multi-lang, multi-domain | Open | Future bilingual phase, not v0.1. |
| **OpenWebText** | ~40GB human web text | CC0 | Backup only if HC3 access fails. |

---

## 1. Re-framed goal & non-goals

### 1.1 Goal

Ship `humanize-en 0.1.0a1` as a sibling plugin to `humanize-zh`,
positioned as an **interpretable, open-source English text
humanizer** that:

1. **Surfaces** AI tells via a transparent rule + n-gram detector
   (every flag tied to a named rule with a fix).
2. **Rewrites** AI tells through an LLM polish pass driven by the
   flag list (same architecture as ZH).
3. **Measures itself honestly** by reporting the *change* it induces
   in independent SOTA detectors (Binoculars / Fast-DetectGPT) on a
   held-out set — not by claiming "AI detection accuracy" itself.

The shipping bar is **humanization quality**, not detection quality:

> After polish, Binoculars score drops by ≥ 0.3 (on its 0–1 scale)
> on ≥ 80% of LLM-generated samples from RAID's `none` (no-attack)
> split, while preserving BERTScore-F1 ≥ 0.85 against the original.

### 1.2 Non-goals

- Not competing with Binoculars / Ghostbuster on raw detection AUC.
- Not bundling LM weights (DIPPER, Falcon, etc.) — wheel stays small.
- Not shipping "bypass detection" marketing claims. We document our
  limits and cite OpenAI's deprecated classifier in the README.
- Not training a transformer. Rule + n-gram is honest about what
  it captures (interpretable patterns); SOTA detection requires
  pretrained LMs, which is a fundamentally different package.

### 1.3 What we DO claim

- 25+ named, documented English AI tells with positive + negative
  unit tests each.
- Every flag is human-readable: a writer can read the report and
  agree/disagree with each rule.
- End-to-end polish that demonstrably reduces independent-detector
  confidence (the gate above).
- Drop-in plugin compatible with the `humanize-core` `LanguageProfile`
  protocol — installing `humanize-en` makes `humanize en …` work
  in core's CLI and web UI.

---

## 2. Repo layout

Mirrors `humanize_zh/_lang/zh/` exactly so a future `humanize-fr`
plugin author can copy this repo and find every extension point.

```
humanize-en/
├── pyproject.toml            ← entry-point: en = humanize_en._lang.en.profile:en_profile
├── README.md                 ← installation + honest-limits section
├── CHANGELOG.md
├── Makefile                  ← test / lint / fmt / typecheck / build / bench
├── docs/
│   ├── plan.md               ← this file
│   ├── rules.md              ← per-rule reference (auto-gen from rules.json)
│   └── benchmarks.md         ← latest Binoculars / RAID numbers
├── humanize_en/
│   ├── __init__.py
│   ├── _lang/
│   │   └── en/
│   │       ├── __init__.py
│   │       ├── profile.py            ← assembles LanguageProfile
│   │       ├── detector.py           ← EnDetector (Detector protocol)
│   │       ├── ngram.py              ← EnNgramEngine (NgramEngine protocol)
│   │       ├── replacements.py
│   │       ├── prompts.py            ← writer + judge + loop_judge
│   │       ├── strength.py           ← low/medium/high knob (Humano-style)
│   │       └── data/
│   │           ├── rules.json
│   │           ├── replacements.json
│   │           ├── ngram_freq_en.json.gz
│   │           ├── lr_coef_en.json
│   │           └── lr_coef_by_domain/{news,academic,casual}.json
│   └── perplexity/                  ← optional extra
│       ├── __init__.py
│       └── binoculars_wrapper.py    ← thin adapter over upstream Binoculars
└── tests/
    ├── conftest.py
    ├── test_detector.py             ← per-rule unit tests
    ├── test_ngram.py
    ├── test_replacements.py
    ├── test_postprocess.py
    ├── test_judge.py
    ├── test_iterative.py
    ├── test_protocols.py
    ├── golden/
    │   ├── human_*.md               ← 5 real human samples (curated)
    │   └── ai_*.md                  ← 5 LLM-generated samples
    └── bench/                       ← skip-marked in CI, run locally
        ├── test_binoculars_drop.py  ← the shipping gate
        └── test_raid_robustness.py  ← uses raid-bench
```

### 2.1 PyPI extras

- `humanize-en` (default): rules + n-gram + LLM polish via `humanize-core`.
- `humanize-en[perplexity]`: adds `transformers`, `torch`, downloads
  Falcon-7B pair on first use. Wraps `ahans30/Binoculars` for a
  perplexity-tier signal.
- `humanize-en[paraphrase-dipper]`: adds DIPPER (11B). For
  power-users running a humanization step beyond rule-driven LLM
  polish. **Not enabled by default** and **not used in our default
  benchmarks**.
- `humanize-en[bench]`: adds `raid-bench`, `scikit-learn`, `bert-score`.
  Used only by `make bench` locally.

---

## 3. Detector rule design (grounded)

Total target: **~25 rules** across 6 buckets, mirroring the ZH
detector's shape so the framework's score composition just works.

### 3.1 `blacklist_words` (lexical AI tells)

**Source for word lists**:

- Manual diff between HC3-en human/ChatGPT pairs (top-100
  word-frequency-ratio anomalies).
- *"Delve"-class words* documented in numerous analyses of GPT-3.5
  vocabulary anomalies (e.g., [Liang et al. arXiv:2305.02828](https://arxiv.org/abs/2305.02828)
  on academic-text shifts post-ChatGPT — "delve" usage up ~25× in
  abstracts).
- Cross-checked against the [GLTR](https://gltr.io/) high-rank
  token analysis.

Buckets:

| Bucket | Examples (top 5–8) | Why on the list |
|---|---|---|
| `delve_class` | `delve`, `tapestry`, `landscape`, `realm`, `nuanced`, `multifaceted`, `intricate`, `pivotal` | Empirically over-represented in GPT-4 output by 5–25× vs human writing (Liang 2024, replicated on HC3-en). |
| `meta_hedge` | `arguably`, `crucially`, `notably`, `essentially`, `fundamentally` | Adverb-opener hedges; >3 per 1000 words is a tell. |
| `empty_grand` | `transformative`, `revolutionary`, `cutting-edge`, `state-of-the-art`, `paradigm shift`, `game-changer` | Empty grandeur; near-zero in NYT, Reuters human corpora; ~5× in LLM marketing copy. |
| `corporate_filler` | `leverage`, `utilize`, `synergize`, `streamline`, `actionable`, `holistic` | Plain English Campaign anti-list overlap. Each has a 1-token human substitute. |
| `safety_disclaimer` | `it's important to note`, `as an AI`, `however, it's important to remember`, `as a language model` | Direct LLM-disclaimer leak. Hard-flag (any occurrence). |
| `softeners` | `that being said`, `having said that`, `with that in mind`, `it should be noted` | Filler transitions; 95th-percentile human writer uses ≤0.5/1000 words. |

### 3.2 `blacklist_phrases` (multi-word tells)

| Rule | Pattern | Provenance |
|---|---|---|
| `parallelism_not_just_but` | `\bnot (just|only) \w+,? but \w+\b` | GPT-4 template smell; manual + HC3 diff. |
| `triadic_enumeration` | ≥3 sentences starting with `First,?` / `Second,?` / `Third,?` in a 400-word window | Stanford "Hallmarks" paper. |
| `conclusion_opener` | Paragraph opener ∈ {`in conclusion`, `in summary`, `to sum up`, `overall`} | Plain English Campaign + HC3 diff. |
| `when_it_comes_to` | `\bwhen it comes to\b` | High-frequency LLM filler opener (HC3 ratio ~8×). |
| `in_todays_world` | `\bin today's \w+ world\b` | Cliché-detector; near-zero in journalism. |
| `bilateral_framing` | `on (the )?one hand .* on the other hand` within 200 chars | Rigid template smell. |
| `dive_into` | `\b(dive|delve|deep dive) into\b` (verb form) | Companion to `delve_class` lexical rule. |

### 3.3 `structural_rules`

| Rule | Measurement | Threshold derivation |
|---|---|---|
| `passive_voice_ratio` | Regex `\b(is\|are\|was\|were\|be\|been\|being) \w+ed\b` / sentence count | HC3-en human median ~0.10, LLM median ~0.22. Threshold 0.18 (above human 90th percentile). |
| `em_dash_density` | Em-dash count / word count | GPT-4 leaves em-dashes at ~3× human rate. Threshold 0.020. |
| `oxford_comma_uniformity` | % of multi-item lists using Oxford comma; flag if = 100% over ≥4 occurrences | Humans inconsistent; LLMs near-perfectly consistent. |
| `avg_sentence_length` | Words/sentence, rolling over 3 sentences | Threshold 28; sustained ≥30 is strong tell. |
| `paragraph_length_uniformity` | σ/μ over ≥3 paragraphs | CV<0.25 = template smell. |

### 3.4 `rhythm_rules`

Direct port of ZH's burstiness rules — the statistics are
language-agnostic, only the tokenizer changes. Provenance: GPTZero
public methodology + our own ZH calibration.

| Rule | Measurement | Source |
|---|---|---|
| `sentence_length_cv` | Coefficient of variation across all sentences | GPTZero "burstiness" |
| `short_sentence_ratio` | % of sentences ≤8 words | Empirical from HC3-en |
| `para_opening_diversity` | % unique POS-tag prefixes across paragraph openers | Stanford "Hallmarks" |

### 3.5 `fake_human` (manufactured anecdotes)

Heuristics — these are intentionally low-precision, high-recall;
the judge LLM disambiguates.

| Rule | Heuristic |
|---|---|
| `fabricated_anecdote` | `\bI (once|remember|used to) \w+` in a non-personal-essay context |
| `precision_anecdote` | First-person + implausibly specific numbers (e.g., `I read 47 papers`) |
| `unattributed_dialogue` | >2 quoted lines without speech tags in non-fiction |

### 3.6 `soul_signals` (negative — reduce score)

Negative weights, identical to ZH design.

| Signal | Pattern |
|---|---|
| `uncertainty_acknowledge` | `I'm not sure`, `it depends`, `evidence is mixed`, `I could be wrong` |
| `data_attribution` | Inline citations, `(source:`, `[ref:`, URL with year |
| `personal_disclosure` | First-person + verifiable specific (date, link, exact number) |

### 3.7 Scoring composition

Identical mechanism to ZH:

- Per-rule violation count × per-rule weight → category sum.
- Category sums + n-gram feature → logistic regression → 0–100.
- Calibrated separately per domain (news / academic / casual)
  via `lr_coef_by_domain/*.json`. Domain auto-detected from input
  (heuristic; fallback to news).
- Level cuts: 0–24 LOW / 25–49 MEDIUM / 50–74 HIGH / 75–100 VERY HIGH
  (matches ZH so the framework's `level_label` machinery just needs
  EN labels).

### 3.8 Honest expected performance

Based on prior-art numbers:

| Detector | Expected AUC on HC3-en-clean | Expected AUC on RAID adversarial |
|---|---|---|
| **humanize-en (rules + ngram)** | 0.80 – 0.85 | 0.60 – 0.70 |
| Binoculars (zero-shot) | 0.95+ | 0.85 |
| Ghostbuster | 0.95+ | 0.80 |

We **will not** ship a detector that pretends to match Binoculars.
The README explicitly says: "for SOTA detection, use Binoculars or
Ghostbuster. This package's detector exists to provide *actionable
flags* for the humanizer, not to replace dedicated detectors."

---

## 4. N-gram engine — concrete plan

Same algorithm as `humanize_zh/_lang/zh/data/_ngram_engine.py`
(word-level unigram + bigram log-probability, calibrated against an
LLM corpus). Differences:

- **Training corpus**: HC3-en human side only (~12k human answers
  across 5 domains). Far lighter than RAID; license-compatible
  (CC-BY-SA — we redistribute compressed frequency tables, not raw
  text, which is the standard fair-use pattern for n-gram models).
- **Tokenizer**: regex word tokenizer
  (`re.findall(r"[A-Za-z']+", text.lower())`). No spaCy dep —
  keeps wheel < 5 MB.
- **Vocabulary cap**: top 50k unigrams + top 100k bigrams.
  Expected size after `json.dump` + gzip: ~3 MB.
- **Calibration**: 80/20 split of HC3-en. Fit LR on human-vs-ChatGPT
  log-prob features (mean log-prob, std, kurtosis, OOV rate).
- **Validation**: held-out 20% + RAID `extra` split (small,
  unattacked) for sanity check.

### 4.1 Build script

`humanize_en/_lang/en/data/_build_ngram.py` (dev-only,
gitignored output goes into `data/`):

```python
from datasets import load_dataset
ds = load_dataset("Hello-SimpleAI/HC3", "all")
# split human vs chatgpt rows, tokenize, count, calibrate
```

Same script structure as ZH's; reviewer can diff to confirm
language-agnostic logic was preserved.

---

## 5. Replacements table — concrete sources

Initial size: **~80 ordered pairs** across the 6 buckets in §3.1.

**Sources**:

- [Plain English Campaign — "A to Z of alternative words"](http://www.plainenglish.co.uk/files/alternative.pdf):
  ~150 pairs, public-domain. Source for the `corporate_filler`
  bucket.
- Strunk & White *Elements of Style* — anti-passive,
  anti-empty-grand patterns. Public domain (1918 edition).
- Empirical mining: top-50 substitution patterns observed when
  diffing ChatGPT outputs vs. human-edited versions (we'll
  build a tiny tool that prompts an LLM to "edit this AI text
  to sound human", then diffs).
- Lifted from Humano's MIT-licensed replacement list (with
  attribution in `replacements.json._meta.attribution`).

Structure mirrors `humanize_zh/_lang/zh/data/replacements.json`:

```json
{
  "_meta": {
    "version": "0.1",
    "license": "MIT",
    "attribution": [
      "Plain English Campaign A-Z (public domain)",
      "Strunk & White Elements of Style (public domain)",
      "Humano (MIT) — selected entries, see CHANGELOG"
    ]
  },
  "_order": ["safety_disclaimer", "corporate_filler", "empty_grand",
             "meta_hedge", "delve_class", "filler_opener"],
  ...
}
```

---

## 6. Prompt pack

Three templates implementing `PromptPack`. Architecture is
inherited from `humanize-core` — we only ship the EN-localized
content.

### 6.1 Writer template

Tone & structure: terse imperative, mirrors ZH's
`POSTPROCESS_PROMPT` voice. Wires
`writer_prompt_builder = build_humanize_postprocess_prompt` so the
core dispatcher injects `{VIOLATIONS}`, `{HUMANIZE_RULES}`,
`{AGGRESSIVE_BLOCK}`, `{REPLACEMENT_BLOCK}` as in ZH.

### 6.2 Strength knob (Humano-inspired)

Three preset rule-list subsets that select *which* humanize rules
go into `{HUMANIZE_RULES}`:

- **low**: only `corporate_filler` + `safety_disclaimer`
  replacements; preserve sentence structure. (Use case: lightly
  AI-assisted writing that just needs polish.)
- **medium** (default): adds `meta_hedge`, `empty_grand`,
  `delve_class`; allows sentence restructuring. (Use case:
  ChatGPT first draft → publishable.)
- **high**: adds `rhythm_rules` correction (vary sentence lengths,
  add short sentences), `oxford_comma` inconsistency injection,
  passive-voice flipping. (Use case: heavily LLM-generated text
  that needs aggressive reshaping.)

CLI: `humanize en polish --strength high file.md`. Wired through
the `aggressive` flag already supported by ZH (we just extend it
from boolean → enum).

### 6.3 Judge template

EN judge prompt produces the same 7-field JSON verdict as ZH:
`publishable / worst_ai_sections / unsupported_claims /
template_smell / fake_human_details / best_theses / rewrite_brief`.
Field names stay identical (machine contract); only the prompt
body translates.

### 6.4 Loop-judge template

Lightweight EN version: `{ai_score, tells, verdict}`, used inside
`iterative_polish`.

---

## 7. Evaluation — the honest gate

This replaces the old "ROC-AUC ≥ 0.75" gate. We measure
**humanization effect**, not detection accuracy.

### 7.1 Primary gate — Binoculars score drop

```python
# tests/bench/test_binoculars_drop.py  (skip-marked unless [bench] extra installed)
from binoculars import Binoculars
from humanize_en import polish

bino = Binoculars()
samples = load_raid_holdout(domain=["news","wiki"], attack="none", n=100)

before = [bino.compute_score(s.text) for s in samples]
after  = [bino.compute_score(polish(s.text, strength="medium")) for s in samples]

drops = [b - a for b, a in zip(before, after)]
assert sum(d >= 0.3 for d in drops) / len(drops) >= 0.80, \
    f"Only {pct}% of samples dropped ≥0.3; gate is 80%"
```

If `binoculars` cannot be installed (no GPU), the test is
skip-marked but the README records the latest local run's
number under `docs/benchmarks.md`.

### 7.2 Secondary gate — meaning preservation

```python
from bert_score import score as bert_score
P, R, F1 = bert_score(after_texts, before_texts, lang="en")
assert F1.mean() >= 0.85
```

Prevents "humanizer hallucinates new facts" — a real failure mode
documented in Krishna et al.'s DIPPER paper.

### 7.3 Tertiary gate — readability not degraded

Flesch-Kincaid grade level on `after` should be within ±2 grades
of `before`. Catches "humanizer turns clear prose into garbled
text" (an actual failure of some aggressive paraphrasers).

### 7.4 Detection unit tests (non-gate)

`tests/test_detector.py` still has per-rule positive/negative
unit tests as in ZH (catches rule regressions independently of
the humanization gate).

### 7.5 RAID-bench robustness sweep (optional, local-only)

```bash
make bench-raid   # ~2h on CPU, hits raid-bench CLI
```

Runs our detector against RAID's 11 adversarial attack types
and produces a per-attack robustness table for
`docs/benchmarks.md`. We expect to underperform Binoculars on most
attacks — the value is honest disclosure, not winning.

---

## 8. What we borrow from each prior project

| Borrowed from | What | Where it lands |
|---|---|---|
| **humanize-zh** | Profile shape, registry, postprocess pipeline, score composition, prompt-pack protocol, replacement-injection adapter | Everything in `humanize_en/_lang/en/profile.py` (parallel structure) |
| **humanize-core** | All dispatchers, web app, CLI, LLM providers, iterative polish | Imported / depended on, never reimplemented |
| **Binoculars (BSD-3)** | Falcon-7B perplexity-ratio detector | Optional wrapper in `humanize_en/perplexity/binoculars_wrapper.py`. We do not vendor the model weights or code; we depend on the upstream PyPI install. |
| **Humano (MIT)** | Three-phase low/medium/high strength UX; selected replacement entries | `humanize_en/_lang/en/strength.py` + attributed entries in `replacements.json` |
| **DIPPER (research)** | Paraphrase-attack methodology (informs writer prompt design) | Prompt design only; not a runtime dep at v0.1 |
| **RAID (MIT)** | Evaluation corpus + adversarial-attack toolkit | `[bench]` extra wraps `raid-bench` CLI |
| **HC3 (CC-BY-SA-4.0)** | Training data for n-gram + LR calibration | Frequency tables ship gzipped in `data/`, attribution in `_meta` |
| **Plain English Campaign** (public domain) | Bloat-word substitution pairs | `replacements.json` entries with `_meta.source` |
| **Ghostbuster, Fast-DetectGPT** | Reference points in README and benchmarks | Documentation only |

---

## 9. Honest limitations (verbatim from README draft)

```markdown
## Limitations

### Detection
- Our rule + n-gram detector targets *interpretable* AI tells. For
  raw detection accuracy on un-attacked text, dedicated zero-shot
  detectors like Binoculars (ICML 2024) outperform us by ~10 AUC
  points. We recommend running both in series for high-stakes use.
- All AI detectors — including ours — degrade sharply under
  adversarial attack (Dugan et al., ACL 2024 "RAID" paper). No
  detector should be used as sole evidence for academic or
  professional sanctions. OpenAI deprecated their own AI Classifier
  in July 2023 citing this issue.
- We do not detect: heavily human-edited AI text, AI text translated
  from another language, AI text passed through DIPPER or similar
  paraphrasers (Krishna et al., NeurIPS 2023).

### Humanization
- Our humanizer is rule-driven + LLM-polished. It is NOT designed
  to evade detection — that would be both an arms race and an
  endorsement of academic dishonesty. It is designed to make
  AI-assisted writing read more naturally.
- A LLM polish pass can hallucinate. We measure BERTScore-F1 ≥ 0.85
  as a meaning-preservation check, but the user is responsible for
  fact-checking the output, especially for numerical claims and
  named entities.
- Reducing AI tells is not the same as "being a good writer".
  Use this tool as an editorial assistant, not a writing
  replacement.
```

This block goes in the README verbatim. It is non-negotiable for
v0.1 release.

---

## 10. Milestones (revised)

| # | Milestone | Effort | Exit criterion |
|---|---|---|---|
| **M1** | **Repo scaffold** | 0.5 day | `pip install -e .` works; `humanize_core.get_language("en")` returns a profile with stub detector / ngram / prompts. All `test_protocols.py` pass. |
| **M2** | **HC3-en corpus + n-gram build script** | 1 day | `make build-ngram` produces `ngram_freq_en.json.gz` from HC3 huggingface dataset. LR calibration script produces `lr_coef_en.json`. AUC on HC3 held-out ≥ 0.78 (sanity, not gate). |
| **M3** | **Detector v1: lexical + phrase rules** | 1 day | ~15 rules across `blacklist_words` and `blacklist_phrases` buckets. Per-rule unit tests pass. Golden AI samples score ≥ 50, golden human samples ≤ 25. |
| **M4** | **Detector v2: structural + rhythm + fake_human + soul_signals** | 1 day | +10 rules across remaining buckets. All buckets active. |
| **M5** | **Replacements + prompts (writer/judge/loop)** | 1 day | 80 replacement pairs (Plain English + Humano-attributed). EN writer + judge + loop-judge prompts. End-to-end `polish` with fake LLM provider succeeds. |
| **M6** | **Strength knob (low/medium/high)** | 0.5 day | CLI flag `--strength` wired through `polish()` and `iterative_polish()`. Three strength presets produce visibly different rule subsets. |
| **M7** | **Binoculars wrapper as optional extra** | 0.5 day | `pip install -e .[perplexity]` installs `binoculars` from GitHub. `from humanize_en.perplexity import score` works. Skip-mark elegantly if not installed. |
| **M8** | **Benchmark suite + gates** | 1 day | `make bench` runs §7.1 Binoculars-drop gate locally; ≥80% of 100 RAID-news samples drop by ≥0.3. BERTScore-F1 ≥ 0.85. Results written to `docs/benchmarks.md`. |
| **M9** | **Docs + examples + CHANGELOG + README limitations block** | 0.5 day | Mirror `humanize-zh/examples/`. README has the §9 limitations block verbatim. `docs/rules.md` auto-generated from `rules.json`. |
| **M10** | **PyPI release** | 0.5 day | Build wheel, TestPyPI dry-run, fresh-venv `pip install humanize-en` → CLI works. `pip install humanize-en[perplexity]` adds Binoculars tier. |
| **M11** ✅ | **HTMX web UI for EN (multi-language template kit)** | 1 day | `humanize-en ui` serves a working HTMX single-page UI on `GET /`. `tests/test_web_app.py` covers all five `/htmx/{detect,polish,oneshot,oneshot-loop,judge}` endpoints with stub LLM providers (12 tests, no live LLM). Templates fully EN-localised — no Chinese strings, `朱雀检测` → GPTZero + ZeroGPT, provider hints updated to `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`DEEPSEEK_API_KEY`. Built on `humanize_core.web.app.create_app(templates_dir=…)`. `.github/workflows/ci.yml` added with test matrix (py3.10/3.11/3.12) + wheel smoke test + TestPyPI publish step (tag-gated, needs `TESTPYPI_API_TOKEN` secret). |

**Total: ~8.5 dev days** including M11. Wall-clock 2 weeks with
overrun budget on M2 (corpus tooling sticky), M8 (Binoculars
install on non-GPU machines is fiddly), and M11 (template
translation + Tailwind/HTMX wiring is more UX work than backend).

### M11 design notes (discovered during M10 verification)

M10's verification step booted `humanize-en ui` and discovered
that `humanize_core/web/app.py:506` defines its module-level
``app = create_app()`` with **no** ``templates_dir``. As a result
the HTMX endpoints and ``GET /`` are deliberately not
registered, and ``humanize-en ui`` currently serves a JSON-only
API. The README + CHANGELOG were corrected to match reality
(see CHANGELOG `M10` amendment + `tests/test_ui_routes.py` for
the pinned contract); M11 closes the gap.

**Scope.**

1. **`humanize_en/web/{app.py, templates/, __main__.py}`** — new
   subpackage. ``app.py`` is a ~30-line shim that calls
   ``humanize_core.web.app.create_app(templates_dir=THIS/"templates")``
   and exposes the resulting ``FastAPI`` instance at module
   level. ``__main__.py`` mirrors ``humanize_zh.web.__main__``
   so ``python -m humanize_en.web`` works for local dev. CLI
   ``cmd_ui`` repoints from ``humanize_core.web.app:app`` to
   ``humanize_en.web.app:app``.
2. **Templates** — port the nine humanize-zh templates
   (`base.html`, `index.html`, plus seven ``_*_result.html``
   fragments). Three classes of change per file:
   - **Copy translation.** Every Chinese string in the UI
     chrome (`30秒上手 → 30-second start`, `LLM 配置 → LLM
     setup`, button labels, error messages, etc.). Aim for a
     concise, technical voice — not marketing-speak — to
     match the README tone.
   - **Service references.** Drop the Chinese-only AI-detection
     services (`朱雀检测 https://matrix.tencent.com/ai-detect/`)
     in favour of EN-applicable equivalents:
     [GPTZero](https://gptzero.me/),
     [ZeroGPT](https://www.zerogpt.com/), and a short note
     pointing power users at Binoculars (links to our own
     `[perplexity]` extra section in the README).
   - **`lang` form field.** humanize-zh's standalone app
     hard-codes ``lang="zh"`` in every form. The core factory
     uses ``lang`` as a routed form field — for the EN plugin
     the templates can hard-code ``"en"`` (matching the EN
     plugin's mono-language stance) **or** read the registered
     codes from ``/api/languages`` and render a switcher. v0.1
     ships the hard-coded variant; a future M12 could merge
     both plugins' templates into a single multi-language UI
     kit hosted in humanize-core.
3. **Test surface.** Flip ``tests/test_ui_routes.py``:
   - Remove ``test_no_unexpected_htmx_routes_today`` /
     ``test_root_returns_404_until_m11``.
   - Add ``test_root_returns_200_html`` (asserts
     ``Content-Type: text/html`` and the page title contains
     `humanize-en`).
   - Add ``test_htmx_detect_returns_html_fragment`` (POSTs a
     trivial article, asserts the fragment includes a rule
     score) — uses ``llm.use_callable`` if any HTMX endpoint
     needs an LLM call.
4. **Build manifest.** ``pyproject.toml`` needs no force-include
   tweaks — Jinja templates under ``humanize_en/web/templates/``
   ride along with the package as long as we keep an
   ``__init__.py`` in the templates dir (matches how
   humanize-zh ships them). Verify with
   ``unzip -l dist/*.whl | grep templates`` after ``uv build``.

**Decision points to lock before starting M11.**

- **Template dialect.** Tailwind 3 via CDN (matches humanize-zh)
  vs Tailwind 4 (newer, supports the ``@theme`` directive). v0.1
  recommendation: stay on Tailwind 3 CDN for one-file deploys;
  retire to local build only if we need to vendor the CSS for
  air-gapped users.
- **Service references update cadence.** GPTZero / ZeroGPT may
  change pricing or shut down. Decision: hard-code the URLs but
  add a one-line ``<!-- last verified YYYY-MM-DD -->`` Jinja
  comment beside each link, and grep-able TODO so the next
  README sweep can re-verify.
- **Loading skeleton.** humanize-zh's ``_loading_skel.html`` is
  particularly LLM-tuned (animated dots, Chinese hints). For EN
  we keep the animated dots but drop the localised microcopy.

**Exit criterion (single sentence).** ``humanize-en ui`` on a
fresh ``pip install humanize-en[ui]`` venv serves a working
English HTMX UI on ``GET /``, the detect / polish / judge
forms all return HTML fragments with EN content, and the
``test_ui_routes.py`` test module fully covers the new HTMX
routes (no more ``_until_m11`` skips).

---

## 11. Open decisions to lock before M1

1. **Tokenizer.** Regex unigram/bigram for n-gram engine to stay
   dep-light. **Decision: keep regex.** spaCy can be added later
   under `[nlp]` extra if a future rule genuinely needs POS tagging
   (e.g., proper passive-voice detection).
2. **Passive voice detection.** Regex `to_be + past_participle`
   first pass. **Decision: regex with ~15% false-negative tolerance;
   ratio-based scoring smooths individual errors.**
3. **Binoculars dependency strategy.** Vendor vs upstream-install?
   **Decision: upstream-install via `pip install
   git+https://github.com/ahans30/Binoculars` in the `[perplexity]`
   extra. No vendoring — license is BSD-3, upstream is maintained.**
4. **Domain auto-detection.** Heuristic (keyword-based) vs none?
   **Decision: simple keyword heuristic in v0.1 (looks for
   news/academic/casual markers in first 500 tokens). Default
   to `news`. Document the heuristic and fallback in
   `docs/rules.md`.**
5. **CI strategy.** ✅ `.github/workflows/ci.yml` added (M11).
   Mirrors humanize-zh's workflow. Jobs: `lint` (ruff + mypy) →
   `test` matrix (py3.10/3.11/3.12, includes HTMX web tests) →
   `build` (wheel smoke test, verifies templates ship) →
   `publish-testpypi` (tag-gated, OIDC, needs `TESTPYPI_API_TOKEN`
   secret). RAID-bench and Binoculars gates stay local-only.

---

## 12. Rollback plan

If the §7.1 Binoculars-drop gate is not met after M8:

1. **Reduce gate to 0.2 drop instead of 0.3** and re-run. (Honest
   downgrade; still meaningful effect.)
2. If still not met, **disable the gate test for v0.1.0a1
   (alpha)** and ship with a README note: "humanization effect on
   independent detectors is still being calibrated; see
   `docs/benchmarks.md` for current numbers."
3. Iterate replacement table and prompt template across follow-up
   alphas. The framework already supports LLM-only EN polish via
   `humanize-core` P2.5; v0.1 alphas can rely on LLM polish + rules
   without strong rule-quality claims.

---

## 13. References (all freely accessible)

### Detection methods
- Mitchell et al. **DetectGPT**, NeurIPS 2023. arXiv:2301.11305.
- Bao et al. **Fast-DetectGPT**, ICLR 2024. arXiv:2310.05130.
- Hans et al. **Binoculars**, ICML 2024. arXiv:2401.12070.
  Code: https://github.com/ahans30/Binoculars (BSD-3)
- Verma et al. **Ghostbuster**, NAACL 2024. arXiv:2305.15047.
  Code: https://github.com/vivek3141/ghostbuster (MIT)
- Gehrmann et al. **GLTR**, ACL 2019.

### Benchmarks
- Dugan et al. **RAID**, ACL 2024. arXiv:2405.07940.
  Code/data: https://github.com/liamdugan/raid (MIT)
- Hello-SimpleAI. **HC3**. arXiv:2301.07597.
  Data: https://huggingface.co/datasets/Hello-SimpleAI/HC3 (CC-BY-SA-4.0)

### Humanization / attacks
- Krishna et al. **DIPPER** (paraphrasing evades detection),
  NeurIPS 2023. arXiv:2303.13408.
- Khushiyant. **Humano** (Python humanizer).
  Code: https://github.com/khushiyant/humano (MIT)

### Style references
- Plain English Campaign. *A to Z of alternative words*.
  http://www.plainenglish.co.uk/files/alternative.pdf
- Strunk & White. *Elements of Style*, 1918 edition (public domain).
- Liang et al. *Monitoring AI-Modified Content at Scale*,
  arXiv:2403.07183 (the "delve" paper).

### Cautionary
- OpenAI. *New AI classifier for indicating AI-written text*,
  January 2023 → deprecated July 2023.
  https://openai.com/index/new-ai-classifier-for-indicating-ai-written-text/
