# humanize-en

**Pre-alpha (M8 — Binoculars wrapper).** English AI-text humanizer
plugin for [`humanize-core`](../humanize-core/). Sibling to
[`humanize-zh`](../humanize-zh/). Roadmap and prior-art survey in
[`docs/plan.md`](docs/plan.md).

Status by milestone:

| ID | Layer                                | Status |
|----|--------------------------------------|--------|
| M1 | Scaffold + protocol contracts        | ✅ |
| M2 | n-gram engine (HC3-en, LR-calibrated) | ✅ |
| M3 | Lexical + phrase rules                | ✅ |
| M4 | Structural / rhythm / soul-signals    | ✅ |
| M5 | Replacement table (102 pairs, 6 buckets) | ✅ |
| M6 | English prompt pack                   | ✅ |
| M7 | Strength knob (low/medium/high)       | ✅ |
| M8 | Optional Binoculars perplexity wrapper | ✅ |

## What this is (when finished, ~M8)

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

## Usage (planned API, ~M6)

```python
from humanize_en import score, postprocess_humanize, llm

llm.use("openai", api_key="sk-...")

text = "It's worth noting that this is a transformative paradigm shift..."
s = score(text)
print(s.total, s.level)   # 60.0 HIGH (likely AI-generated)

polished = postprocess_humanize(text, strength="medium")
print(polished)           # "This is a major change..."
```

The CLI mirrors humanize-zh's interface:

```bash
humanize en detect file.md
humanize en polish file.md --strength high
humanize en judge file.md
```

Through M8, the detector / replacement / prompt layers are wired
into the `LanguageProfile`. End-to-end `postprocess_humanize` and
`judge` work via `humanize_core` — the convenience top-level
re-exports (`humanize_en.score`, `humanize_en.postprocess_humanize`,
etc.) and the dedicated `humanize-en` CLI are still pending.

## Optional: Binoculars perplexity signal (M8)

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

- Our humanizer is rule-driven + LLM-polished. It is **not** designed
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

MIT. See [`LICENSE`](LICENSE) (added with first PyPI release).

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
