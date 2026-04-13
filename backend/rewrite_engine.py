"""Rewrite orchestration engine.

Given a CardContext, generates N prompt variants according to the
configured distribution of conservative / moderate / aggressive styles.

Default distributions:
  2 variants → 1 moderate + 1 aggressive
  3 variants → 1 conservative + 1 moderate + 1 aggressive
  N variants → spread roughly evenly across styles
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from backend.card_interpreter import CardContext, RewriteMode
from backend.content_normalizer import ContentNormalizer
from backend.llm_provider import BaseLLMProvider, LLMError
from backend.prompts import (
    REWRITE_AGGRESSIVE,
    REWRITE_CONSERVATIVE,
    REWRITE_MODERATE,
    PromptTemplate,
    get_prompt,
)

logger = logging.getLogger(__name__)

STYLE_PROMPTS: dict[str, PromptTemplate] = {
    "conservative": REWRITE_CONSERVATIVE,
    "moderate": REWRITE_MODERATE,
    "aggressive": REWRITE_AGGRESSIVE,
}


@dataclass
class RewriteVariant:
    id: str
    style: str
    text: str           # the rewritten prompt (HTML preserved from original if needed)
    text_plain: str     # plain text version shown in UI
    warnings: list[str]
    raw_llm_response: str = ""
    error: Optional[str] = None


def compute_distribution(
    variant_count: int,
    override: Optional[dict[str, int]] = None,
) -> list[str]:
    """
    Return an ordered list of style names for the requested variant count.

    If override is provided, it should be {"conservative": N, "moderate": N, "aggressive": N}.
    """
    if override:
        styles: list[str] = []
        for style, count in override.items():
            styles.extend([style] * count)
        return styles[:variant_count]

    if variant_count <= 0:
        return []
    if variant_count == 1:
        return ["moderate"]
    if variant_count == 2:
        return ["moderate", "aggressive"]

    # 3+ variants: spread evenly across three styles
    base, remainder = divmod(variant_count, 3)
    styles = (
        ["conservative"] * base
        + ["moderate"] * base
        + ["aggressive"] * base
    )
    # Distribute remainder: prefer aggressive, then moderate
    extras = ["aggressive", "moderate", "conservative"]
    for i in range(remainder):
        styles.append(extras[i % 3])

    return sorted(
        styles,
        key=lambda s: {"conservative": 0, "moderate": 1, "aggressive": 2}[s],
    )


class RewriteEngine:
    def __init__(self, provider: BaseLLMProvider) -> None:
        self.provider = provider
        self.normalizer = ContentNormalizer()

    async def generate_variants(
        self,
        ctx: CardContext,
        variant_count: int = 3,
        distribution_override: Optional[dict[str, int]] = None,
    ) -> list[RewriteVariant]:
        """
        Generate `variant_count` prompt rewrites for the given CardContext.

        Returns list of RewriteVariant; failed variants have error set.
        """
        if ctx.rewrite_mode == RewriteMode.UNSUPPORTED:
            return [
                RewriteVariant(
                    id=str(uuid.uuid4()),
                    style="unsupported",
                    text=ctx.prompt_raw,
                    text_plain=ctx.prompt_plain,
                    warnings=["Note type not supported for rewriting."],
                    error="unsupported",
                )
            ]

        styles = compute_distribution(variant_count, distribution_override)
        prompt_text = ctx.prompt_plain
        answer_text = ctx.answer_plain or ""

        # Fan out all variants concurrently (respecting concurrency cap via semaphore)
        concurrency = getattr(self.provider, "concurrency_cap", 3)
        sem = asyncio.Semaphore(concurrency)

        async def _gen_one(style: str, idx: int) -> RewriteVariant:
            async with sem:
                return await self._generate_single(
                    style=style,
                    prompt_text=prompt_text,
                    answer_text=answer_text,
                    prompt_raw=ctx.prompt_raw,
                    protected_spans=ctx.protected_spans,
                    variant_id=f"v{idx+1}-{style[:3]}-{uuid.uuid4().hex[:6]}",
                )

        tasks = [_gen_one(style, i) for i, style in enumerate(styles)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        variants: list[RewriteVariant] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                variants.append(
                    RewriteVariant(
                        id=f"error-{i}",
                        style=styles[i],
                        text=ctx.prompt_raw,
                        text_plain=ctx.prompt_plain,
                        warnings=[str(result)],
                        error=str(result),
                    )
                )
            else:
                variants.append(result)

        return variants

    async def _generate_single(
        self,
        style: str,
        prompt_text: str,
        answer_text: str,
        prompt_raw: str,
        protected_spans: list,
        variant_id: str,
    ) -> RewriteVariant:
        tpl = STYLE_PROMPTS[style]
        user_msg = tpl.user.format(
            prompt=prompt_text,
            answer=answer_text,
            variant_id=variant_id,
        )

        try:
            raw_response = await self.provider.complete(tpl.system, user_msg)
            data = self._parse_response(raw_response, style)
        except LLMError as exc:
            return RewriteVariant(
                id=variant_id,
                style=style,
                text=prompt_raw,
                text_plain=prompt_text,
                warnings=[str(exc)],
                error=str(exc),
            )

        if not data.get("text"):
            return RewriteVariant(
                id=variant_id,
                style=style,
                text=prompt_raw,
                text_plain=prompt_text,
                warnings=data.get("warnings", ["Model returned empty rewrite."]),
                raw_llm_response=raw_response,
                error="empty_rewrite",
            )

        # Reinsert protected spans
        plain_with_tokens = data["text"]
        final_plain = self.normalizer.reinsert_protected(plain_with_tokens, protected_spans)

        # Rebuild HTML: if original was plain text, final is plain; otherwise
        # we preserve the original HTML wrapping and replace only the text.
        # For now keep it as plain text; template injection will decide rendering.
        final_text = final_plain

        return RewriteVariant(
            id=data.get("id", variant_id),
            style=data.get("style", style),
            text=final_text,
            text_plain=final_plain,
            warnings=data.get("warnings", []),
            raw_llm_response=raw_response,
        )

    def _parse_response(self, raw: str, expected_style: str) -> dict[str, Any]:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:])
            raw = raw.rsplit("```", 1)[0]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise LLMError(f"Model did not return valid JSON. Raw output: {raw[:300]}")

        if not isinstance(data, dict):
            raise LLMError("Model returned JSON but not an object.")

        return data

    def variants_to_storage_format(self, variants: list[RewriteVariant]) -> list[dict[str, Any]]:
        """Convert variants to the format stored in NoteRewrite.rewrite_data."""
        return [
            {
                "id": v.id,
                "style": v.style,
                "text": v.text,
                "text_plain": v.text_plain,
                "warnings": v.warnings,
                "error": v.error,
                "validation": None,  # filled in by validation engine
            }
            for v in variants
        ]

    @staticmethod
    def content_hash(prompt: str, answer: str) -> str:
        """Compute a stable hash of the prompt+answer pair for stale detection."""
        combined = f"{prompt}\x00{answer}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
