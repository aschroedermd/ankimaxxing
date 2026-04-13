"""Note type registry: classifies Anki note types by rewrite support level.

Support levels:
  FULL          – well-known type, safe to clone and rewrite
  CAUTION       – recognizable but has quirks; proceed with user confirmation
  AUDIT_ONLY    – can audit for accuracy but not safe to rewrite
  UNSUPPORTED   – skip entirely

Known note type families (matched by prefix/exact name):
  - Basic
  - Basic (and reversed card)
  - Basic (optional reversed card)
  - Basic (type in the answer)
  - Cloze
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SupportLevel(str, Enum):
    FULL = "full"
    CAUTION = "caution"
    AUDIT_ONLY = "audit_only"
    UNSUPPORTED = "unsupported"


class NoteKind(str, Enum):
    BASIC = "basic"
    BASIC_REVERSED = "basic_reversed"
    BASIC_OPTIONAL_REVERSED = "basic_optional_reversed"
    BASIC_TYPE_ANSWER = "basic_type_answer"
    CLOZE = "cloze"
    UNKNOWN = "unknown"


@dataclass
class NoteTypeClassification:
    model_name: str
    support_level: SupportLevel
    kind: NoteKind
    notes: list[str] = field(default_factory=list)
    is_app_managed: bool = False


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

_APP_SUFFIX = " (AI Rewriter)"

_BASIC_NAMES = {
    "Basic",
    "基本",  # Japanese
}

_BASIC_REVERSED_NAMES = {
    "Basic (and reversed card)",
    "Basic (und umgekehrte Karte)",
}

_BASIC_OPTIONAL_REVERSED_NAMES = {
    "Basic (optional reversed card)",
}

_BASIC_TYPE_NAMES = {
    "Basic (type in the answer)",
}

_CLOZE_NAMES = {
    "Cloze",
    "穴埋め",
}


def _strip_app_suffix(name: str) -> str:
    if name.endswith(_APP_SUFFIX):
        return name[: -len(_APP_SUFFIX)]
    return name


def classify_note_type(
    model_name: str,
    field_names: list[str] | None = None,
    template_names: list[str] | None = None,
) -> NoteTypeClassification:
    """
    Classify a note type by name (and optionally by fields/templates).

    Returns a NoteTypeClassification with support level, kind, and notes.
    """
    is_app_managed = model_name.endswith(_APP_SUFFIX)
    base_name = _strip_app_suffix(model_name)

    def _classify(name: str) -> tuple[SupportLevel, NoteKind, list[str]]:
        if name in _BASIC_NAMES:
            return SupportLevel.FULL, NoteKind.BASIC, []

        if name in _BASIC_REVERSED_NAMES:
            return SupportLevel.FULL, NoteKind.BASIC_REVERSED, []

        if name in _BASIC_OPTIONAL_REVERSED_NAMES:
            return (
                SupportLevel.FULL,
                NoteKind.BASIC_OPTIONAL_REVERSED,
                ["Only cards that actually exist will be rewritten."],
            )

        if name in _BASIC_TYPE_NAMES:
            return (
                SupportLevel.CAUTION,
                NoteKind.BASIC_TYPE_ANSWER,
                ["Type-in-answer cards are rewritten but 'type:' syntax is preserved."],
            )

        if name in _CLOZE_NAMES:
            return (
                SupportLevel.FULL,
                NoteKind.CLOZE,
                ["Cloze tokens are protected; only surrounding context is rewritten."],
            )

        # Heuristic: name contains "cloze" (case-insensitive)
        if "cloze" in name.lower():
            return (
                SupportLevel.CAUTION,
                NoteKind.CLOZE,
                [
                    "Detected as cloze-like by name. Cloze tokens will be protected, "
                    "but verify the template uses standard {{cloze:Field}} syntax."
                ],
            )

        # Heuristic: name starts with "Basic"
        if name.lower().startswith("basic"):
            return (
                SupportLevel.CAUTION,
                NoteKind.BASIC,
                [
                    "Custom Basic variant detected. Front/Back fields assumed; "
                    "verify templates use standard field names."
                ],
            )

        # Image occlusion
        if "image occlusion" in name.lower() or "image occlusion" in (
            " ".join(field_names or []).lower()
        ):
            return (
                SupportLevel.AUDIT_ONLY,
                NoteKind.UNKNOWN,
                ["Image occlusion notes cannot be rewritten; audit-only mode is available."],
            )

        # Unknown with standard Front/Back fields → cautious
        if field_names and {"Front", "Back"}.issubset(set(field_names)):
            return (
                SupportLevel.CAUTION,
                NoteKind.BASIC,
                [
                    "Custom note type with standard Front/Back fields. "
                    "Templates must be reviewed before patching."
                ],
            )

        return (
            SupportLevel.AUDIT_ONLY,
            NoteKind.UNKNOWN,
            [
                "Note type not recognized. Audit-only mode is available. "
                "Rewrite support may be added via manual field mapping in a future version."
            ],
        )

    support_level, kind, notes = _classify(base_name)

    return NoteTypeClassification(
        model_name=model_name,
        support_level=support_level,
        kind=kind,
        notes=notes,
        is_app_managed=is_app_managed,
    )


def get_prompt_fields_for_kind(
    kind: NoteKind,
    template_name: str,
    fields_on_templates: dict[str, list[list[str]]],
) -> tuple[str | None, str | None]:
    """
    Return (prompt_field, answer_field) for a given card template.

    Uses modelFieldsOnTemplates data when available; falls back to kind-based
    defaults for well-known note types.
    """
    # Prefer the API-provided mapping
    if template_name in fields_on_templates:
        front_fields, back_fields = fields_on_templates[template_name]
        prompt = front_fields[0] if front_fields else None
        answer = back_fields[0] if back_fields else None
        return prompt, answer

    # Fallback defaults for well-known kinds
    if kind in (NoteKind.BASIC, NoteKind.BASIC_TYPE_ANSWER):
        return "Front", "Back"

    if kind == NoteKind.BASIC_REVERSED:
        if "2" in template_name or "reverse" in template_name.lower():
            return "Back", "Front"
        return "Front", "Back"

    if kind == NoteKind.BASIC_OPTIONAL_REVERSED:
        if "2" in template_name or "reverse" in template_name.lower():
            return "Back", "Front"
        return "Front", "Back"

    if kind == NoteKind.CLOZE:
        return "Text", None  # Cloze answer is derived from the field itself

    return None, None
