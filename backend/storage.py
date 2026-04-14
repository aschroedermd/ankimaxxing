"""SQLAlchemy async models and database initialization."""

import json
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from backend.config import settings


engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ProviderProfile(Base):
    __tablename__ = "provider_profiles"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    provider_kind = Column(String, nullable=False)  # openai | openai_compatible | google | anthropic
    model = Column(String, nullable=False)
    base_url = Column(String, nullable=True)
    api_key_encrypted = Column(Text, nullable=True)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2000)
    timeout_seconds = Column(Integer, default=60)
    concurrency_cap = Column(Integer, default=3)
    use_structured_output = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rewrite_jobs = relationship("RewriteJob", back_populates="provider_profile")


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True)
    # rewrite-conservative | rewrite-moderate | rewrite-aggressive |
    # validate-fidelity | audit-accuracy
    family = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    template = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class RewriteJob(Base):
    __tablename__ = "rewrite_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    deck_name = Column(String, nullable=True)
    query = Column(String, nullable=True)
    variant_count = Column(Integer, default=3)
    # JSON: {"conservative": 1, "moderate": 1, "aggressive": 1}
    distribution = Column(Text, default="{}")
    provider_profile_id = Column(Integer, ForeignKey("provider_profiles.id"), nullable=True)
    validation_enabled = Column(Boolean, default=True)
    approval_required = Column(Boolean, default=True)
    # pending | running | paused | complete | failed | cancelled
    status = Column(String, default="pending")
    total_notes = Column(Integer, default=0)
    processed_notes = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    provider_profile = relationship("ProviderProfile", back_populates="rewrite_jobs")
    note_rewrites = relationship("NoteRewrite", back_populates="job")


class NoteRewrite(Base):
    __tablename__ = "note_rewrites"

    id = Column(Integer, primary_key=True)
    job_id = Column(String, ForeignKey("rewrite_jobs.id"), nullable=False)
    note_id = Column(Integer, nullable=False)
    model_name = Column(String, nullable=False)
    template_name = Column(String, nullable=False)
    prompt_field = Column(String, nullable=False)
    answer_field = Column(String, nullable=False)
    original_prompt = Column(Text, nullable=False)
    original_answer = Column(Text, nullable=False)
    # JSON: array of variant objects
    rewrite_data = Column(Text, default="[]")
    # pending | approved | rejected | written_back | stale | error
    status = Column(String, default="pending")
    content_hash = Column(String, nullable=False)
    prompt_version_id = Column(Integer, ForeignKey("prompt_versions.id"), nullable=True)
    provider_profile_id = Column(Integer, ForeignKey("provider_profiles.id"), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("RewriteJob", back_populates="note_rewrites")
    validation_runs = relationship("ValidationRun", back_populates="note_rewrite")

    @property
    def variants(self) -> list[dict]:
        return json.loads(self.rewrite_data or "[]")

    @variants.setter
    def variants(self, value: list[dict]) -> None:
        self.rewrite_data = json.dumps(value)


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id = Column(Integer, primary_key=True)
    note_rewrite_id = Column(Integer, ForeignKey("note_rewrites.id"), nullable=False)
    variant_id = Column(String, nullable=False)
    # accurate | probably_accurate | possibly_inaccurate | likely_inaccurate | wrong
    rating = Column(String, nullable=False)
    rationale = Column(Text, nullable=True)
    accept_for_writeback = Column(Boolean, nullable=True)
    # low | medium | high
    risk_level = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    note_rewrite = relationship("NoteRewrite", back_populates="validation_runs")


class AuditJob(Base):
    __tablename__ = "audit_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    deck_name = Column(String, nullable=True)
    query = Column(String, nullable=True)
    provider_profile_id = Column(Integer, ForeignKey("provider_profiles.id"), nullable=True)
    # pending | running | paused | complete | failed | cancelled
    status = Column(String, default="pending")
    total_notes = Column(Integer, default=0)
    processed_notes = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to results
    results = relationship("AuditResult", back_populates="job")


class AuditResult(Base):
    __tablename__ = "audit_results"

    id = Column(Integer, primary_key=True)
    job_id = Column(String, ForeignKey("audit_jobs.id"), nullable=True)
    note_id = Column(Integer, nullable=False)
    model_name = Column(String, nullable=True)
    # accurate | probably_accurate | possibly_inaccurate | likely_inaccurate | wrong
    overall_score = Column(String, nullable=False)
    rationale = Column(Text, nullable=True)
    # JSON array of category tags
    category_tags = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("AuditJob", back_populates="results")

    @property
    def tags(self) -> list[str]:
        return json.loads(self.category_tags or "[]")


class TemplatePatch(Base):
    __tablename__ = "template_patches"

    id = Column(Integer, primary_key=True)
    original_model_name = Column(String, nullable=False)
    patched_model_name = Column(String, nullable=False)
    patch_version = Column(Integer, default=1)
    # JSON: {template_name: {front: str, back: str}}
    original_template_html = Column(Text, nullable=False)
    patched_template_html = Column(Text, nullable=False)
    # JSON array of field names added
    fields_added = Column(Text, nullable=False)
    # active | rolled_back
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    rolled_back_at = Column(DateTime, nullable=True)


class AppEvent(Base):
    __tablename__ = "app_events"

    id = Column(Integer, primary_key=True)
    event_type = Column(String, nullable=False)
    payload = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """FastAPI dependency: yield a database session."""
    async with async_session_factory() as session:
        yield session


async def log_event(session: AsyncSession, event_type: str, payload: Any = None) -> None:
    event = AppEvent(
        event_type=event_type,
        payload=json.dumps(payload) if payload is not None else None,
    )
    session.add(event)
    await session.commit()
