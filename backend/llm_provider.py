"""LLM provider abstraction.

Supports:
  - OpenAI API
  - OpenAI-compatible endpoints (local inference servers)
  - Google Gemini (via google-genai)
  - Anthropic Claude

Each provider implements BaseLLMProvider.complete() which takes a system
prompt + user prompt and returns a string response.

Provider profiles are loaded from the database and cached.
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """Raised when an LLM call fails after retries."""


class BaseLLMProvider(ABC):
    def __init__(self, profile: dict[str, Any]) -> None:
        self.profile = profile
        self.model = profile.get("model", "")
        self.temperature = profile.get("temperature", 0.7)
        self.max_tokens = profile.get("max_tokens", 2000)
        self.timeout = profile.get("timeout_seconds", 60)

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Return model response text."""

    async def complete_json(self, system: str, user: str) -> Any:
        """Call complete() and parse the result as JSON."""
        raw = await self.complete(system, user)
        raw = raw.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0]
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Provider returned invalid JSON: {exc}\nRaw output: {raw[:500]}") from exc


# ---------------------------------------------------------------------------
# OpenAI provider (also handles OpenAI-compatible endpoints)
# ---------------------------------------------------------------------------

class OpenAIProvider(BaseLLMProvider):
    def __init__(self, profile: dict[str, Any]) -> None:
        super().__init__(profile)
        import openai
        api_key = profile.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        base_url = profile.get("base_url") or None

        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=self.timeout,
            max_retries=0,  # we handle retries ourselves
        )

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def complete(self, system: str, user: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("OpenAI call failed: %s", exc)
            raise LLMError(f"OpenAI error: {exc}") from exc


# ---------------------------------------------------------------------------
# Anthropic Claude provider
# ---------------------------------------------------------------------------

class AnthropicProvider(BaseLLMProvider):
    def __init__(self, profile: dict[str, Any]) -> None:
        super().__init__(profile)
        import anthropic
        api_key = profile.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def complete(self, system: str, user: str) -> str:
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text
        except Exception as exc:
            logger.warning("Anthropic call failed: %s", exc)
            raise LLMError(f"Anthropic error: {exc}") from exc


# ---------------------------------------------------------------------------
# Google Gemini provider
# ---------------------------------------------------------------------------

class GoogleProvider(BaseLLMProvider):
    def __init__(self, profile: dict[str, Any]) -> None:
        super().__init__(profile)
        from google import genai
        api_key = profile.get("api_key") or os.environ.get("GOOGLE_API_KEY", "")
        self._client = genai.Client(api_key=api_key)

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def complete(self, system: str, user: str) -> str:
        from google.genai import types
        try:
            # google-genai uses sync client; wrap in asyncio
            import asyncio
            loop = asyncio.get_event_loop()
            combined = f"{system}\n\n{user}"
            response = await loop.run_in_executor(
                None,
                lambda: self._client.models.generate_content(
                    model=self.model,
                    contents=combined,
                    config=types.GenerateContentConfig(
                        temperature=self.temperature,
                        max_output_tokens=self.max_tokens,
                    ),
                ),
            )
            return response.text or ""
        except Exception as exc:
            logger.warning("Google Gemini call failed: %s", exc)
            raise LLMError(f"Google error: {exc}") from exc


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

_PROVIDER_MAP: dict[str, type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "openai_compatible": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
}


def build_provider(profile: dict[str, Any]) -> BaseLLMProvider:
    """Instantiate the correct provider from a profile dict."""
    kind = profile.get("provider_kind", "openai")
    cls = _PROVIDER_MAP.get(kind)
    if cls is None:
        raise ValueError(f"Unknown provider kind: {kind!r}. Must be one of {list(_PROVIDER_MAP)}")
    return cls(profile)


def decrypt_api_key(encrypted: str | None, encryption_key: str) -> str | None:
    """Decrypt an API key stored in the database."""
    if not encrypted or not encryption_key:
        return encrypted
    try:
        from cryptography.fernet import Fernet
        f = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        return f.decrypt(encrypted.encode()).decode()
    except Exception:
        return encrypted  # return as-is if decryption fails


def encrypt_api_key(plain: str, encryption_key: str) -> str:
    """Encrypt an API key for database storage."""
    if not encryption_key:
        return plain
    from cryptography.fernet import Fernet
    f = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
    return f.encrypt(plain.encode()).decode()


def profile_to_provider_dict(db_profile, encryption_key: str = "") -> dict[str, Any]:
    """Convert a ProviderProfile ORM object to a dict for build_provider()."""
    raw_key = db_profile.api_key_encrypted
    decrypted = decrypt_api_key(raw_key, encryption_key) if raw_key else None
    return {
        "provider_kind": db_profile.provider_kind,
        "model": db_profile.model,
        "base_url": db_profile.base_url,
        "api_key": decrypted,
        "temperature": db_profile.temperature,
        "max_tokens": db_profile.max_tokens,
        "timeout_seconds": db_profile.timeout_seconds,
        "concurrency_cap": db_profile.concurrency_cap,
    }
