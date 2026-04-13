"""API routes: provider profile management."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings as app_settings
from backend.llm_provider import build_provider, encrypt_api_key
from backend.storage import ProviderProfile, get_session

router = APIRouter(prefix="/settings", tags=["settings"])

VALID_KINDS = {"openai", "openai_compatible", "google", "anthropic"}


class ProviderProfileCreate(BaseModel):
    name: str
    provider_kind: str
    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=1, le=32000)
    timeout_seconds: int = Field(default=60, ge=5, le=300)
    concurrency_cap: int = Field(default=3, ge=1, le=20)
    use_structured_output: bool = False


class ProviderProfileResponse(BaseModel):
    id: int
    name: str
    provider_kind: str
    model: str
    base_url: Optional[str]
    temperature: float
    max_tokens: int
    timeout_seconds: int
    concurrency_cap: int
    use_structured_output: bool
    has_api_key: bool
    created_at: str


@router.post("/providers", response_model=ProviderProfileResponse, status_code=201)
async def create_provider(
    req: ProviderProfileCreate,
    session: AsyncSession = Depends(get_session),
):
    if req.provider_kind not in VALID_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider_kind. Must be one of: {list(VALID_KINDS)}",
        )

    # Encrypt the API key before storing
    encrypted_key: Optional[str] = None
    if req.api_key:
        encrypted_key = encrypt_api_key(req.api_key, app_settings.encryption_key)

    profile = ProviderProfile(
        name=req.name,
        provider_kind=req.provider_kind,
        model=req.model,
        base_url=req.base_url,
        api_key_encrypted=encrypted_key,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        timeout_seconds=req.timeout_seconds,
        concurrency_cap=req.concurrency_cap,
        use_structured_output=req.use_structured_output,
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return _profile_response(profile)


@router.get("/providers", response_model=list[ProviderProfileResponse])
async def list_providers(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(ProviderProfile).order_by(ProviderProfile.name)
    )
    profiles = result.scalars().all()
    return [_profile_response(p) for p in profiles]


@router.get("/providers/{profile_id}", response_model=ProviderProfileResponse)
async def get_provider(profile_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(ProviderProfile).where(ProviderProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Provider profile not found.")
    return _profile_response(profile)


@router.put("/providers/{profile_id}", response_model=ProviderProfileResponse)
async def update_provider(
    profile_id: int,
    req: ProviderProfileCreate,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ProviderProfile).where(ProviderProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Provider profile not found.")

    encrypted_key = profile.api_key_encrypted
    if req.api_key:
        encrypted_key = encrypt_api_key(req.api_key, app_settings.encryption_key)

    await session.execute(
        update(ProviderProfile)
        .where(ProviderProfile.id == profile_id)
        .values(
            name=req.name,
            provider_kind=req.provider_kind,
            model=req.model,
            base_url=req.base_url,
            api_key_encrypted=encrypted_key,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            timeout_seconds=req.timeout_seconds,
            concurrency_cap=req.concurrency_cap,
            use_structured_output=req.use_structured_output,
        )
    )
    await session.commit()

    result = await session.execute(
        select(ProviderProfile).where(ProviderProfile.id == profile_id)
    )
    return _profile_response(result.scalar_one())


@router.delete("/providers/{profile_id}", status_code=204)
async def delete_provider(profile_id: int, session: AsyncSession = Depends(get_session)):
    await session.execute(
        delete(ProviderProfile).where(ProviderProfile.id == profile_id)
    )
    await session.commit()


@router.post("/providers/{profile_id}/test")
async def test_provider(profile_id: int, session: AsyncSession = Depends(get_session)):
    """Send a lightweight test request to verify provider connectivity."""
    result = await session.execute(
        select(ProviderProfile).where(ProviderProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Provider profile not found.")

    from backend.llm_provider import decrypt_api_key, profile_to_provider_dict
    profile_dict = profile_to_provider_dict(profile, app_settings.encryption_key)

    try:
        provider = build_provider(profile_dict)
        response = await provider.complete(
            system="You are a test assistant. Reply only with the word 'OK'.",
            user="Reply with exactly: OK",
        )
        return {
            "status": "ok",
            "response_preview": response[:100],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Provider test failed: {exc}",
        )


def _profile_response(p: ProviderProfile) -> ProviderProfileResponse:
    return ProviderProfileResponse(
        id=p.id,
        name=p.name,
        provider_kind=p.provider_kind,
        model=p.model,
        base_url=p.base_url,
        temperature=p.temperature,
        max_tokens=p.max_tokens,
        timeout_seconds=p.timeout_seconds,
        concurrency_cap=p.concurrency_cap,
        use_structured_output=p.use_structured_output,
        has_api_key=bool(p.api_key_encrypted),
        created_at=str(p.created_at),
    )
