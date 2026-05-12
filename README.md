# humanize-en

**Alpha (M10 — PyPI release prep).** English AI-text humanizer
plugin for [`humanize-core`](../humanize-core/). Sibling to
[`humanize-zh`](../humanize-zh/). Roadmap and prior-art survey in
[`docs/plan.md`](docs/plan.md).

Status by milestone (numbering matches `docs/plan.md` §10):

| ID  | Layer                                          | Status |
|-----|------------------------------------------------|--------|
| M1  | Scaffold + protocol contracts                  | ✅ |
| M2  | n-gram engine (HC3-en, LR-calibrated)          | ✅ |
| M3  | Detector v1 — lexical + phrase rules           | ✅ |
| M4  | Detector v2 — structural / rhythm / soul-signals | ✅ |
| M5  | Replacements (102 pairs) + prompts (writer/judge/loop) | ✅ |
| M6  | Strength knob (low / medium / high)            | ✅ |
| M7  | Optional Binoculars perplexity wrapper         | ✅ |
| M9  | Examples + auto-generated rules docs           | ✅ |
| M8  | Benchmark suite + §7 gates (structure + skip-marked numbers) | ✅ structure / 🟡 numbers pending GPU run |
| M10 | CLI + LICENSE + TestPyPI release prep          | ✅ |
| M11 | HTMX web UI for EN (multi-language template kit) | 📝 planned (see `docs/plan.md` §M11) |

## What this is (when finished, ~M10)

An **interpretable, open-source English AI-text humanizer** that:

1. **Surfaces** AI tells via a transparent rule + n-gram detector
   (every flag tied to a named rule with a fix).
2. **Rewrites** AI tells through an LLM polish pass driven by the
   flag list.
3. **Measures itself honestly** against independent SOTA detectors
   (Binoculars / Fast-DetectGPT) and reports the score *drop* it
   induces — not "AI detection accuracy" claims.

## What this is **not**

- **Not a SOTA AI detector.** For raw detection accuracy on
  English text, use [Binoculars (ICML 2024)][binoculars] or
  [Fast-DetectGPT (ICLR 2024)][fast-detectgpt]. They achieve
  ~0.99 AUC zero-shot; our rule + n-gram pipeline caps around
  0.80 by design. We exist to provide *actionable, named flags*
  that drive a humanizer, not to compete on a single number.
- **Not a "bypass detection" tool.** All AI detectors degrade
  under adversarial attack (Dugan et al., [RAID][raid], ACL 2024).
  We do not promise our output evades any specific detector, and
  we do not endorse using this package for academic dishonesty.
  OpenAI deprecated their own AI Classifier in July 2023 citing
  exactly this issue — *every* detector has the same problem.
- **Not a paraphraser.** [DIPPER][dipper] (Krishna et al., NeurIPS
  2023) is the canonical 11B paraphrase-attack model. We target
  named-pattern correction at the sentence level; DIPPER targets
  full reformulation. They are complementary, not competing.

## Installation

```bash
# default — rules + ngram + LLM polish via humanize-core
pip install humanize-en

# add OpenAI / Anthropic SDKs for LLM polish
pip install "humanize-en[openai]"
pip install "humanize-en[anthropic]"

# add the FastAPI web UI (served by humanize-core)
pip install "humanize-en[ui]"

# heavy: add a Binoculars perplexity-tier signal (~14 GB Falcon-7B
# weights, downloaded on first use). Best on English; off by default.
pip install "humanize-en[perplexity]"
pip install "git+https://github.com/ahans30/Binoculars"

# evaluation suite (raid-bench + BERTScore). Local benchmarking only.
pip install "humanize-en[bench]"
```

Local development install (recommended while pre-alpha):

```bash
cd Humanize/humanize-en
uv sync --extra dev   # picks up ../humanize-core via [tool.uv.sources]
make test
```

## Usage

```python
from humanize_en import (
    score, ngram_score, combined_score,
    postprocess_humanize, judge, iterative_polish,
    Strength, llm,
)

# Configure an LLM provider (pick one):
llm.autodetect()                                # discover from env vars
# llm.use("openai", api_key="sk-...")
# llm.use_openai_compat(name="deepseek", base_url="...", api_key="...",
#                       model="deepseek-chat")

text = "It is important to note that this paradigm shift will leverage cutting-edge AI..."

# 1) Detection (no LLM required) ─────────────────────────────────────
s = score(text)
print(s.total, s.level)                         # 23.0  LOW (looks human-written)
for v in s.violations:
    print(f"  {v.rule}: {v.sample!r}  (+{v.score})")

# 2) One-shot polish ─────────────────────────────────────────────────
polished, after, before = postprocess_humanize(text, scene="analysis")
print(polished)

# 3) Custom-strength polish (low / medium / high) ───────────────────
from humanize_en import build_humanize_postprocess_prompt
prompt = build_humanize_postprocess_prompt(
    text, violations=s.violations, scene="analysis", strength=Strength.HIGH,
)
polished_aggressive = llm.get_active().complete(prompt).text

# 4) Closed-loop polish — writer/judge ping-pong until score ≤ 30 ───
result = iterative_polish(text, rounds=3, target_ai_score=30,
                          writer_provider="openai", judge_provider="anthropic")
print(result.rounds[-1].polished)

# 5) Final LLM review ────────────────────────────────────────────────
verdict = judge(polished, writer_provider="openai", judge_provider="anthropic")
print(verdict["publishable"], verdict.get("rewrite_brief"))
```

`postprocess_humanize` / `judge` / `iterative_polish` are all
EN-defaulted thin shims over `humanize_core` — see
`humanize_en/{postprocess,judge,iterative}.py` for the exact
forwarding contract.

### CLI quickstart

Installing the package wires up a `humanize-en` console script
that mirrors `humanize-zh` (so any pipeline tooling you have for
the ZH plugin works against EN by renaming the binary):

```bash
# Detection only — no LLM key required.
humanize-en detect article.md
humanize-en detect article.md --json     # machine-readable

# LLM polish (strips AI tells). Auto-detects a provider from env vars
# (OPENAI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, ...).
humanize-en polish article.md -o polished.md
humanize-en polish article.md --scene academic --provider anthropic

# LLM final-review verdict (writer ≠ judge, collusion check enforced).
humanize-en judge  article.md --writer openai --judge anthropic
humanize-en judge  article.md --json -o review.json

# Surface auto-detected providers.
humanize-en providers

# Launch the multi-language JSON API server (humanize-core[ui]).
# Today this is JSON-only — the HTMX web UI for EN is plan-M11.
# Exposes /api/detect /api/polish /api/judge /api/providers /api/languages.
humanize-en ui --port 8765
```

The CLI auto-loads `./.env` and `~/.humanize-en.env` (skipped if
`HUMANIZE_EN_NO_DOTENV=1` is set) so `OPENAI_API_KEY=…` in a
project-local `.env` Just Works. `python -m humanize_en.cli`
is the equivalent entry point if you prefer to skip the script
stub.

See [`examples/`](examples/) for four self-contained ~50-line
scripts (detect-only, polish, iterative, prompt-injection),
[`docs/rules.md`](docs/rules.md) for the auto-generated rule
reference (26 rules across 6 categories, with descriptions,
weights, and sample patterns), and [`docs/benchmarks.md`](docs/benchmarks.md)
for the §7 gate harness (structure verified; honest numbers
require a Falcon-7B-equipped run — see plan-M8 status above).

## Optional: Binoculars perplexity signal (M7)

For benchmark and gate-check use, we ship a thin wrapper around the
upstream [Binoculars][binoculars] detector (Hans et al., ICML 2024 —
Falcon-7B base vs Falcon-7B-instruct perplexity ratio, BSD-3 licence).
Binoculars achieves ~0.99 zero-shot AUC on un-attacked English; our
HC3-trained rule + n-gram pipeline caps around 0.80 by design. The
wrapper exists so the §7.1 *humanization gate* can measure
Binoculars-score *drop* after polish, not as a replacement detector.

```bash
pip install "humanize-en[perplexity]"
pip install "git+https://github.com/ahans30/Binoculars"
```

```python
from humanize_en.perplexity import is_available, score

if is_available():
    # Lower = more AI-like (paper polarity; we never invert).
    raw = score(article_text)
```

Important properties:

- **Lazy import.** Importing `humanize_en.perplexity` never touches
  `transformers` / `torch` / `binoculars`. Model load happens on the
  first `score()` call (~30 s GPU, several minutes CPU; ~14 GB of
  Falcon-7B weights downloaded once).
- **Singleton.** Repeated `score()` calls reuse one detector.
  Tests / batch jobs that need isolation should construct
  `BinocularsScorer` directly.
- **Typed missing-dep error.** Without the extras installed,
  `score()` raises `PerplexityNotInstalledError` (a subclass of
  `ImportError`) with the install commands in the message.
- **Polarity matches the paper, not our other detectors.** Lower
  numbers indicate AI. We resist normalising this so benchmark
  numbers can be compared verbatim with published results.

## Limitations

This section is non-negotiable for v0.1 release. Verbatim:

### Detection

- Our rule + n-gram detector targets *interpretable* AI tells. For
  raw detection accuracy on un-attacked text, dedicated zero-shot
  detectors like Binoculars (ICML 2024) outperform us by ~10 AUC
  points. We recommend running both in series for high-stakes use.
- All AI detectors — including ours — degrade sharply under
  adversarial attack (Dugan et al., ACL 2024 "[RAID][raid]" paper).
  No detector should be used as sole evidence for academic or
  professional sanctions. OpenAI deprecated their own [AI Classifier][openai-classifier]
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
- Reducing AI tells is not the same as "being a good writer". Use
  this tool as an editorial assistant, not a writing replacement.

## License

MIT. See [`LICENSE`](LICENSE).

## References

See [`docs/plan.md` §13](docs/plan.md) for the complete reference
list. The most-cited works:

- Hans et al. **Binoculars**, ICML 2024. [arXiv:2401.12070][binoculars]
- Bao et al. **Fast-DetectGPT**, ICLR 2024. [arXiv:2310.05130][fast-detectgpt]
- Dugan et al. **RAID**, ACL 2024. [arXiv:2405.07940][raid]
- Krishna et al. **DIPPER**, NeurIPS 2023. [arXiv:2303.13408][dipper]
- Hello-SimpleAI, **HC3** corpus (CC-BY-SA-4.0). [HuggingFace][hc3]

[binoculars]: https://arxiv.org/abs/2401.12070
[fast-detectgpt]: https://arxiv.org/abs/2310.05130
[raid]: https://arxiv.org/abs/2405.07940
[dipper]: https://arxiv.org/abs/2303.13408
[hc3]: https://huggingface.co/datasets/Hello-SimpleAI/HC3
[openai-classifier]: https://openai.com/index/new-ai-classifier-for-indicating-ai-written-text/
