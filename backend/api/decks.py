"""API routes: deck browsing and note introspection."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.anki_client import AnkiClient, AnkiConnectError
from backend.card_interpreter import CardInterpreter
from backend.note_type_registry import SupportLevel, classify_note_type

router = APIRouter(prefix="/decks", tags=["decks"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class DeckSummary(BaseModel):
    name: str
    id: Optional[int] = None
    note_count: int = 0


class NoteTypeSummary(BaseModel):
    model_name: str
    support_level: str
    kind: str
    notes: list[str]
    is_app_managed: bool
    field_names: list[str]
    template_names: list[str]


class NotePreview(BaseModel):
    note_id: int
    model_name: str
    fields: dict[str, str]
    tags: list[str]
    cards: list[int]


class DeckInspection(BaseModel):
    deck_name: str
    note_count: int
    note_types: list[NoteTypeSummary]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[DeckSummary])
async def list_decks():
    """Return all Anki decks with note counts."""
    anki = AnkiClient()
    try:
        deck_ids = await anki.deck_names_and_ids()
    except AnkiConnectError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    results: list[DeckSummary] = []
    for name, deck_id in deck_ids.items():
        try:
            count = await anki.get_note_count_in_deck(name)
        except Exception:
            count = 0
        results.append(DeckSummary(name=name, id=deck_id, note_count=count))

    return sorted(results, key=lambda d: d.name)


@router.get("/ping")
async def ping_anki():
    """Check AnkiConnect connectivity."""
    anki = AnkiClient()
    reachable = await anki.ping()
    if not reachable:
        raise HTTPException(
            status_code=503,
            detail="AnkiConnect is not reachable. Make sure Anki is running with the AnkiConnect add-on.",
        )
    version = await anki.get_version()
    return {"status": "ok", "anki_connect_version": version}


@router.get("/note-types", response_model=list[NoteTypeSummary])
async def list_note_types():
    """Return all note types with their support classification."""
    anki = AnkiClient()
    try:
        model_names = await anki.model_names()
    except AnkiConnectError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    results: list[NoteTypeSummary] = []
    for name in model_names:
        try:
            fields = await anki.model_field_names(name)
            templates_map = await anki.model_fields_on_templates(name)
            classification = classify_note_type(
                name, field_names=fields, template_names=list(templates_map.keys())
            )
            results.append(
                NoteTypeSummary(
                    model_name=name,
                    support_level=classification.support_level.value,
                    kind=classification.kind.value,
                    notes=classification.notes,
                    is_app_managed=classification.is_app_managed,
                    field_names=fields,
                    template_names=list(templates_map.keys()),
                )
            )
        except Exception as exc:
            results.append(
                NoteTypeSummary(
                    model_name=name,
                    support_level=SupportLevel.UNSUPPORTED.value,
                    kind="unknown",
                    notes=[f"Error inspecting note type: {exc}"],
                    is_app_managed=False,
                    field_names=[],
                    template_names=[],
                )
            )

    return sorted(results, key=lambda m: m.model_name)


@router.get("/{deck_name}/inspect", response_model=DeckInspection)
async def inspect_deck(deck_name: str):
    """
    Inspect a deck: return note count and a breakdown of note types with
    their support classification.
    """
    anki = AnkiClient()
    try:
        note_ids = await anki.find_notes(f'deck:"{deck_name}"')
    except AnkiConnectError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if not note_ids:
        return DeckInspection(deck_name=deck_name, note_count=0, note_types=[])

    # Sample up to 200 notes to determine note types in use
    sample_ids = note_ids[:200]
    notes = await anki.chunk_notes_info(sample_ids)

    model_names_seen: set[str] = {n["modelName"] for n in notes}

    note_types: list[NoteTypeSummary] = []
    for model_name in model_names_seen:
        try:
            fields = await anki.model_field_names(model_name)
            templates_map = await anki.model_fields_on_templates(model_name)
            classification = classify_note_type(
                model_name, field_names=fields, template_names=list(templates_map.keys())
            )
            note_types.append(
                NoteTypeSummary(
                    model_name=model_name,
                    support_level=classification.support_level.value,
                    kind=classification.kind.value,
                    notes=classification.notes,
                    is_app_managed=classification.is_app_managed,
                    field_names=fields,
                    template_names=list(templates_map.keys()),
                )
            )
        except Exception as exc:
            note_types.append(
                NoteTypeSummary(
                    model_name=model_name,
                    support_level=SupportLevel.UNSUPPORTED.value,
                    kind="unknown",
                    notes=[str(exc)],
                    is_app_managed=False,
                    field_names=[],
                    template_names=[],
                )
            )

    return DeckInspection(
        deck_name=deck_name,
        note_count=len(note_ids),
        note_types=sorted(note_types, key=lambda t: t.model_name),
    )


@router.get("/notes/{note_id}", response_model=NotePreview)
async def get_note_by_id(note_id: int):
    """Return note info for a specific note ID."""
    anki = AnkiClient()
    try:
        notes = await anki.notes_info([note_id])
    except AnkiConnectError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if not notes:
        raise HTTPException(status_code=404, detail="Note not found.")

    n = notes[0]
    return NotePreview(
        note_id=n["noteId"],
        model_name=n["modelName"],
        fields={k: v["value"] for k, v in n["fields"].items()},
        tags=n.get("tags", []),
        cards=n.get("cards", []),
    )


@router.get("/{deck_name}/notes", response_model=list[NotePreview])
async def list_notes(
    deck_name: str,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Return notes in a deck (paginated)."""
    anki = AnkiClient()
    try:
        note_ids = await anki.find_notes(f'deck:"{deck_name}"')
    except AnkiConnectError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    page_ids = note_ids[offset : offset + limit]
    if not page_ids:
        return []

    notes = await anki.chunk_notes_info(page_ids)
    return [
        NotePreview(
            note_id=n["noteId"],
            model_name=n["modelName"],
            fields={k: v["value"] for k, v in n["fields"].items()},
            tags=n.get("tags", []),
            cards=n.get("cards", []),
        )
        for n in notes
    ]


@router.get("/{deck_name}/notes/{note_id}/contexts")
async def get_note_contexts(deck_name: str, note_id: int):
    """Return card contexts (prompt/answer interpretation) for a note."""
    anki = AnkiClient()
    try:
        notes = await anki.notes_info([note_id])
    except AnkiConnectError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if not notes:
        raise HTTPException(status_code=404, detail="Note not found.")

    interpreter = CardInterpreter(anki)
    contexts = await interpreter.interpret_note(notes[0])

    return [
        {
            "template_name": ctx.template_name,
            "prompt_field": ctx.prompt_field,
            "answer_field": ctx.answer_field,
            "prompt_plain": ctx.prompt_plain,
            "answer_plain": ctx.answer_plain,
            "rewrite_mode": ctx.rewrite_mode.value,
            "support_level": ctx.support_level.value,
            "card_kind": ctx.card_kind.value,
            "notes": ctx.notes,
            "protected_span_count": len(ctx.protected_spans),
        }
        for ctx in contexts
    ]
