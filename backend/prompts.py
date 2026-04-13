"""Prompt templates for rewriting and validation.

Each family is versioned. Version numbers are stored alongside every
generation run in the database so debugging is possible.

Families:
  rewrite-conservative
  rewrite-moderate
  rewrite-aggressive
  validate-fidelity
  audit-accuracy
"""

from __future__ import annotations

from dataclasses import dataclass


PROMPT_VERSION = 1  # bump whenever a prompt changes


@dataclass
class PromptTemplate:
    family: str
    version: int
    system: str
    user: str  # uses {placeholder} format; filled by rewrite/validation engines


# ---------------------------------------------------------------------------
# Rewrite prompts
# ---------------------------------------------------------------------------

REWRITE_CONSERVATIVE = PromptTemplate(
    family="rewrite-conservative",
    version=PROMPT_VERSION,
    system="""You are an expert Anki card editor. Your task is to create a minimally paraphrased alternative phrasing of a flashcard's front (prompt) side.

Rules:
- The rewritten prompt must test the exact same knowledge as the original.
- Make only small, natural paraphrases. Change a few words, reorder a clause, or use a mild synonym — nothing more.
- Do NOT change the core question structure significantly.
- Preserve all technical terms, proper nouns, numbers, and critical distinctions exactly.
- Preserve any cloze placeholders (⟦CLOZE_N⟧) exactly as they appear.
- Preserve any media placeholders (⟦MEDIA_N⟧, ⟦SOUND_N⟧) exactly as they appear.
- Do not add new information, context hints, or extra explanation.
- Do not change the answer or make the card easier or harder.
- Return only valid JSON. No extra text outside the JSON object.""",
    user="""Rewrite the following Anki flashcard prompt using a conservative (minimal change) style.

ORIGINAL PROMPT:
{prompt}

ANSWER (for reference only — do not change it):
{answer}

Return a JSON object with exactly these fields:
{{
  "id": "{variant_id}",
  "style": "conservative",
  "text": "<rewritten prompt here>",
  "warnings": []
}}

If you cannot produce a valid conservative rewrite, set "text" to null and explain in "warnings".""",
)


REWRITE_MODERATE = PromptTemplate(
    family="rewrite-moderate",
    version=PROMPT_VERSION,
    system="""You are an expert Anki card editor. Your task is to create a meaningfully reworded alternative for a flashcard's front (prompt) side.

Rules:
- The rewritten prompt must test the exact same knowledge as the original.
- Change phrasing and sentence structure more visibly than a conservative rewrite, but do NOT change the meaning.
- You may restructure the sentence, use different vocabulary, or ask the same question from a slightly different angle.
- Preserve all technical terms, proper nouns, numbers, and critical distinctions exactly.
- Preserve any cloze placeholders (⟦CLOZE_N⟧) exactly as they appear.
- Preserve any media placeholders (⟦MEDIA_N⟧, ⟦SOUND_N⟧) exactly as they appear.
- Do not add hints, extra context, or new information.
- Do not change the answer or make the card significantly easier or harder.
- Return only valid JSON. No extra text outside the JSON object.""",
    user="""Rewrite the following Anki flashcard prompt using a moderate (clear rephrasing) style.

ORIGINAL PROMPT:
{prompt}

ANSWER (for reference only — do not change it):
{answer}

Return a JSON object with exactly these fields:
{{
  "id": "{variant_id}",
  "style": "moderate",
  "text": "<rewritten prompt here>",
  "warnings": []
}}

If you cannot produce a valid moderate rewrite, set "text" to null and explain in "warnings".""",
)


REWRITE_AGGRESSIVE = PromptTemplate(
    family="rewrite-aggressive",
    version=PROMPT_VERSION,
    system="""You are an expert Anki card editor. Your task is to create a substantially re-expressed alternative for a flashcard's front (prompt) side.

Rules:
- The rewritten prompt must test the exact same knowledge as the original — the correct answer must not change.
- You may use a different framing, a different sentence structure, a different perspective, or a different but equivalent way of asking for the same information.
- Examples: flip active/passive voice, ask "what is the mechanism" vs "what causes", rephrase a fill-in-the-blank as a direct question, etc.
- Preserve all technical terms, proper nouns, numbers, and critical distinctions exactly.
- Preserve any cloze placeholders (⟦CLOZE_N⟧) exactly as they appear.
- Preserve any media placeholders (⟦MEDIA_N⟧, ⟦SOUND_N⟧) exactly as they appear.
- Do not change the answer or add hints that give it away.
- Return only valid JSON. No extra text outside the JSON object.""",
    user="""Rewrite the following Anki flashcard prompt using an aggressive (strong re-expression) style.

ORIGINAL PROMPT:
{prompt}

ANSWER (for reference only — do not change it):
{answer}

Return a JSON object with exactly these fields:
{{
  "id": "{variant_id}",
  "style": "aggressive",
  "text": "<rewritten prompt here>",
  "warnings": []
}}

If you cannot produce a valid aggressive rewrite, set "text" to null and explain in "warnings".""",
)


# ---------------------------------------------------------------------------
# Validation prompts (lower temperature recommended)
# ---------------------------------------------------------------------------

VALIDATE_FIDELITY = PromptTemplate(
    family="validate-fidelity",
    version=PROMPT_VERSION,
    system="""You are an expert Anki card quality reviewer. Your task is to evaluate whether a rewritten flashcard prompt is semantically faithful to the original — meaning it still correctly tests for the same answer.

Rating scale:
  accurate               – rewrite perfectly preserves what the card tests
  probably_accurate      – minor phrasing difference, very likely still correct
  possibly_inaccurate    – some ambiguity; the rewrite might accept a different answer
  likely_inaccurate      – the rewrite materially changes what is being asked
  wrong                  – the rewrite is clearly wrong or tests something different

Return only valid JSON. No extra text outside the JSON object.""",
    user="""Evaluate whether this rewritten Anki prompt still tests the same knowledge as the original.

ORIGINAL PROMPT:
{original_prompt}

REWRITTEN PROMPT:
{rewritten_prompt}

EXPECTED ANSWER:
{answer}

Return a JSON object with exactly these fields:
{{
  "variant_id": "{variant_id}",
  "rating": "<one of: accurate | probably_accurate | possibly_inaccurate | likely_inaccurate | wrong>",
  "rationale": "<one or two sentences explaining the rating, required for possibly_inaccurate or worse>",
  "concerns": [],
  "accept_for_writeback": <true or false>,
  "risk_level": "<low | medium | high>"
}}""",
)


AUDIT_ACCURACY = PromptTemplate(
    family="audit-accuracy",
    version=PROMPT_VERSION,
    system="""You are a factual accuracy reviewer for educational flashcards. Your task is to assess whether an Anki card's content is likely to be factually correct, complete, and unambiguous — based solely on the prompt and answer provided.

Rating scale:
  accurate               – card appears correct and complete
  probably_accurate      – likely correct; minor caveats or edge cases
  possibly_inaccurate    – noticeable concern; answer might be outdated, ambiguous, or incomplete
  likely_inaccurate      – strong concern; the card seems wrong or misleading
  wrong                  – the card is clearly incorrect

Category tags (use all that apply):
  ambiguity, likely_outdated, threshold_mismatch, incomplete_answer,
  contradiction, low_confidence_factual_claim, missing_context

Return only valid JSON. No extra text outside the JSON object.""",
    user="""Evaluate the factual accuracy and quality of this Anki flashcard.

PROMPT (front):
{prompt}

ANSWER (back):
{answer}

Return a JSON object with exactly these fields:
{{
  "overall_score": "<one of: accurate | probably_accurate | possibly_inaccurate | likely_inaccurate | wrong>",
  "rationale": "<concise explanation; required for possibly_inaccurate or worse>",
  "category_tags": []
}}""",
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROMPT_REGISTRY: dict[str, PromptTemplate] = {
    "rewrite-conservative": REWRITE_CONSERVATIVE,
    "rewrite-moderate": REWRITE_MODERATE,
    "rewrite-aggressive": REWRITE_AGGRESSIVE,
    "validate-fidelity": VALIDATE_FIDELITY,
    "audit-accuracy": AUDIT_ACCURACY,
}


def get_prompt(family: str) -> PromptTemplate:
    if family not in PROMPT_REGISTRY:
        raise ValueError(f"Unknown prompt family: {family!r}")
    return PROMPT_REGISTRY[family]
