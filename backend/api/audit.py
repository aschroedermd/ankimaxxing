"""API routes: deck audit mode."""

from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.jobs import run_audit_job
from backend.storage import AuditResult, get_session

router = APIRouter(prefix="/audit", tags=["audit"])


class StartAuditRequest(BaseModel):
    deck_name: Optional[str] = None
    query: Optional[str] = None
    provider_profile_id: int


class AuditResultResponse(BaseModel):
    id: int
    job_id: Optional[str]
    note_id: int
    model_name: Optional[str]
    overall_score: str
    rationale: Optional[str]
    category_tags: list[str]
    created_at: str


class AuditSummary(BaseModel):
    job_id: str
    total: int
    accurate: int
    probably_accurate: int
    possibly_inaccurate: int
    likely_inaccurate: int
    wrong: int


@router.post("/start", status_code=202)
async def start_audit(
    req: StartAuditRequest,
    background_tasks: BackgroundTasks,
):
    """Start a deck audit job in the background."""
    if not req.deck_name and not req.query:
        raise HTTPException(status_code=400, detail="deck_name or query required.")

    job_id = str(uuid.uuid4())
    background_tasks.add_task(
        run_audit_job,
        job_id=job_id,
        deck_name=req.deck_name or "",
        query=req.query,
        provider_id=req.provider_profile_id,
    )
    return {"job_id": job_id, "status": "started"}


@router.get("/results", response_model=list[AuditResultResponse])
async def list_audit_results(
    job_id: Optional[str] = None,
    score: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Return audit results with optional filters."""
    stmt = (
        select(AuditResult)
        .order_by(AuditResult.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if job_id:
        stmt = stmt.where(AuditResult.job_id == job_id)
    if score:
        stmt = stmt.where(AuditResult.overall_score == score)

    result = await session.execute(stmt)
    records = result.scalars().all()

    responses = [_audit_response(r) for r in records]

    # Filter by tag (post-filter since tags are stored as JSON)
    if tag:
        responses = [r for r in responses if tag in r.category_tags]

    return responses


@router.get("/summary/{job_id}", response_model=AuditSummary)
async def audit_summary(job_id: str, session: AsyncSession = Depends(get_session)):
    """Return score distribution for an audit job."""
    result = await session.execute(
        select(AuditResult).where(AuditResult.job_id == job_id)
    )
    records = result.scalars().all()

    counts = {
        "accurate": 0,
        "probably_accurate": 0,
        "possibly_inaccurate": 0,
        "likely_inaccurate": 0,
        "wrong": 0,
    }
    for r in records:
        key = r.overall_score
        if key in counts:
            counts[key] += 1

    return AuditSummary(
        job_id=job_id,
        total=len(records),
        **counts,
    )


@router.get("/results/{result_id}", response_model=AuditResultResponse)
async def get_audit_result(result_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(AuditResult).where(AuditResult.id == result_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Audit result not found.")
    return _audit_response(record)


def _audit_response(r: AuditResult) -> AuditResultResponse:
    return AuditResultResponse(
        id=r.id,
        job_id=r.job_id,
        note_id=r.note_id,
        model_name=r.model_name,
        overall_score=r.overall_score,
        rationale=r.rationale,
        category_tags=json.loads(r.category_tags or "[]"),
        created_at=str(r.created_at),
    )
