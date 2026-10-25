"""Data models for the Knowledge Graph module in Gobber."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


class Note:
    """Represents a single Obsidian note in the knowledge graph."""

    def __init__(
        self,
        file_path: str,
        title: str,
        content: str,
        links: list[str] | None = None,
        id: UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.id = id or uuid4()
        self.file_path = file_path
        self.title = title
        self.content = content
        self.links = links or []
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "file_path": self.file_path,
            "title": self.title,
            "content": self.content,
            "links": self.links,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class NoteLink:
    """Represents a link between two notes (e.g., [[Note Name]])."""

    def __init__(
        self,
        source_note_id: UUID,
        target_note_id: UUID,
    ):
        self.source_note_id = source_note_id
        self.target_note_id = target_note_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_note_id": str(self.source_note_id),
            "target_note_id": str(self.target_note_id),
        }


class SearchResult:
    """Represents a note found by semantic search."""

    def __init__(
        self,
        note: Note,
        score: float,
        context: str | None = None,
    ):
        self.note = note
        self.score = score
        self.context = context

    def to_dict(self) -> dict[str, Any]:
        result = self.note.to_dict()
        result["score"] = self.score
        if self.context:
            result["context"] = self.context
        return result
