"""AnkiConnect HTTP client.

Wraps the AnkiConnect JSON-RPC-over-HTTP API (http://localhost:8765).
All public methods are async and raise AnkiConnectError on failure.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from backend.config import settings


class AnkiConnectError(Exception):
    """Raised when AnkiConnect returns an error or is unreachable."""


class AnkiClient:
    """Thin async wrapper around the AnkiConnect API."""

    def __init__(
        self,
        url: str = settings.anki_connect_url,
        version: int = settings.anki_connect_version,
        timeout: float = settings.anki_connect_timeout,
    ) -> None:
        self.url = url
        self.version = version
        self.timeout = timeout

    async def _request(self, action: str, **params: Any) -> Any:
        payload: dict[str, Any] = {"action": action, "version": self.version}
        if params:
            payload["params"] = params

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.url, json=payload)
                resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise AnkiConnectError(
                f"Cannot connect to AnkiConnect at {self.url}. "
                "Is Anki running with the AnkiConnect add-on installed?"
            ) from exc
        except httpx.HTTPError as exc:
            raise AnkiConnectError(f"HTTP error calling AnkiConnect: {exc}") from exc

        data = resp.json()
        if data.get("error"):
            raise AnkiConnectError(f"AnkiConnect error: {data['error']}")
        return data["result"]

    # ------------------------------------------------------------------
    # Connection health
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if AnkiConnect is reachable."""
        try:
            await self._request("version")
            return True
        except AnkiConnectError:
            return False

    async def get_version(self) -> int:
        return await self._request("version")

    # ------------------------------------------------------------------
    # Deck operations
    # ------------------------------------------------------------------

    async def deck_names(self) -> list[str]:
        return await self._request("deckNames")

    async def deck_names_and_ids(self) -> dict[str, int]:
        return await self._request("deckNamesAndIds")

    async def get_deck_stats(self, deck_names: list[str]) -> dict[str, Any]:
        return await self._request("getDeckStats", decks=deck_names)

    # ------------------------------------------------------------------
    # Note search
    # ------------------------------------------------------------------

    async def find_notes(self, query: str) -> list[int]:
        """Return list of note IDs matching an Anki search query."""
        return await self._request("findNotes", query=query)

    async def find_cards(self, query: str) -> list[int]:
        return await self._request("findCards", query=query)

    # ------------------------------------------------------------------
    # Note info
    # ------------------------------------------------------------------

    async def notes_info(self, note_ids: list[int]) -> list[dict[str, Any]]:
        """
        Return full note info for each note ID.

        Each item contains: noteId, modelName, tags, fields, cards.
        fields is a dict of {fieldName: {value: str, order: int}}.
        """
        return await self._request("notesInfo", notes=note_ids)

    async def cards_info(self, card_ids: list[int]) -> list[dict[str, Any]]:
        """Return card scheduling + info for each card ID."""
        return await self._request("cardsInfo", cards=card_ids)

    async def get_note_ids_from_card_ids(self, card_ids: list[int]) -> list[int]:
        return await self._request("cardsToNotes", cards=card_ids)

    # ------------------------------------------------------------------
    # Model (note type) operations
    # ------------------------------------------------------------------

    async def model_names(self) -> list[str]:
        return await self._request("modelNames")

    async def model_names_and_ids(self) -> dict[str, int]:
        return await self._request("modelNamesAndIds")

    async def model_field_names(self, model_name: str) -> list[str]:
        """Return ordered list of field names for a note type."""
        return await self._request("modelFieldNames", modelName=model_name)

    async def model_fields_on_templates(self, model_name: str) -> dict[str, list[list[str]]]:
        """
        Return fields used on each template's front and back.

        Response shape:
          {
            "Card 1": [["Front"], ["Back"]],   # [front_fields, back_fields]
            "Card 2": [["Back"], ["Front"]],
          }
        """
        return await self._request("modelFieldsOnTemplates", modelName=model_name)

    async def model_templates(self, model_name: str) -> dict[str, dict[str, str]]:
        """
        Return raw template HTML for each card template.

        Response shape:
          {
            "Card 1": {"Front": "<front html>", "Back": "<back html>"},
          }
        """
        return await self._request("modelTemplates", modelName=model_name)

    async def model_styling(self, model_name: str) -> dict[str, str]:
        """Return the CSS styling for a note type. Result: {"css": "..."}"""
        return await self._request("modelStyling", modelName=model_name)

    async def find_models_by_name(self, model_names: list[str]) -> list[dict[str, Any]]:
        """Return full model definitions for a list of model names."""
        return await self._request("findModelsByName", modelNames=model_names)

    # ------------------------------------------------------------------
    # Note updates
    # ------------------------------------------------------------------

    async def update_note_fields(self, note_id: int, fields: dict[str, str]) -> None:
        """Update one or more fields of an existing note."""
        await self._request("updateNoteFields", note={"id": note_id, "fields": fields})

    async def add_note(self, note: dict[str, Any]) -> int:
        """Add a new note. Returns the new note ID."""
        return await self._request("addNote", note=note)

    # ------------------------------------------------------------------
    # Model (note type) mutation
    # ------------------------------------------------------------------

    async def create_model(
        self,
        model_name: str,
        fields: list[str],
        css: str,
        card_templates: list[dict[str, Any]],
        is_cloze: bool = False,
    ) -> dict[str, Any]:
        """
        Create a new note type (model).

        card_templates items: {"Name": "...", "Front": "...", "Back": "..."}
        """
        return await self._request(
            "createModel",
            modelName=model_name,
            inOrderFields=fields,
            css=css,
            isCloze=is_cloze,
            cardTemplates=card_templates,
        )

    async def update_model_templates(
        self, model_name: str, templates: dict[str, dict[str, str]]
    ) -> None:
        """
        Update card templates for an existing note type.

        templates: {"Card 1": {"Front": "...", "Back": "..."}}
        """
        await self._request(
            "updateModelTemplates",
            model={"name": model_name, "templates": templates},
        )

    async def update_model_styling(self, model_name: str, css: str) -> None:
        """Replace the CSS for a note type."""
        await self._request(
            "updateModelStyling",
            model={"name": model_name, "css": css},
        )

    async def model_field_add(self, model_name: str, field_name: str, index: int | None = None) -> None:
        """Add a field to an existing note type."""
        params: dict[str, Any] = {"modelName": model_name, "fieldName": field_name}
        if index is not None:
            params["index"] = index
        await self._request("modelFieldAdd", **params)

    async def model_field_remove(self, model_name: str, field_name: str) -> None:
        """Remove a field from an existing note type."""
        await self._request("modelFieldRemove", modelName=model_name, fieldName=field_name)

    # ------------------------------------------------------------------
    # Deck-level note query helpers
    # ------------------------------------------------------------------

    async def get_notes_in_deck(self, deck_name: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Return full note info for all notes in a deck."""
        query = f'deck:"{deck_name}"'
        note_ids = await self.find_notes(query)
        if limit:
            note_ids = note_ids[:limit]
        if not note_ids:
            return []
        return await self.notes_info(note_ids)

    async def get_note_count_in_deck(self, deck_name: str) -> int:
        note_ids = await self.find_notes(f'deck:"{deck_name}"')
        return len(note_ids)

    async def chunk_notes_info(
        self, note_ids: list[int], chunk_size: int = 100
    ) -> list[dict[str, Any]]:
        """Fetch note info in chunks to avoid overwhelming AnkiConnect."""
        results: list[dict[str, Any]] = []
        for i in range(0, len(note_ids), chunk_size):
            chunk = note_ids[i : i + chunk_size]
            results.extend(await self.notes_info(chunk))
        return results
