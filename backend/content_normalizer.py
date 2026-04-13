"""Content normalization for LLM consumption.

Responsibilities:
  - Strip HTML tags while preserving structure where meaningful
  - Extract and protect cloze tokens {{cN::...}} from modification
  - Extract and protect media references [sound:...], <img ...>
  - Return plain text for model input + list of protected spans
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup, NavigableString

from backend.note_type_registry import NoteKind


@dataclass
class ProtectedSpan:
    start: int
    end: int
    text: str          # the raw original token
    placeholder: str   # placeholder inserted in normalized text
    kind: str          # "cloze" | "media" | "type_tag"


_CLOZE_RE = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.DOTALL)
_SOUND_RE = re.compile(r"\[sound:[^\]]+\]")
_TYPE_TAG_RE = re.compile(r"\{\{type:[^}]+\}\}")


class ContentNormalizer:
    """Convert raw Anki field HTML to plain text suitable for LLM prompts."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def normalize(
        self,
        raw: str,
        kind: NoteKind = NoteKind.BASIC,
    ) -> tuple[str, list[ProtectedSpan]]:
        """
        Return (plain_text, protected_spans).

        plain_text has protected spans replaced with numbered placeholders.
        protected_spans carries the original text for each placeholder so the
        caller can reinsert them after generation.
        """
        if not raw or not raw.strip():
            return "", []

        if kind == NoteKind.CLOZE:
            return self._normalize_cloze(raw)
        return self._normalize_html(raw)

    def reinsert_protected(self, text: str, spans: list[ProtectedSpan]) -> str:
        """Replace placeholders in LLM-generated text with original tokens."""
        result = text
        for span in spans:
            result = result.replace(span.placeholder, span.text, 1)
        return result

    # ------------------------------------------------------------------
    # HTML normalization
    # ------------------------------------------------------------------

    def _normalize_html(self, raw: str) -> tuple[str, list[ProtectedSpan]]:
        # First pass: protect sound/media tags
        protected: list[ProtectedSpan] = []
        counter = [0]

        def _protect(text: str, kind: str) -> str:
            ph = f"⟦{kind.upper()}_{counter[0]}⟧"
            protected.append(
                ProtectedSpan(
                    start=0, end=0,
                    text=text,
                    placeholder=ph,
                    kind=kind,
                )
            )
            counter[0] += 1
            return ph

        # Protect [sound:...] references
        working = _SOUND_RE.sub(lambda m: _protect(m.group(0), "media"), raw)

        # Parse HTML and extract text
        soup = BeautifulSoup(working, "lxml")
        plain = self._soup_to_text(soup)

        # Collapse whitespace
        plain = re.sub(r"\n{3,}", "\n\n", plain)
        plain = plain.strip()

        return plain, protected

    def _soup_to_text(self, soup: BeautifulSoup) -> str:
        parts: list[str] = []

        def _visit(node):
            if isinstance(node, NavigableString):
                parts.append(str(node))
                return

            tag = node.name.lower() if node.name else ""

            block_tags = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li"}
            if tag == "br":
                parts.append("\n")
                return
            if tag in block_tags:
                # Newline before block elements
                if parts and not parts[-1].endswith("\n"):
                    parts.append("\n")
                for child in node.children:
                    _visit(child)
                parts.append("\n")
                return
            if tag == "ul" or tag == "ol":
                parts.append("\n")
                for child in node.children:
                    _visit(child)
                parts.append("\n")
                return
            if tag in ("script", "style"):
                return  # skip scripts
            for child in node.children:
                _visit(child)

        body = soup.find("body") or soup
        for child in body.children:
            _visit(child)

        return "".join(parts)

    # ------------------------------------------------------------------
    # Cloze normalization
    # ------------------------------------------------------------------

    def _normalize_cloze(self, raw: str) -> tuple[str, list[ProtectedSpan]]:
        """
        For cloze notes, protect {{cN::answer}} tokens so they survive rewriting.

        The LLM sees: "The capital of ⟦CLOZE_0⟧ is Paris."
        After generation, we reinsert the original cloze tokens.
        """
        protected: list[ProtectedSpan] = []
        counter = [0]

        def _protect_cloze(m: re.Match) -> str:
            ph = f"⟦CLOZE_{counter[0]}⟧"
            # preserve the full cloze token exactly
            protected.append(
                ProtectedSpan(
                    start=m.start(),
                    end=m.end(),
                    text=m.group(0),
                    placeholder=ph,
                    kind="cloze",
                )
            )
            counter[0] += 1
            return ph

        # Strip HTML first, but keep cloze tokens
        working = _CLOZE_RE.sub(_protect_cloze, raw)
        # Now strip HTML
        soup = BeautifulSoup(working, "lxml")
        plain = self._soup_to_text(soup)
        plain = re.sub(r"\n{3,}", "\n\n", plain)
        plain = plain.strip()

        return plain, protected

    # ------------------------------------------------------------------
    # Post-processing: validate cloze tokens survived
    # ------------------------------------------------------------------

    def validate_cloze_integrity(
        self, original: str, generated: str, spans: list[ProtectedSpan]
    ) -> list[str]:
        """
        Return a list of error messages if any cloze token is missing
        from the generated text after reinsertion.
        """
        errors: list[str] = []
        cloze_spans = [s for s in spans if s.kind == "cloze"]
        for span in cloze_spans:
            if span.text not in generated:
                errors.append(
                    f"Cloze token was lost during generation: {span.text!r}"
                )
        return errors
