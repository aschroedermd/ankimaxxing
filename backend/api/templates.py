"""API routes: template patch management."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.anki_client import AnkiClient, AnkiConnectError
from backend.note_type_registry import classify_note_type
from backend.storage import TemplatePatch, get_session
from backend.template_patch_manager import PatchPlan, TemplateDiff, TemplatePatchManager

router = APIRouter(prefix="/templates", tags=["templates"])


class PatchPlanResponse(BaseModel):
    original_model_name: str
    patched_model_name: str
    fields_to_add: list[str]
    template_diffs: list[dict]
    is_clone: bool
    already_patched: bool
    warnings: list[str]


class ApplyPatchRequest(BaseModel):
    model_name: str
    confirmed: bool = False  # must be True to actually apply


class PatchRecordResponse(BaseModel):
    id: int
    original_model_name: str
    patched_model_name: str
    patch_version: int
    fields_added: list[str]
    status: str
    created_at: str
    rolled_back_at: Optional[str]


@router.get("/plan/{model_name}", response_model=PatchPlanResponse)
async def get_patch_plan(model_name: str):
    """
    Preview what would change if we patch this note type.
    Does NOT modify anything in Anki.
    """
    anki = AnkiClient()
    try:
        field_names = await anki.model_field_names(model_name)
        templates_map = await anki.model_fields_on_templates(model_name)
    except AnkiConnectError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    classification = classify_note_type(
        model_name,
        field_names=field_names,
        template_names=list(templates_map.keys()),
    )

    manager = TemplatePatchManager(anki)
    plan = await manager.build_patch_plan(model_name, classification)

    return PatchPlanResponse(
        original_model_name=plan.original_model_name,
        patched_model_name=plan.patched_model_name,
        fields_to_add=plan.fields_to_add,
        template_diffs=[
            {
                "template_name": d.template_name,
                "original_front": d.original_front,
                "patched_front": d.patched_front,
                "original_back": d.original_back,
                "patched_back": d.patched_back,
            }
            for d in plan.template_diffs
        ],
        is_clone=plan.is_clone,
        already_patched=plan.already_patched,
        warnings=plan.warnings,
    )


@router.post("/apply", response_model=PatchRecordResponse, status_code=201)
async def apply_patch(
    req: ApplyPatchRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Apply a template patch (clone + inject JS) to the given note type.
    Requires confirmed=True as an explicit approval gate.
    """
    if not req.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Set confirmed=true to apply the patch. Review the plan at GET /templates/plan/{model_name} first.",
        )

    anki = AnkiClient()
    try:
        field_names = await anki.model_field_names(req.model_name)
        templates_map = await anki.model_fields_on_templates(req.model_name)
        orig_templates = await anki.model_templates(req.model_name)
    except AnkiConnectError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    classification = classify_note_type(
        req.model_name,
        field_names=field_names,
        template_names=list(templates_map.keys()),
    )

    manager = TemplatePatchManager(anki)
    plan = await manager.build_patch_plan(req.model_name, classification)

    if plan.already_patched:
        # Find existing record
        result = await session.execute(
            select(TemplatePatch).where(
                TemplatePatch.patched_model_name == plan.patched_model_name,
                TemplatePatch.status == "active",
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return _patch_response(existing)

    try:
        apply_result = await manager.apply_patch(plan)
    except AnkiConnectError as exc:
        raise HTTPException(status_code=500, detail=f"AnkiConnect error during patch: {exc}")

    # Store rollback data
    patched_templates: dict = {}
    for diff in plan.template_diffs:
        patched_templates[diff.template_name] = {
            "Front": diff.patched_front,
            "Back": diff.patched_back,
        }

    record = TemplatePatch(
        original_model_name=req.model_name,
        patched_model_name=plan.patched_model_name,
        patch_version=1,
        original_template_html=json.dumps(orig_templates),
        patched_template_html=json.dumps(patched_templates),
        fields_added=json.dumps(plan.fields_to_add),
        status="active",
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    return _patch_response(record)


@router.get("/", response_model=list[PatchRecordResponse])
async def list_patches(session: AsyncSession = Depends(get_session)):
    """Return all template patch records."""
    result = await session.execute(
        select(TemplatePatch).order_by(TemplatePatch.created_at.desc())
    )
    records = result.scalars().all()
    return [_patch_response(r) for r in records]


@router.post("/{patch_id}/rollback")
async def rollback_patch(patch_id: int, session: AsyncSession = Depends(get_session)):
    """
    Roll back a template patch (restores original template HTML).
    Does NOT remove added fields from the note type.
    """
    result = await session.execute(
        select(TemplatePatch).where(TemplatePatch.id == patch_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Patch record not found.")

    if record.status == "rolled_back":
        return {"status": "already_rolled_back"}

    anki = AnkiClient()
    manager = TemplatePatchManager(anki)
    try:
        await manager.rollback_patch(record)
    except AnkiConnectError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    from datetime import datetime
    await session.execute(
        update(TemplatePatch)
        .where(TemplatePatch.id == patch_id)
        .values(status="rolled_back", rolled_back_at=datetime.utcnow())
    )
    await session.commit()

    return {"status": "rolled_back", "patch_id": patch_id}


def _patch_response(r: TemplatePatch) -> PatchRecordResponse:
    return PatchRecordResponse(
        id=r.id,
        original_model_name=r.original_model_name,
        patched_model_name=r.patched_model_name,
        patch_version=r.patch_version,
        fields_added=json.loads(r.fields_added or "[]"),
        status=r.status,
        created_at=str(r.created_at),
        rolled_back_at=str(r.rolled_back_at) if r.rolled_back_at else None,
    )
