"""Async job queue and worker for rewrite and audit jobs.

Jobs run in the background via asyncio tasks. Each job updates its
status in the database and can be paused/cancelled.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.anki_client import AnkiClient
from backend.card_interpreter import CardInterpreter, RewriteMode
from backend.config import settings
from backend.llm_provider import BaseLLMProvider, build_provider, profile_to_provider_dict
from backend.rewrite_engine import RewriteEngine
from backend.storage import (
    AppEvent,
    AuditResult,
    NoteRewrite,
    PromptVersion,
    ProviderProfile,
    RewriteJob,
    ValidationRun,
    async_session_factory,
    log_event,
)
from backend.validation_engine import ValidationEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory job registry (maps job_id → asyncio.Task)
# ---------------------------------------------------------------------------

_running_jobs: dict[str, asyncio.Task] = {}
_cancel_flags: dict[str, bool] = {}


def cancel_job(job_id: str) -> bool:
    """Request cancellation of a running job. Returns True if found."""
    if job_id in _cancel_flags:
        _cancel_flags[job_id] = True
        return True
    if job_id in _running_jobs:
        _running_jobs[job_id].cancel()
        return True
    return False


def get_running_jobs() -> list[str]:
    return list(_running_jobs.keys())


# ---------------------------------------------------------------------------
# Rewrite job worker
# ---------------------------------------------------------------------------

async def run_rewrite_job(job_id: str) -> None:
    """
    Main worker coroutine for a rewrite job.

    Fetches notes from Anki, generates variants, optionally validates them,
    and writes results to the database.
    """
    _cancel_flags[job_id] = False

    async with async_session_factory() as session:
        # Load job
        result = await session.execute(select(RewriteJob).where(RewriteJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            logger.error("Job %s not found", job_id)
            return

        await _update_job_status(session, job_id, "running")
        logger.info("Starting rewrite job %s", job_id)

        try:
            await _do_rewrite_job(session, job)
            await _update_job_status(session, job_id, "complete")
            await log_event(session, "job_complete", {"job_id": job_id})
        except asyncio.CancelledError:
            await _update_job_status(session, job_id, "cancelled")
            logger.info("Job %s cancelled", job_id)
        except Exception as exc:
            logger.exception("Job %s failed: %s", job_id, exc)
            await _update_job_status(session, job_id, "failed", error=str(exc))
            await log_event(session, "job_failed", {"job_id": job_id, "error": str(exc)})
        finally:
            _running_jobs.pop(job_id, None)
            _cancel_flags.pop(job_id, None)


async def _do_rewrite_job(session: AsyncSession, job: RewriteJob) -> None:
    anki = AnkiClient()

    # Build provider
    provider: Optional[BaseLLMProvider] = None
    if job.provider_profile_id:
        result = await session.execute(
            select(ProviderProfile).where(ProviderProfile.id == job.provider_profile_id)
        )
        profile_row = result.scalar_one_or_none()
        if profile_row:
            profile_dict = profile_to_provider_dict(profile_row, settings.encryption_key)
            provider = build_provider(profile_dict)

    if not provider:
        raise ValueError("No LLM provider configured for this job.")

    rewriter = RewriteEngine(provider)
    validator = ValidationEngine(provider) if job.validation_enabled else None
    interpreter = CardInterpreter(anki)

    # Find notes
    query = job.query or f'deck:"{job.deck_name}"'
    note_ids = await anki.find_notes(query)

    await session.execute(
        update(RewriteJob)
        .where(RewriteJob.id == job.id)
        .values(total_notes=len(note_ids))
    )
    await session.commit()

    processed = 0
    distribution = json.loads(job.distribution or "{}")

    for note_id in note_ids:
        if _cancel_flags.get(job.id):
            break

        try:
            notes = await anki.notes_info([note_id])
            if not notes:
                continue
            note_info = notes[0]

            contexts = await interpreter.interpret_note(note_info)

            for ctx in contexts:
                if ctx.rewrite_mode == RewriteMode.UNSUPPORTED:
                    continue

                variants_raw = await rewriter.generate_variants(
                    ctx,
                    variant_count=job.variant_count,
                    distribution_override=distribution or None,
                )
                variants_data = rewriter.variants_to_storage_format(variants_raw)

                # Validation
                if validator and variants_data:
                    fidelity_results = await validator.validate_all_variants(
                        original_prompt=ctx.prompt_plain,
                        answer=ctx.answer_plain or "",
                        variants=variants_data,
                    )
                    # Merge validation into variant data
                    fid_map = {r.variant_id: r for r in fidelity_results}
                    for v in variants_data:
                        fid = fid_map.get(v["id"])
                        if fid:
                            v["validation"] = {
                                "rating": fid.rating,
                                "rationale": fid.rationale,
                                "accept": fid.accept_for_writeback,
                                "risk_level": fid.risk_level,
                            }

                content_hash = RewriteEngine.content_hash(
                    ctx.prompt_plain, ctx.answer_plain or ""
                )

                # Determine initial status
                if not job.approval_required:
                    # Auto-approve if all variants passed validation
                    all_ok = all(
                        (v.get("validation") or {}).get("accept", True)
                        for v in variants_data
                        if not v.get("error")
                    )
                    status = "approved" if all_ok else "pending"
                else:
                    status = "pending"

                note_rewrite = NoteRewrite(
                    job_id=job.id,
                    note_id=ctx.note_id,
                    model_name=ctx.model_name,
                    template_name=ctx.template_name,
                    prompt_field=ctx.prompt_field,
                    answer_field=ctx.answer_field or "",
                    original_prompt=ctx.prompt_raw,
                    original_answer=ctx.answer_raw or "",
                    rewrite_data=json.dumps(variants_data),
                    status=status,
                    content_hash=content_hash,
                    provider_profile_id=job.provider_profile_id,
                )
                session.add(note_rewrite)

            processed += 1
            await session.execute(
                update(RewriteJob)
                .where(RewriteJob.id == job.id)
                .values(processed_notes=processed)
            )
            await session.commit()

        except Exception as exc:
            logger.warning("Error processing note %s: %s", note_id, exc)
            continue


# ---------------------------------------------------------------------------
# Audit job worker
# ---------------------------------------------------------------------------

async def run_audit_job(job_id: str, deck_name: str, query: Optional[str], provider_id: int) -> None:
    """Audit job: evaluate factual accuracy of all cards in a deck."""
    _cancel_flags[job_id] = False

    async with async_session_factory() as session:
        try:
            result = await session.execute(
                select(ProviderProfile).where(ProviderProfile.id == provider_id)
            )
            profile_row = result.scalar_one_or_none()
            if not profile_row:
                raise ValueError("Provider profile not found.")

            profile_dict = profile_to_provider_dict(profile_row, settings.encryption_key)
            provider = build_provider(profile_dict)
            validator = ValidationEngine(provider)
            anki = AnkiClient()
            interpreter = CardInterpreter(anki)

            search_query = query or f'deck:"{deck_name}"'
            note_ids = await anki.find_notes(search_query)

            for note_id in note_ids:
                if _cancel_flags.get(job_id):
                    break

                try:
                    notes = await anki.notes_info([note_id])
                    if not notes:
                        continue
                    note_info = notes[0]
                    contexts = await interpreter.interpret_note(note_info)

                    if not contexts:
                        continue

                    ctx = contexts[0]
                    audit = await validator.audit_card_accuracy(
                        note_id=ctx.note_id,
                        prompt=ctx.prompt_plain,
                        answer=ctx.answer_plain or "",
                    )

                    audit_record = AuditResult(
                        job_id=job_id,
                        note_id=audit.note_id,
                        model_name=ctx.model_name,
                        overall_score=audit.overall_score,
                        rationale=audit.rationale,
                        category_tags=json.dumps(audit.category_tags),
                    )
                    session.add(audit_record)
                    await session.commit()

                except Exception as exc:
                    logger.warning("Audit error for note %s: %s", note_id, exc)

        except Exception as exc:
            logger.error("Audit job %s failed: %s", job_id, exc)
        finally:
            _cancel_flags.pop(job_id, None)


# ---------------------------------------------------------------------------
# Writeback: push approved variants into Anki
# ---------------------------------------------------------------------------

async def write_back_variants(note_rewrite_id: int) -> dict[str, Any]:
    """
    Push approved variants for a NoteRewrite record into Anki note fields.

    Builds the AIRewriteData JSON structure and calls updateNoteFields.
    """
    anki = AnkiClient()

    async with async_session_factory() as session:
        result = await session.execute(
            select(NoteRewrite).where(NoteRewrite.id == note_rewrite_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError(f"NoteRewrite {note_rewrite_id} not found.")

        variants = json.loads(record.rewrite_data or "[]")

        # Build AIRewriteData JSON
        ai_data = {
            "schema_version": 1,
            "fields": {
                record.prompt_field: {
                    "variants": [
                        {
                            "id": v["id"],
                            "style": v["style"],
                            "text": v["text"],
                            "validation": v.get("validation"),
                        }
                        for v in variants
                        if not v.get("error")
                    ]
                }
            },
            "templates": {
                record.template_name: {
                    "prompt_field": record.prompt_field,
                    "answer_field": record.answer_field,
                }
            },
        }

        # Select a random starting variant (index 0 to start, app can randomize later)
        ai_meta = {
            "schema_version": 1,
            "selected_variant_idx": 0,
            "source_hash": record.content_hash,
        }

        fields_update = {
            settings.ai_rewrite_data_field: json.dumps(ai_data, ensure_ascii=False),
            settings.ai_rewrite_meta_field: json.dumps(ai_meta, ensure_ascii=False),
        }

        await anki.update_note_fields(record.note_id, fields_update)

        await session.execute(
            update(NoteRewrite)
            .where(NoteRewrite.id == note_rewrite_id)
            .values(status="written_back")
        )
        await session.commit()

        return {"status": "written_back", "note_id": record.note_id}


# ---------------------------------------------------------------------------
# Job launcher
# ---------------------------------------------------------------------------

def start_rewrite_job(job_id: str) -> asyncio.Task:
    task = asyncio.create_task(run_rewrite_job(job_id))
    _running_jobs[job_id] = task
    return task


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _update_job_status(
    session: AsyncSession,
    job_id: str,
    status: str,
    error: Optional[str] = None,
) -> None:
    values: dict[str, Any] = {"status": status}
    if error:
        values["error_message"] = error
    await session.execute(
        update(RewriteJob).where(RewriteJob.id == job_id).values(**values)
    )
    await session.commit()
