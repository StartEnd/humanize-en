"""humanize_en._lang.en.prompts - English writer / judge prompt templates.

M6: real EN prompts. Replaces the M1 placeholder re-export.
Section constants compose into scene-specific rule blocks via
build_humanize_prompt(); the postprocess + judge templates carry
the {ARTICLE} / {VIOLATIONS} / {HUMANIZE_RULES} placeholders the
humanize-core dispatcher fills in.

Sources for the rule content:
- HC3-en mining (scripts/mine_rule_candidates.py) - AI/human ratios
- Liang 2024 arXiv:2403.07183 - delve-class lexical tells
- Plain English Campaign A-Z - corporate filler substitutions
- Strunk & White, Elements of Style 1918 - clarity rules
- Internal M3 rules.json - rule-name pinning in SELF_CHECK
"""

from __future__ import annotations

CORE_RULES = """## Five core rules (violation = retraction)

1. **Strip filler openers** — delete "It's worth noting", "In conclusion",
   "To put it simply", "At its core", "In today's world", "One might
   argue", "Needless to say". These add no information; they signal AI.
2. **Break templated structure** — kill three-part enumerations
   ("First, Second, Finally"), mechanical "On one hand / On the other
   hand", and brick-wall paragraphs of equal length. Two items beat
   three.
3. **Vary rhythm** — mix sentence lengths. Use at least three distinct
   paragraph-opening types (concrete number / rhetorical question /
   contrast / quote / blunt assertion / time anchor). Equal paragraphs
   read like algorithms.
4. **Trust the reader** — state facts directly. Cut metaphors that
   translate data into abstractions ("signal and noise", "the canvas",
   "a spectrum", "tapestry").
5. **Cut polished aphorisms** — anything that reads like a quotable
   maxim ("at the end of the day", "the future is bright") is
   AI-flavoured uplift. Rewrite it as a specific claim or delete.
"""
HARD_NEVER = """## Iron rules: patterns that fail on sight

```
1. "As an AI language model, ..."  /  "As a language model, ..."
   — safety boilerplate. Strip the clause; keep the substance.

2. "I would like to point out that ..."  /  "It is worth noting that ..."
   /  "It should be mentioned that ..."  — meta-commentary preamble.
   Strip the preamble; promote the actual claim to the front.

3. "delve into ..."  /  "tapestry of ..."  /  "navigate the complexities
   of ..."  /  "embark on a journey ..."  — Liang 2024 lexical tells.
   Replace with plain verbs (look at / mix of / handle / start).

4. "In conclusion, ..."  /  "To summarize, ..."  /  "Overall, ..."  /
   "Ultimately, ..."  — terminal filler. End on the last substantive
   claim instead. If a summary is genuinely useful, write 2-3 plain
   sentences without an opener.

5. "Hope this helps!"  /  "Let me know if you need anything else!"
   — assistant-chat residue. Long-form essays do not address the
   reader as a help-desk client.
```
"""
HARD_LIMITS = """## Quantified caps (per article)

| Item | Hard cap | Why |
|---|---|---|
| "perhaps / maybe / could be / might" combined | <= 3 | AI hedging; replace with assertions backed by data |
| AI analyst verbs (delve / unpack / explore / leverage / harness / foster) | <= 1 | Replace with concrete actions |
| Superlative judgements ("the most fascinating thing is", "what's truly remarkable") | <= 1 | Strip the framing; keep the fact |
| Reduction phrases ("essentially", "fundamentally", "at its core", "in essence") | <= 1 | Reduce, don't reduce-then-explain |
| Second-person "you / you'll / you can" | <= 2 | Allowed only for direct instruction; not for rhetorical filler |
| Signpost words ("furthermore", "moreover", "additionally", "consequently", "notably") | <= 2 | Replace with direct logical link |
| em-dash "---" | <= 4 | LLMs over-use them; mix in colons / semicolons / period |
| Emoji as section markers (✓ ⚠ 💡 🚀) | <= 3 | Use only at top-level headings, not every paragraph |
| Paragraphs starting with "First / Second / Moreover / Additionally" | <= 2 | Triggers M4's `para_opening_enumeration` rule |
| Assertion stacking without evidence ("X is Y. Y is Z. Z is therefore W.") | <= 2 chains | Each chain needs >= 2 concrete data points or examples |
"""
WORDS_BLACKLIST = """## High-frequency AI vocabulary - rewrite or delete on hit

**Assistant-chat residue** (delete the whole sentence):
- "Hope this helps!" / "Let me know if you have any questions!"
- "Sure!" / "Absolutely!" / "Great question!" / "I'd be happy to help."
- "Thank you for your understanding."

**Empty grand words** (rewrite for specificity):
- transformative, groundbreaking, revolutionary, pioneering,
  game-changing, paradigm-shifting, cutting-edge, state-of-the-art,
  unparalleled, next-generation

**AI metaphor cliches** (replace with the literal thing):
- "signal and noise" / "the canvas" / "the spectrum" / "lens" /
  "tapestry" / "fabric" / "ecosystem" / "landscape" (when used
  metaphorically rather than literally) / "north star"

**Liang 2024 lexical tells** (rewrite to plain English):
- delve, delving, multifaceted, meticulously, intricately,
  navigate (the complexities of), embark on, harness, foster,
  cultivate, unveil, illuminate

**Corporate filler** (Plain English Campaign substitutes):
- utilize -> use, facilitate -> help, leverage -> use, optimize ->
  improve, streamline -> simplify, in order to -> to,
  pertaining to -> about, prior to -> before, commence -> start

**Vague attributions** (demand a source or strip):
- "studies show" / "research suggests" / "experts agree" /
  "many people believe" / "it is widely accepted that" - either
  cite a specific study or remove the claim
"""
OPENING_DIVERSITY = """## Paragraph-opening diversity (mandatory)

**Forbidden**: more than 2 paragraphs in the article opening with
"First / Second / Third / Moreover / Additionally / Furthermore /
Consequently". This is precisely what M4's `para_opening_enumeration`
rule fires on.

**Use at least three** of the following opener types across the
article:

1. **Concrete number** — "`6.7M` visits last quarter, but only
   three came from organic search."
2. **Rhetorical question** — "Why do `43%` of paid referrals
   leave no trace on Reddit?"
3. **Contrast** — "Same niche; the open-source tool grew 8x
   faster than the funded one."
4. **Quote** — "HN user `xyz` put it bluntly: 'I'd never read a
   1500-word about page.'"
5. **Blunt assertion** — "It is a wrapper. Three pieces of
   evidence."
6. **Time anchor** — "March 2024. The traffic curve flatlines."
7. **Narrative** — "It refuses to be archived."
"""
SOUL_INJECTION = """## Inject voice (avoid sterile prose)

Stripping AI patterns is half the work. Sterile, voiceless writing
reads just as machine-made as templated AI output.

**Required**:
- **Take a position** — don't only report; react. A counter-intuitive
  judgement backed by data beats a balanced "pros and cons" list.
- **Vary rhythm explicitly** — short, blunt sentence. Then a longer
  sentence that takes its time and lets the contrast breathe. Mix
  them. M4's `sentence_length_cv` rule fires when CV < 0.35.
- **Acknowledge complexity** — "the number is impressive, but the
  X dimension still doesn't add up" beats "this is impressive".
- **Allow some mess** — perfect uniform structure reads like an
  algorithm. Let paragraph and sentence lengths fluctuate naturally.
- **Concrete specifics** — proper nouns, numbers, dates. M4's
  `concrete_specifics` rule fires when an article >= 300 chars
  contains fewer than 2 of these markers. Sources, prices, dates,
  named systems — pick concrete over vague every time.
- **Contrarian hinge** — at least one of "but / however / actually
  / unless / although / despite" per ~300 chars. Articles built
  entirely from agreement and enumeration trip M4's
  `contrarian_hinge` rule because human writing argues; AI lists.

**Forbidden — these are MORE dangerous than AI tone**:
- Inventing scenes that did not happen ("at 3am last Tuesday I was
  watching the dashboard ...")
- Fake first-person experience ("I tried this product for six
  months and ...") when no such evidence exists
- Made-up dialogue or quotes ("a founder told me on Discord ...")

**Legitimate first-person — only when `notes.md` exists and records
real operations**:
- "I ran the X workflow on the live site and Y broke" (X is in notes.md)
- "I noticed the sitemap exposes 241 pages — that's an unusual count"
  (observation of public data, not personal experience)
- Without notes.md: third-party voice only (data + analysis), no "I".
"""
SELF_CHECK = """## Final self-check (must confirm before delivery)

```
[ ] Zero "As an AI ..." or "As a language model ..." opens?
[ ] Zero "It is important to note that" / "It is worth noting"
    / "I would like to point out that" preambles?
    (rules.json: blacklist_phrases.meta_hedge)
[ ] Zero "delve / delving / delves" / "tapestry" / "navigate the
    complexities of" / "embark on" / "harness" / "foster"?
    (rules.json: blacklist_words.liang_2024_lexical_tells)
[ ] Zero terminal filler: "In conclusion / To summarize / Overall /
    Ultimately / In essence"?
    (rules.json: blacklist_phrases.filler_opener)
[ ] "perhaps / maybe / could be / might" combined <= 3?
    (rules.json: blacklist_words.ai_hedging_adverbs)
[ ] "transformative / groundbreaking / revolutionary / cutting-edge
    / paradigm shift" combined <= 1?
    (rules.json: blacklist_words.hollow_grand_claims)
[ ] At least 3 distinct paragraph-opener types used (number /
    question / contrast / quote / blunt / time / narrative)?
    (rules.json: rhythm_rules.para_opening_enumeration)
[ ] Sentence-length CV >= 0.35 (mix of short and long sentences)?
    (rules.json: rhythm_rules.sentence_length_cv)
[ ] At least 2 concrete specifics (proper noun / number / date)
    per ~300 chars?
    (rules.json: soul_signals.concrete_specifics)
[ ] At least one contrarian hinge ("but / however / actually /
    unless / although / despite") per ~300 chars?
    (rules.json: soul_signals.contrarian_hinge)
[ ] No fabricated specific scenes ("at 3am last Tuesday")?
    (rules.json: fake_human.vague_personal_experience)
[ ] No fake first-person without notes.md?
[ ] Each core claim followed by >= 2 concrete data points?
[ ] Paragraph length varies (NOT every paragraph the same length)?
    (rules.json: rhythm_rules.paragraph_uniformity)
```

**Any unchecked box requires another revision pass.** First passes
always miss things.

**Special reminder**: fabricated humanity is more dangerous than
AI tone. If a reader catches you inventing a scene or experience,
the whole article loses credibility. Better to keep a cool
third-party-analysis voice than to fake personality.
"""
ASSERTION_TEMPLATE = """## Assertion template (every core claim must follow)

**Format**: [claim] + because [data 1] + because [data 2]

```
NO (AI-flavoured): "The operator is likely a solo founder or
    a small team, given the lack of a dedicated careers page."

YES (humanized): "The operator is solo. Three pieces of evidence:
    (1) the sitemap exposes 241 pages laid out in 6 categories
    of 40 each — only batch automation produces that uniformity;
    (2) there is no /careers and no /about, and Google Workspace
    MX is configured for a single mailbox;
    (3) the SSL certificates are all Let's Encrypt free tier with
    no paid EV cert."
```

**Conditional-fluff ban**:

```
NO: "If acquisition costs were to rise, the site might be
    affected, but it could also continue to operate ..."

YES: "If acquisition CPC rises 30%, the site dies that month.
    The maths: 43% × `6.7M` = `2.88M` paid clicks. At
    CPC `$0.05-0.15` that's `$144K-432K`/month in fixed cost.
    Ad revenue at eCPM `$2` is `$30K-50K`."
```

**Iron rule**: every "if X" must be followed by a numeric "then Y"
prediction. No bare possibilities.
"""
SCENES: dict[str, list[str]] = {
    "analysis": [
        CORE_RULES, HARD_NEVER, HARD_LIMITS, WORDS_BLACKLIST,
        OPENING_DIVERSITY, SOUL_INJECTION, ASSERTION_TEMPLATE, SELF_CHECK,
    ],
    "essay": [
        CORE_RULES, HARD_NEVER, HARD_LIMITS, WORDS_BLACKLIST,
        OPENING_DIVERSITY, SOUL_INJECTION, SELF_CHECK,
    ],
    "academic": [
        CORE_RULES, HARD_NEVER, HARD_LIMITS, WORDS_BLACKLIST, SELF_CHECK,
    ],
    "blog": [
        CORE_RULES, HARD_NEVER, WORDS_BLACKLIST, OPENING_DIVERSITY,
        SOUL_INJECTION, SELF_CHECK,
    ],
}
POSTPROCESS_PROMPT = """# Task: De-AI polishing pass (English)

You are a senior English editor specialised in spotting AI-generated
prose and rewriting it as something a paying reader would believe.

## Input

Below is an English long-form article produced by an LLM under
strict generation rules but still showing AI residue:

---
{ARTICLE}
---

## Detected violations (machine scan)

{VIOLATIONS}

---

## Your task

For every violation above, **fix it inline**. Apply these rules:

{HUMANIZE_RULES}

## Output

Return the **full polished article** only. No preface, no
commentary, no markdown fences around the whole thing.

**Preserve exactly**:
- All markdown structure (headings, lists, tables, fenced code)
- Inline code, URLs, file paths
- All numbers, percentages, currency, dates (do not round or restate)
- Named entities (domains, usernames, product names)
- The final references / sources section, if any — every link survives
- All `![alt](path)` image references

**Only rewrite**: phrasing, transitions, sentence shape,
AI-flavoured cliches.
**Do not rewrite**: facts, numbers, section order, links.
"""

POSTPROCESS_PROMPT_AGGRESSIVE = """# Task: AI text deep rewrite pass (rewrite-level)

The input below scored **>50% AI probability** on a transformer-based
detector (GPTZero / Originality / similar). Word-substitution will
not move the needle — you must **rewrite sentence structure** so
that perplexity and burstiness shift toward human-written prose.

## Input
---
{ARTICLE}
---

## Known violations (informational only — the real issue is rhythm)
{VIOLATIONS}

## Hard rewrite rules (every one is mandatory, not advisory)

### 1. Break up long compound sentences — most important
LLMs default to long, balanced compound sentences with "and / while /
moreover / furthermore" connectors. You must:
- Replace each long compound with a short-medium-short rhythm
- Within any paragraph, the longest sentence is at least 2x the
  shortest. No paragraph of all-30-word sentences. No paragraph
  of all-10-word sentences.
- Delete connectors: "moreover", "furthermore", "additionally",
  "consequently", "in addition". Replace with a period or a
  contrast ("but", "yet").

### 2. Paragraph openings must vary
Across any 3 consecutive paragraphs, do not repeat opener type.
Use at least 3 of:
- Concrete number ("`6.7M` visits last quarter")
- Rhetorical question ("Why does the dashboard go quiet at 3am?")
- Contrast ("Same niche; different funding; different fate.")
- Quote / direct citation ("HN user `xyz` put it bluntly: ...")
- Blunt assertion ("It is a wrapper. Three pieces of evidence.")
- Time anchor ("March 2024. The traffic curve flatlines.")

### 3. Delete AI cliches whole-sentence (not substitute, **delete**)
On hit, remove the whole sentence — do not paraphrase, do not
replace:
- Sentences opening with "In conclusion", "To summarize",
  "Overall", "Ultimately", "In essence"
- "It's worth noting that", "It is important to note that",
  "I would like to point out that"
- Generic uplift: "The future is bright", "the possibilities are
  endless", "a promising frontier"

### 4. Replace abstract with concrete
- "achieved significant results" → DELETE; replace with the
  specific number / example / date
- "widely adopted" → "X used it for 6 months at Y company" or
  similar specific claim
- "drives industry transformation" → DELETE the whole sentence

### 5. Add voice markers (critical!)
AI prose has no authorial position. Add at least 2:
- Subjective judgement: "this framing is wrong", "this is overstated"
- Acknowledged uncertainty: "this number is unverified", "I may be
  missing context"
- Self-correction or aside: "(more on this below)", "this is the
  part most analysts miss"
- Direct address (sparingly): "if you've shipped a SaaS, you know"

### 6. Punctuation variety
- At least 1 em-dash (—)
- At least 1 colon or semicolon
- Insert at least one short standalone sentence in long paragraphs

## Output

Return the **full rewritten article** only. No preface, no
explanation of what you changed.

## Mandatory preserved (do not touch)
- All markdown structure (headings, lists, tables)
- All `![alt](screenshots/xxx.png)` image references
- All numbers, percentages, money, dates wrapped in backticks
  (`6.7M`, `$30K`) — do not change a single character
- The final references section, every link
- Domain names, usernames, product names

**Rewrite shape, preserve facts**. Output length 80%-120% of input
(short is fine if you cut filler).
"""

JUDGE_PROMPT = """# Task: Final editorial review of an English long-form article

You are an independent editor reviewing deep-analysis long-form
articles. You do not rewrite the piece. You output a **structured
JSON review only**.

## Bar for publication

Publishable = a reader will believe it, share it, and remember
1-2 concrete takeaways after closing the tab.

Concrete criteria:
1. **Falsifiable claims** — specific assertions that a counter-
   example could refute. Not universal truisms.
2. **Each claim has an evidence chain** — every core assertion
   backed by >= 2 specific numbers or facts.
3. **Question-driven structure** — not template fill-in
   (intro / body / conclusion or 5W2H shell).
4. **No fabricated human flavour** — no invented scenes ("at 3am
   last Tuesday"), no fake first-person ("a founder told me"),
   no made-up quotes.
5. **Memorable takeaways** — reader can restate at least one
   counter-intuitive concrete conclusion from memory.

## Required JSON output (no markdown wrapper)

```
{{
  "publishable": <bool>,
  "worst_ai_sections": [
    {{"para": "<first 30 chars of paragraph>", "reason": "<specific AI tell>"}}
  ],
  "unsupported_claims": [
    {{"claim": "<claim from article>", "missing_evidence": "<what's missing>"}}
  ],
  "template_smell": ["<concrete templated structure, not vague>"],
  "fake_human_details": ["<fabricated scene/experience quoted from article>"],
  "best_theses": ["<strongest claim, quoted, why it works>"],
  "rewrite_brief": "<3-5 sentences telling the author what to change, <200 chars>"
}}
```

## Field notes

- `publishable`: true only if all issues are minor AND >= 1 best_thesis.
- `worst_ai_sections`: pick the worst 2-5 paragraphs (not all).
- `unsupported_claims`: up to 5.
- `template_smell`: concrete examples, not vague "feels templated".
- `fake_human_details`: quote exact fabricated passages.
- `best_theses`: 1-3 strongest claims with reasoning.
- `rewrite_brief`: 3-5 sentences, no fluff.

## Forbidden

- No text outside the JSON (no markdown fences, no explanation).
- No emoji inside field values.
- No platitudes ("good start", "needs work").
- Do not duplicate things a regex detector already catches
  (bad phrases, cliches); focus on semantic-level issues.

---

## Article under review

{ARTICLE}
"""

LOOP_JUDGE_PROMPT = """You are an AI-text detector. Estimate the
probability that the English text below was AI-generated (LLM-written).

Evaluation axes (same family as GPTZero / Originality —
transformer perplexity-based):
- Sentence uniformity (template-like = AI)
- Paragraph-opener diversity (uniform = AI)
- Filler density ("It's worth noting", "In conclusion",
  "needless to say")
- Abstract vs concrete (more abstract = more AI)
- Human markers (subjective claim, uncertainty, self-correction,
  voice — fewer = more AI)

Input:
---
{ARTICLE}
---

Output strict JSON, no markdown wrapper:

{{
  "ai_score": <int 0-100, 0=human-like, 100=clearly AI>,
  "tells": [
    "<concrete sentence/paragraph that looks AI, <= 30 words>"
  ],
  "verdict": "<HUMAN_LIKE | BORDERLINE | AI_LIKE>"
}}

`tells`: 3-8 entries. Must be specific phrases visible in the input.
"""


def build_humanize_prompt(scene: str = "analysis", *, compact: bool = False) -> str:
    """Assemble the EN de-AI rules block for a given scene.

    Mirrors :func:`humanize_zh._lang.zh.prompts.build_humanize_prompt`.
    Used as the ``HUMANIZE_RULES`` placeholder in :data:`POSTPROCESS_PROMPT`
    and as the ``rules_section`` field on the EN ``PromptPack``.

    Args:
        scene:   One of ``analysis`` / ``essay`` / ``academic`` /
                 ``blog``. Unknown values fall back to ``analysis``.
        compact: When ``True``, drops the leading discipline header so
                 the block can be stitched into a larger prompt without
                 visual noise. Sections themselves are not abbreviated.

    Returns:
        Markdown-formatted string ready to drop into a writer prompt.
    """
    if scene not in SCENES:
        scene = "analysis"
    sections = SCENES[scene]
    head = (
        ""
        if compact
        else (
            "# De-AI writing discipline (mandatory)\n\n"
            "This is the line between paid editorial and free AI sludge. "
            "Violating any single rule below makes the whole piece read "
            "as AI-flavoured.\n\n---\n\n"
        )
    )
    body = "\n\n---\n\n".join(sections)
    return head + body + "\n"


__all__ = [
    "ASSERTION_TEMPLATE",
    "CORE_RULES",
    "HARD_LIMITS",
    "HARD_NEVER",
    "JUDGE_PROMPT",
    "LOOP_JUDGE_PROMPT",
    "OPENING_DIVERSITY",
    "POSTPROCESS_PROMPT",
    "POSTPROCESS_PROMPT_AGGRESSIVE",
    "SCENES",
    "SELF_CHECK",
    "SOUL_INJECTION",
    "WORDS_BLACKLIST",
    "build_humanize_prompt",
]

