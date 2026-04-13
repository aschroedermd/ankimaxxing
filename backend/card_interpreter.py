"""Card understanding engine.

Converts raw AnkiConnect note/model data into a structured CardContext
that downstream engines (rewrite, validation) can consume.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from backend.anki_client import AnkiClient
from backend.content_normalizer import ContentNormalizer
from backend.note_type_registry import (
    NoteKind,
    NoteTypeClassification,
    SupportLevel,
    classify_note_type,
    get_prompt_fields_for_kind,
)


class RewriteMode(str, Enum):
    FIELD_REWRITE = "field_rewrite"   # rewrite entire prompt field
    CLOZE_CONTEXT = "cloze_context"  # rewrite context around cloze tokens
    UNSUPPORTED = "unsupported"


@dataclass
class ProtectedSpan:
    """A text span that must survive the rewrite unchanged."""
    start: int
    end: int
    text: str
    kind: str  # "cloze" | "media" | "html_entity" | "type_tag"


@dataclass
class CardContext:
    note_id: int
    model_name: str
    template_name: str
    prompt_field: str
    answer_field: Optional[str]
    prompt_raw: str           # original HTML from Anki field
    answer_raw: Optional[str]
    prompt_plain: str         # cleaned text for LLM consumption
    answer_plain: Optional[str]
    content_type: str         # "html" | "text" | "cloze"
    card_kind: NoteKind
    rewrite_mode: RewriteMode
    support_level: SupportLevel
    protected_spans: list[ProtectedSpan] = field(default_factory=list)
    cloze_ordinal: Optional[int] = None  # for cloze notes
    notes: list[str] = field(default_factory=list)  # human-readable warnings


class CardInterpreter:
    def __init__(self, anki: AnkiClient) -> None:
        self.anki = anki
        self.normalizer = ContentNormalizer()
        # Cache model info to avoid repeated API calls
        self._model_cache: dict[str, dict[str, Any]] = {}

    async def _get_model_info(self, model_name: str) -> dict[str, Any]:
        if model_name not in self._model_cache:
            fields = await self.anki.model_field_names(model_name)
            templates_on_fields = await self.anki.model_fields_on_templates(model_name)
            templates_html = await self.anki.model_templates(model_name)
            self._model_cache[model_name] = {
                "fields": fields,
                "fields_on_templates": templates_on_fields,
                "templates_html": templates_html,
            }
        return self._model_cache[model_name]

    async def interpret_note(
        self,
        note_info: dict[str, Any],
        template_name: Optional[str] = None,
    ) -> list[CardContext]:
        """
        Return one CardContext per relevant card template for this note.

        If template_name is given, only that template is processed.
        """
        note_id: int = note_info["noteId"]
        model_name: str = note_info["modelName"]
        raw_fields: dict[str, dict] = note_info["fields"]

        model_info = await self._get_model_info(model_name)
        field_names: list[str] = model_info["fields"]
        fields_on_templates: dict = model_info["fields_on_templates"]

        classification = classify_note_type(
            model_name,
            field_names=field_names,
            template_names=list(fields_on_templates.keys()),
        )

        template_names = (
            [template_name] if template_name else list(fields_on_templates.keys())
        )

        contexts: list[CardContext] = []

        for tpl_name in template_names:
            ctx = await self._build_context(
                note_id=note_id,
                model_name=model_name,
                template_name=tpl_name,
                raw_fields=raw_fields,
                classification=classification,
                fields_on_templates=fields_on_templates,
            )
            if ctx:
                contexts.append(ctx)

        return contexts

    async def _build_context(
        self,
        note_id: int,
        model_name: str,
        template_name: str,
        raw_fields: dict[str, dict],
        classification: NoteTypeClassification,
        fields_on_templates: dict[str, list[list[str]]],
    ) -> Optional[CardContext]:
        kind = classification.kind
        support = classification.support_level

        prompt_field, answer_field = get_prompt_fields_for_kind(
            kind, template_name, fields_on_templates
        )

        if not prompt_field:
            return CardContext(
                note_id=note_id,
                model_name=model_name,
                template_name=template_name,
                prompt_field="",
                answer_field=None,
                prompt_raw="",
                answer_raw=None,
                prompt_plain="",
                answer_plain=None,
                content_type="text",
                card_kind=kind,
                rewrite_mode=RewriteMode.UNSUPPORTED,
                support_level=SupportLevel.UNSUPPORTED,
                notes=["Could not determine prompt field for this template."],
            )

        prompt_raw = raw_fields.get(prompt_field, {}).get("value", "")
        answer_raw = (
            raw_fields.get(answer_field, {}).get("value", "")
            if answer_field
            else None
        )

        # Determine content type and rewrite mode
        if kind == NoteKind.CLOZE:
            content_type = "cloze"
            rewrite_mode = RewriteMode.CLOZE_CONTEXT
        elif "<" in prompt_raw:
            content_type = "html"
            rewrite_mode = RewriteMode.FIELD_REWRITE
        else:
            content_type = "text"
            rewrite_mode = RewriteMode.FIELD_REWRITE

        if support == SupportLevel.UNSUPPORTED:
            rewrite_mode = RewriteMode.UNSUPPORTED

        # Normalize for LLM consumption
        prompt_plain, prompt_spans = self.normalizer.normalize(
            prompt_raw, kind=kind
        )
        answer_plain = None
        if answer_raw is not None:
            answer_plain, _ = self.normalizer.normalize(answer_raw, kind=NoteKind.BASIC)

        return CardContext(
            note_id=note_id,
            model_name=model_name,
            template_name=template_name,
            prompt_field=prompt_field,
            answer_field=answer_field,
            prompt_raw=prompt_raw,
            answer_raw=answer_raw,
            prompt_plain=prompt_plain,
            answer_plain=answer_plain,
            content_type=content_type,
            card_kind=kind,
            rewrite_mode=rewrite_mode,
            support_level=support,
            protected_spans=prompt_spans,
            notes=classification.notes.copy(),
        )
