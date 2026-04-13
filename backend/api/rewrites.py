"""API routes: rewrite job management."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.jobs import cancel_job, get_running_jobs, start_rewrite_job, write_back_variants
from backend.storage import NoteRewrite, RewriteJob, ValidationRun, get_session

router = APIRouter(prefix="/rewrites", tags=["rewrites"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CreateJobRequest(BaseModel):
    deck_name: Optional[str] = None
    query: Optional[str] = None
    variant_count: int = Field(default=3, ge=1, le=10)
    distribution: dict[str, int] = Field(default_factory=dict)
    provider_profile_id: Optional[int] = None
    validation_enabled: bool = True
    approval_required: bool = True


class JobResponse(BaseModel):
    id: str
    deck_name: Optional[str]
    query: Optional[str]
    status: str
    variant_count: int
    total_notes: int
    processed_notes: int
    validation_enabled: bool
    approval_required: bool
    created_at: str
    error_message: Optional[str] = None


class NoteRewriteResponse(BaseModel):
    id: int
    job_id: str
    note_id: int
    model_name: str
    template_name: str
    prompt_field: str
    answer_field: str
    original_prompt: str
    original_answer: str
    variants: list[dict]
    status: str
    content_hash: str
    created_at: str


class ApproveVariantsRequest(BaseModel):
    variant_ids: list[str]  # IDs of variants to approve
    write_back: bool = False  # immediately write back to Anki


class RejectRequest(BaseModel):
    note_rewrite_id: int
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/jobs", response_model=JobResponse, status_code=201)
async def create_rewrite_job(
    req: CreateJobRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Create and immediately start a rewrite job."""
    if not req.deck_name and not req.query:
        raise HTTPException(status_code=400, detail="Either deck_name or query is required.")

    job = RewriteJob(
        id=str(uuid.uuid4()),
        deck_name=req.deck_name,
        query=req.query,
        variant_count=req.variant_count,
        distribution=json.dumps(req.distribution),
        provider_profile_id=req.provider_profile_id,
        validation_enabled=req.validation_enabled,
        approval_required=req.approval_required,
        status="pending",
    )
    session.add(job)
    await session.commit()

    # Start the background worker
    background_tasks.add_task(start_rewrite_job, job.id)

    return _job_response(job)


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_session),
):
    """List rewrite jobs, newest first."""
    stmt = select(RewriteJob).order_by(RewriteJob.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(RewriteJob.status == status)
    result = await session.execute(stmt)
    jobs = result.scalars().all()
    return [_job_response(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(RewriteJob).where(RewriteJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _job_response(job)


@router.post("/jobs/{job_id}/cancel")
async def cancel_rewrite_job(job_id: str, session: AsyncSession = Depends(get_session)):
    """Request cancellation of a running job."""
    found = cancel_job(job_id)
    if not found:
        # Mark as cancelled in DB if not in-memory
        await session.execute(
            update(RewriteJob).where(RewriteJob.id == job_id).values(status="cancelled")
        )
        await session.commit()
    return {"status": "cancellation_requested", "job_id": job_id}


@router.get("/jobs/{job_id}/notes", response_model=list[NoteRewriteResponse])
async def list_job_notes(
    job_id: str,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """List NoteRewrite records for a job with optional filters."""
    stmt = (
        select(NoteRewrite)
        .where(NoteRewrite.job_id == job_id)
        .order_by(NoteRewrite.id)
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(NoteRewrite.status == status)

    result = await session.execute(stmt)
    records = result.scalars().all()

    responses = [_note_rewrite_response(r) for r in records]

    # Filter by risk level if requested (filter on variants)
    if risk_level:
        filtered = []
        for resp in responses:
            if any(
                (v.get("validation") or {}).get("risk_level") == risk_level
                for v in resp.variants
            ):
                filtered.append(resp)
        return filtered

    return responses


@router.get("/notes/{note_rewrite_id}", response_model=NoteRewriteResponse)
async def get_note_rewrite(note_rewrite_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(NoteRewrite).where(NoteRewrite.id == note_rewrite_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="NoteRewrite not found.")
    return _note_rewrite_response(record)


@router.post("/notes/{note_rewrite_id}/approve")
async def approve_note_rewrite(
    note_rewrite_id: int,
    req: ApproveVariantsRequest,
    session: AsyncSession = Depends(get_session),
):
    """Approve selected variants and optionally write them back to Anki."""
    result = await session.execute(
        select(NoteRewrite).where(NoteRewrite.id == note_rewrite_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="NoteRewrite not found.")

    await session.execute(
        update(NoteRewrite)
        .where(NoteRewrite.id == note_rewrite_id)
        .values(status="approved")
    )
    await session.commit()

    if req.write_back:
        try:
            wb_result = await write_back_variants(note_rewrite_id)
            return {"status": "written_back", "detail": wb_result}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Write-back failed: {exc}")

    return {"status": "approved"}


@router.post("/notes/{note_rewrite_id}/reject")
async def reject_note_rewrite(
    note_rewrite_id: int,
    req: RejectRequest,
    session: AsyncSession = Depends(get_session),
):
    """Mark a NoteRewrite as rejected."""
    await session.execute(
        update(NoteRewrite)
        .where(NoteRewrite.id == note_rewrite_id)
        .values(status="rejected")
    )
    await session.commit()
    return {"status": "rejected"}


@router.post("/notes/{note_rewrite_id}/write-back")
async def write_back_note(
    note_rewrite_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Write approved variants for this note back to Anki."""
    try:
        result = await write_back_variants(note_rewrite_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/jobs/{job_id}/write-back-all")
async def write_back_all_approved(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Write back all approved NoteRewrite records for a job."""
    result = await session.execute(
        select(NoteRewrite).where(
            NoteRewrite.job_id == job_id,
            NoteRewrite.status == "approved",
        )
    )
    records = result.scalars().all()

    written = 0
    errors: list[str] = []
    for rec in records:
        try:
            await write_back_variants(rec.id)
            written += 1
        except Exception as exc:
            errors.append(f"Note {rec.note_id}: {exc}")

    return {"written": written, "errors": errors}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job_response(job: RewriteJob) -> JobResponse:
    return JobResponse(
        id=job.id,
        deck_name=job.deck_name,
        query=job.query,
        status=job.status,
        variant_count=job.variant_count,
        total_notes=job.total_notes,
        processed_notes=job.processed_notes,
        validation_enabled=job.validation_enabled,
        approval_required=job.approval_required,
        created_at=str(job.created_at),
        error_message=job.error_message,
    )


def _note_rewrite_response(record: NoteRewrite) -> NoteRewriteResponse:
    return NoteRewriteResponse(
        id=record.id,
        job_id=record.job_id,
        note_id=record.note_id,
        model_name=record.model_name,
        template_name=record.template_name,
        prompt_field=record.prompt_field,
        answer_field=record.answer_field,
        original_prompt=record.original_prompt,
        original_answer=record.original_answer,
        variants=json.loads(record.rewrite_data or "[]"),
        status=record.status,
        content_hash=record.content_hash,
        created_at=str(record.created_at),
    )
