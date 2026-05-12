# humanize-en detector rules

> Auto-generated from `humanize_en/_lang/en/data/rules.json` by `scripts/gen_rules_doc.py`. Do **not** edit by hand — your changes will be overwritten on the next regeneration. Edit the JSON instead.

## Rule-set metadata

| Field | Value |
|-------|-------|
| `version` | `0.4.0` |
| `milestone` | `M4-structural-rhythm-fake-soul` |
| `description` | humanize-en detector rules. M3 shipped 16 lexical + phrase rules. M4 adds 10 rules across structural (2) / rhythm (4) / fake_human (2) / soul_signals (2). |
| `sources` | - HC3-English mining (scripts/mine_rule_candidates.py) — AI/human ratio on 57k human + 27k ChatGPT answers<br>- Liang et al. arXiv:2403.07183 — 'The delve paper': post-RLHF lexical tells (delve, meticulous, realm, intricate, ...)<br>- Plain English Campaign A-Z of alternative words (public domain, http://www.plainenglish.co.uk/files/alternative.pdf) — corporate filler<br>- GPTZero public methodology — meta-comments and structural transitions<br>- Stanford 'Hallmarks of AI text' analyses — uniform sentence length + transition density |
| `scoring.weight_scale` | Hits scored as: count*weight*0.5 if count<=soft_threshold; count*weight if soft<count<=hard; (count-hard)*weight added on top once hard exceeded. |
| `scoring.normalization` | Total = min(100, sum(rule_scores) / max(1, len(text)/3000)). Length-normalised so a 12k-word essay isn't auto-flagged. |
| `scoring.bands` | 0-24 LOW; 25-49 MEDIUM; 50-74 HIGH; 75-100 VERY_HIGH (matches humanize_core._format.level_key). |

Total rules: **26** across 6 categories.

## Lexical AI tells (`blacklist_words`)

Single-word AI tells. Each rule sums hits across all patterns and applies the (soft, hard) threshold ladder.

_7 rule(s)._

#### `abstract_possessives`

ChatGPT loves abstract subject's-X constructions. HC3 ratio 23-100x. (e.g. 'the body's natural defense', 'the country's economy')

- **Weight**: `3`    **Soft threshold**: `2`    **Hard threshold**: `5`
- **Patterns** (15): `body's`, `earth's`, `person's`, `country's`, `people's`, `individual's`, … (**9 more**)

#### `ai_hedging_adverbs`

Vacuous hedge adverbs. HC3 ratio 7-12x. Each rare; many together = AI scaffolding.

- **Weight**: `2`    **Soft threshold**: `3`    **Hard threshold**: `8`
- **Patterns** (12): `carefully`, `ultimately`, `additionally`, `specifically`, `generally`, `typically`, … (**6 more**)

#### `ai_categorical_nouns`

Vague catch-all nouns used to enumerate without committing. HC3 ratio 6-11x.

- **Weight**: `2`    **Soft threshold**: `3`    **Hard threshold**: `8`
- **Patterns** (11): `variety`, `factors`, `challenges`, `goals`, `preferences`, `recommendations`, … (**5 more**)

#### `liang_2024_lexical_tells`

Post-RLHF lexical signature of GPT-4 / Claude (Liang 2024 arXiv:2403.07183 Tables 2-3). Rare in HC3 (early-2023 GPT-3.5) but diagnostic in current AI text.

- **Weight**: `4`    **Soft threshold**: `1`    **Hard threshold**: `3`
- **Patterns** (21): `delve`, `delves`, `delving`, `meticulous`, `meticulously`, `tapestry`, … (**15 more**)

#### `corporate_filler`

Corporate-speak verbs flagged by Plain English Campaign. Each is a one-word smell of management consulting.

- **Weight**: `3`    **Soft threshold**: `1`    **Hard threshold**: `2`
- **Patterns** (20): `utilize`, `utilizes`, `utilizing`, `utilization`, `facilitate`, `facilitates`, … (**14 more**)

#### `ai_amplifiers`

Vacuous strengtheners. Real writers cut these; ChatGPT sprinkles them. HC3 ratio 3-5x.

- **Weight**: `2`    **Soft threshold**: `3`    **Hard threshold**: `6`
- **Patterns** (8): `incredibly`, `remarkably`, `truly`, `vital`, `crucial`, `essential`, … (**2 more**)

#### `hollow_grand_claims`

Marketing-grade superlatives. Almost never appear in human casual writing.

- **Weight**: `4`    **Soft threshold**: `0`    **Hard threshold**: `2`
- **Patterns** (9): `transformative`, `groundbreaking`, `revolutionary`, `cutting-edge`, `state-of-the-art`, `next-generation`, … (**3 more**)

## Multi-word AI tells (`blacklist_phrases`)

Multi-word AI tells. Patterns are matched case-insensitively as word-boundary-anchored substrings. Hit accumulation follows the same soft/hard threshold ladder as blacklist_words.

_9 rule(s)._

#### `meta_hedge`

Meta-comments about what the writer is about to say. The single strongest AI tell. HC3 phrase ratio 80-330x. (Liang 2024 + GPTZero methodology.)

- **Weight**: `8`    **Soft threshold**: `0`    **Hard threshold**: `1`
- **Patterns** (11): `it's important to note`, `it is important to note`, `it's worth noting`, `it is worth noting`, `it's worth mentioning`, `it is worth mentioning`, … (**5 more**)

#### `structural_summary`

Closing-paragraph scaffold. Each is fine once; together they signal AI essay template.

- **Weight**: `6`    **Soft threshold**: `0`    **Hard threshold**: `1`
- **Patterns** (7): `in conclusion`, `in summary`, `to summarize`, `to sum up`, `overall, the`, `ultimately, the`, … (**1 more**)

#### `structural_transitions`

Heavy use of explicit transitions. The n-gram engine also measures transition_density — this rule fires interpretably on the worst offenders so the polish prompt can target them by name.

- **Weight**: `3`    **Soft threshold**: `2`    **Hard threshold**: `5`
- **Patterns** (8): `moreover`, `furthermore`, `additionally,`, `consequently,`, `on the other hand`, `in contrast,`, … (**2 more**)

#### `ai_safety_disclaimer`

Verbatim ChatGPT safety boilerplate. Even one is a near-certain AI signature; weight is set so a single hit produces a HIGH score on its own.

- **Weight**: `15`    **Soft threshold**: `0`    **Hard threshold**: `0`
- **Patterns** (11): `as an ai language model`, `as an ai assistant`, `i'm just an ai`, `i am just an ai`, `i don't have personal`, `i do not have personal`, … (**5 more**)

#### `reflexive_helpers`

Soft-pedalled advice scaffolding. HC3 ratio 3-9x (especially in finance/medicine subsets).

- **Weight**: `4`    **Soft threshold**: `0`    **Hard threshold**: `2`
- **Patterns** (8): `can be a great way to`, `is a great way to`, `is one of the best ways`, `may help to`, `may help you`, `good idea to consult`, … (**2 more**)

#### `exemplar_padding`

Padding phrases that promise examples without committing to specifics.

- **Weight**: `6`    **Soft threshold**: `0`    **Hard threshold**: `1`
- **Patterns** (6): `including but not limited to`, `such as but not limited to`, `to name a few`, `just to name a few`, `among other things`, `among others`

#### `generic_caveat`

Non-answer fallbacks. ChatGPT uses these to look comprehensive without giving advice.

- **Weight**: `4`    **Soft threshold**: `1`    **Hard threshold**: `3`
- **Patterns** (8): `depending on a variety of factors`, `depends on a number of factors`, `depending on a number of factors`, `varies depending on`, `depending on your individual`, `depending on your specific`, … (**2 more**)

#### `enumeration_padding`

Listing scaffolds. Real writers say 'three things' or just list; ChatGPT prefaces.

- **Weight**: `4`    **Soft threshold**: `1`    **Hard threshold**: `3`
- **Patterns** (6): `here are a few`, `here are some`, `there are several`, `there are a few`, `below are some`, `the following are`

#### `important_to_X`

The all-purpose 'important to / essential to / crucial to' scaffold. HC3 3-gram ratio 90-100x for the literal phrase.

- **Weight**: `5`    **Soft threshold**: `1`    **Hard threshold**: `3`
- **Patterns** (6): `important to remember`, `important to consider`, `important to understand`, `essential to understand`, `crucial to understand`, `key to understanding`

## Document structure (`structural_rules`)

Hard-constraint structure checks that fire once per text when their metric crosses the threshold. Unlike blacklist_* rules these do NOT accumulate by count — each rule is a yes/no gate with a fixed penalty.

_2 rule(s)._

#### `heading_density`

Markdown heading (## / ###) density. HC3 human answers never use headings (Reddit-style prose); ChatGPT essay outputs regularly ship '## Section' scaffolds. Threshold: > 3 headings per 1000 chars in text >= 500 chars.

- **Weight**: `5`  **min_text_length**: `500`  **threshold_per_1000_chars**: `3`

#### `list_density`

% of non-empty lines starting with bullet/numbered markers. AI listicle outputs exceed 50% easily; human prose is usually <20%. Guards against ChatGPT's listification reflex.

- **Weight**: `5`  **min_text_length**: `500`  **threshold_ratio**: `0.5`

## Sentence / paragraph rhythm (`rhythm_rules`)

Numeric gates on sentence / paragraph rhythm. Thresholds calibrated by scripts/calibrate_rhythm.py on HC3-en (85k answers). Each rule fires once if its metric crosses the AI threshold; the n-gram engine tracks the same numbers continuously — rhythm_rules give interpretable, prompt-injectable violations on the worst offenders.

_4 rule(s)._

#### `sentence_length_cv`

Coefficient of variation of word-counts across sentences. HC3 calibration: human p25=0.35, AI p75=0.42; AI median 0.32 vs human median 0.47. CV < 0.35 => uniform sentences => AI tell.

- **Weight**: `10`  **min_sentences**: `5`  **ai_threshold**: `0.35`

#### `short_sentence_ratio`

Fraction of sentences under 6 words. HC3: human p75=0.14 vs AI p75=0.00 — ChatGPT almost never uses fragments. Requires >=300 chars so tiny answers aren't flagged.

- **Weight**: `4`  **min_sentences**: `5`  **min_text_length**: `300`  **ai_threshold**: `0.02`

#### `paragraph_uniformity`

CV of paragraph character-counts. Huge HC3 gap: human p25=1.78, AI p75=0.36 (AI paragraphs are remarkably uniform). Paragraph CV < 0.3 with >=3 paragraphs => AI tell.

- **Weight**: `6`  **ai_threshold**: `0.3`

#### `para_opening_enumeration`

Paragraphs starting with enumeration or transition markers (First,/Moreover,/Additionally,/1./2./*). AI uses these >= 3 times in structured answers; human prose blends them inline.

- **Weight**: `5`

## Manufactured anecdotes (`fake_human`)

Pseudo-personal-experience regexes. Only enforced when has_notes=False — if the author has a real notes.md their first-person claims are presumed honest. Patterns are regex. Fixed penalty per hit (weight * max(count, hard_threshold)); no threshold-ladder — a single fake claim is already a problem.

_2 rule(s)._

#### `vague_personal_experience`

Generic first-person experience claims without concrete details. Liang 2024 notes these as common ChatGPT hedges to sound relatable.

- **Weight**: `5`  **hard_threshold**: `1`  **regex**: `True`
- **Patterns** (9): `\bin my (?:personal )?experience\b`, `\bfrom my (?:personal )?experience\b`, `\bbased on my experience\b`, `\bspeaking from (?:personal )?experience\b`, `\bas someone who (?:has|is) (?:been|worked|lived|tried|used)\b`, `\bi['’]ve been (?:\w+ing )?for \d+ (?:years|months)\b`, … (**3 more**)

#### `generic_authority_claim`

Bare assertions of credibility that appear without follow-up specifics. HC3 ratio low but false-positive-cost in humanize workflows is also low since real writers rarely use these verbatim.

- **Weight**: `5`  **hard_threshold**: `1`  **regex**: `True`
- **Patterns** (5): `\btrust me\b,`, `\bbelieve me\b,`, `\bi strongly believe that\b`, `\bi firmly believe that\b`, `\bi can assure you\b`

## Negative — argument-quality signals (`soul_signals`)

Argumentation-quality signals that should be PRESENT in human writing. Each rule fires when its signal count is BELOW min_threshold, adding (min_threshold - count) * weight to the AI score. Think of it as 'penalty for missing human fingerprints'.

_2 rule(s)._

#### `concrete_specifics`

Proper nouns, numbers, and dates ground writing in reality. HC3 AI answers often pass on these (generic enough to sound universal). Counts: Title-Case multi-word names, standalone numbers >= 2 digits, YYYY dates. Min 2 in text >=300 chars. case_insensitive MUST be false — the Title-Case branch relies on case to find proper nouns.

- **Weight**: `5`  **min_threshold**: `2`  **min_text_length**: `300`  **regex**: `True`  **case_insensitive**: `False`
- **Pattern**: `\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b|\b\d{2,}\b|\b(?:19|20)\d{2}\b`

#### `contrarian_hinge`

Argumentative hinge words (but, however, actually, unless, although, despite, yet) signal that the writer is contrasting ideas, not just enumerating. Missing in text >=300 chars => mechanical listing, not thinking.

- **Weight**: `5`  **min_threshold**: `1`  **min_text_length**: `300`  **regex**: `True`
- **Pattern**: `\b(?:but|however,|actually,|unless|although|despite|yet,)\b`

---

Regenerate this file with `make rules-doc` or `uv run python scripts/gen_rules_doc.py`.
