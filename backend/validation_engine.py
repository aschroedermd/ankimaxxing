"""Validation engine.

Two separate functions:
  1. validate_variant_fidelity() – checks if a rewrite still tests the same thing
  2. audit_card_accuracy()       – checks if the original card content is factually sound
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from backend.llm_provider import BaseLLMProvider, LLMError
from backend.prompts import AUDIT_ACCURACY, VALIDATE_FIDELITY

logger = logging.getLogger(__name__)

VALID_RATINGS = {
    "accurate",
    "probably_accurate",
    "possibly_inaccurate",
    "likely_inaccurate",
    "wrong",
}

VALID_RISK_LEVELS = {"low", "medium", "high"}

AUDIT_TAGS = {
    "ambiguity",
    "likely_outdated",
    "threshold_mismatch",
    "incomplete_answer",
    "contradiction",
    "low_confidence_factual_claim",
    "missing_context",
}


@dataclass
class FidelityResult:
    variant_id: str
    rating: str
    rationale: str
    concerns: list[str]
    accept_for_writeback: bool
    risk_level: str
    raw_response: str = ""
    error: Optional[str] = None


@dataclass
class AuditResult:
    note_id: int
    overall_score: str
    rationale: str
    category_tags: list[str]
    raw_response: str = ""
    error: Optional[str] = None


class ValidationEngine:
    """Runs fidelity validation and deck audit scoring."""

    def __init__(self, provider: BaseLLMProvider) -> None:
        self.provider = provider

    # ------------------------------------------------------------------
    # Variant fidelity validation
    # ------------------------------------------------------------------

    async def validate_variant_fidelity(
        self,
        original_prompt: str,
        rewritten_prompt: str,
        answer: str,
        variant_id: str,
    ) -> FidelityResult:
        """
        Evaluate whether a rewritten prompt still correctly tests the same knowledge.
        """
        user_msg = VALIDATE_FIDELITY.user.format(
            original_prompt=original_prompt,
            rewritten_prompt=rewritten_prompt,
            answer=answer,
            variant_id=variant_id,
        )

        try:
            raw = await self.provider.complete(VALIDATE_FIDELITY.system, user_msg)
            data = self._parse_json(raw)
        except LLMError as exc:
            return FidelityResult(
                variant_id=variant_id,
                rating="possibly_inaccurate",
                rationale="Validation failed to complete.",
                concerns=[str(exc)],
                accept_for_writeback=False,
                risk_level="high",
                error=str(exc),
            )

        rating = data.get("rating", "possibly_inaccurate")
        if rating not in VALID_RATINGS:
            rating = "possibly_inaccurate"

        risk_level = data.get("risk_level", "medium")
        if risk_level not in VALID_RISK_LEVELS:
            risk_level = "medium"

        # Default accept logic: accept if accurate or probably_accurate
        accept = data.get("accept_for_writeback")
        if accept is None:
            accept = rating in {"accurate", "probably_accurate"}

        return FidelityResult(
            variant_id=data.get("variant_id", variant_id),
            rating=rating,
            rationale=data.get("rationale", ""),
            concerns=data.get("concerns", []),
            accept_for_writeback=bool(accept),
            risk_level=risk_level,
            raw_response=raw,
        )

    async def validate_all_variants(
        self,
        original_prompt: str,
        answer: str,
        variants: list[dict[str, Any]],
    ) -> list[FidelityResult]:
        """Validate multiple variants for a single note."""
        import asyncio

        results = await asyncio.gather(
            *[
                self.validate_variant_fidelity(
                    original_prompt=original_prompt,
                    rewritten_prompt=v["text_plain"],
                    answer=answer,
                    variant_id=v["id"],
                )
                for v in variants
                if not v.get("error")
            ],
            return_exceptions=True,
        )

        final: list[FidelityResult] = []
        for r in results:
            if isinstance(r, Exception):
                final.append(
                    FidelityResult(
                        variant_id="unknown",
                        rating="possibly_inaccurate",
                        rationale="Validation error.",
                        concerns=[str(r)],
                        accept_for_writeback=False,
                        risk_level="high",
                        error=str(r),
                    )
                )
            else:
                final.append(r)
        return final

    # ------------------------------------------------------------------
    # Deck factual audit
    # ------------------------------------------------------------------

    async def audit_card_accuracy(
        self,
        note_id: int,
        prompt: str,
        answer: str,
    ) -> AuditResult:
        """
        Evaluate the factual accuracy of an original Anki card.

        This is separate from variant fidelity — a card can have perfectly
        faithful rewrites but still contain wrong information.
        """
        user_msg = AUDIT_ACCURACY.user.format(prompt=prompt, answer=answer)

        try:
            raw = await self.provider.complete(AUDIT_ACCURACY.system, user_msg)
            data = self._parse_json(raw)
        except LLMError as exc:
            return AuditResult(
                note_id=note_id,
                overall_score="possibly_inaccurate",
                rationale="Audit failed to complete.",
                category_tags=[],
                error=str(exc),
            )

        score = data.get("overall_score", "possibly_inaccurate")
        if score not in VALID_RATINGS:
            score = "possibly_inaccurate"

        tags = [t for t in data.get("category_tags", []) if t in AUDIT_TAGS]

        return AuditResult(
            note_id=note_id,
            overall_score=score,
            rationale=data.get("rationale", ""),
            category_tags=tags,
            raw_response=raw,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_json(self, raw: str) -> dict[str, Any]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0]
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Validation response not valid JSON: {exc}") from exc
