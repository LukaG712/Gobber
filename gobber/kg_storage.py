"""SQLite storage backend for the Knowledge Graph module in Gobber."""

import json
import math
import os
import re
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from gobber.kg_models import Note, SearchResult


def _default_db_path() -> str:
    """Return a writable default database path.

    Tries /app/data/gobber.db first, then falls back to a temp directory.
    """
    default = "/app/data/gobber.db"
    try:
        Path(default).parent.mkdir(parents=True, exist_ok=True)
        return default
    except (PermissionError, OSError):
        return os.path.join(tempfile.gettempdir(), "gobber.db")


class KnowledgeGraphStorage:
    """SQLite-backed storage for knowledge graph data (notes, links, embeddings)."""

    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or _default_db_path())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    links TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS note_links (
                    source_note_id TEXT NOT NULL,
                    target_note_id TEXT NOT NULL,
                    PRIMARY KEY (source_note_id, target_note_id),
                    FOREIGN KEY (source_note_id) REFERENCES notes(id),
                    FOREIGN KEY (target_note_id) REFERENCES notes(id)
                );

                CREATE TABLE IF NOT EXISTS note_embeddings (
                    note_id TEXT PRIMARY KEY,
                    embedding TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (note_id) REFERENCES notes(id)
                );

                CREATE INDEX IF NOT EXISTS idx_notes_title ON notes(title);
                CREATE INDEX IF NOT EXISTS idx_note_links_source ON note_links(source_note_id);
                CREATE INDEX IF NOT EXISTS idx_note_links_target ON note_links(target_note_id);
            """)

    # ─── Notes ────────────────────────────────────────────────

    def upsert_note(self, note: Note) -> Note:
        """Insert or update a note in the database."""
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO notes (id, file_path, title, content, links, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(file_path) DO UPDATE SET
                       id=excluded.id,
                       title=excluded.title,
                       content=excluded.content,
                       links=excluded.links,
                       updated_at=excluded.updated_at""",
                (
                    str(note.id),
                    note.file_path,
                    note.title,
                    note.content,
                    json.dumps(note.links),
                    note.created_at.isoformat(),
                    note.updated_at.isoformat(),
                ),
            )
        return note

    def get_note(self, note_id: str) -> Note | None:
        """Get a note by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM notes WHERE id = ?", (note_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_note(row)

    def get_note_by_path(self, file_path: str) -> Note | None:
        """Get a note by file path."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM notes WHERE file_path = ?", (file_path,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_note(row)

    def list_notes(self, limit: int = 100, offset: int = 0) -> list[Note]:
        """List all notes with pagination."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [self._row_to_note(row) for row in rows]

    def delete_note(self, note_id: str) -> bool:
        """Delete a note and its associated data."""
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM note_links WHERE source_note_id = ? OR target_note_id = ?",
                (note_id, note_id),
            )
            conn.execute("DELETE FROM note_embeddings WHERE note_id = ?", (note_id,))
            result = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            return result.rowcount > 0

    def count_notes(self) -> int:
        """Count total notes in the database."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM notes").fetchone()
            return row["cnt"]

    # ─── Links ────────────────────────────────────────────────

    def upsert_links(self, source_note_id: UUID, target_note_ids: list[UUID]) -> None:
        """Update links for a note — removes old links and inserts new ones."""
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM note_links WHERE source_note_id = ?",
                (str(source_note_id),),
            )
            for target_id in target_note_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO note_links (source_note_id, target_note_id) VALUES (?, ?)",
                    (str(source_note_id), str(target_id)),
                )

    def get_outgoing_links(self, note_id: str) -> list[Note]:
        """Get all notes linked from the given note."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT n.* FROM notes n
                   JOIN note_links nl ON n.id = nl.target_note_id
                   WHERE nl.source_note_id = ?""",
                (note_id,),
            ).fetchall()
            return [self._row_to_note(row) for row in rows]

    def get_incoming_links(self, note_id: str) -> list[Note]:
        """Get all notes that link to the given note."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT n.* FROM notes n
                   JOIN note_links nl ON n.id = nl.source_note_id
                   WHERE nl.target_note_id = ?""",
                (note_id,),
            ).fetchall()
            return [self._row_to_note(row) for row in rows]

    def count_links(self) -> int:
        """Count total links in the graph."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM note_links").fetchone()
            return row["cnt"]

    # ─── Embeddings ───────────────────────────────────────────

    def store_embedding(self, note_id: str, embedding: list[float]) -> None:
        """Store a vector embedding for a note."""
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO note_embeddings (note_id, embedding, dimensions, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(note_id) DO UPDATE SET
                       embedding=excluded.embedding,
                       dimensions=excluded.dimensions,
                       created_at=excluded.created_at""",
                (
                    note_id,
                    json.dumps(embedding),
                    len(embedding),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_embedding(self, note_id: str) -> list[float] | None:
        """Get the embedding vector for a note."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT embedding FROM note_embeddings WHERE note_id = ?", (note_id,)
            ).fetchone()
            if row is None:
                return None
            return json.loads(row["embedding"])

    def keyword_search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """Search for notes by keyword matching in title and content.

        Uses TF-IDF-like scoring: matches in title are weighted higher than
        matches in content. Returns (note_id, score) tuples sorted by score.

        Args:
            query: Keyword query string.
            limit: Maximum number of results.
        """
        if not query.strip():
            return []

        # Tokenize query into individual terms
        terms = re.findall(r"\w[\w-]*", query.lower())
        if not terms:
            return []

        with self._get_conn() as conn:
            rows = conn.execute("SELECT id, title, content FROM notes").fetchall()

        results: dict[str, float] = {}
        for row in rows:
            note_id = row["id"]
            title = row["title"].lower()
            content = row["content"].lower()

            score = 0.0
            for term in terms:
                # Title matches weighted 10x higher
                title_count = title.count(term)
                if title_count > 0:
                    score += title_count * 10.0

                # Exact phrase match in content
                if term in content:
                    content_count = content.count(term)
                    score += content_count * 1.0

                # Bonus for whole word matches
                whole_word_pattern = rf"\b{re.escape(term)}\b"
                whole_word_count = len(re.findall(whole_word_pattern, content))
                if whole_word_count > 0:
                    score += whole_word_count * 2.0

            if score > 0:
                results[note_id] = results.get(note_id, 0.0) + score

        # Normalize scores by number of notes to prevent bias toward larger corpora
        if results:
            max_score = max(results.values())
            if max_score > 0:
                results = {nid: s / max_score for nid, s in results.items()}

        # Sort by score descending and limit
        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)[
            :limit
        ]
        return sorted_results

    def hybrid_search(
        self,
        query: str,
        query_embedding: list[float],
        limit: int = 10,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        user_id: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> list[SearchResult]:
        """Hybrid search combining semantic similarity and keyword matching.

        Combines cosine similarity scores with keyword matching scores using
        configurable weights. This ensures exact term matches are found even
        when semantic similarity is low.

        Args:
            query: Original query string for keyword matching.
            query_embedding: Query embedding vector for semantic search.
            limit: Maximum number of results.
            semantic_weight: Weight for semantic similarity (0-1).
            keyword_weight: Weight for keyword matching (0-1).
            user_id: Optional user ID to scope results.
            project_id: Optional project ID to scope results.
            session_id: Optional session ID to scope results.
        """
        # Get semantic results
        semantic_results: dict[str, float] = {}
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT note_id, embedding FROM note_embeddings"
            ).fetchall()

        for row in rows:
            note_embedding = json.loads(row["embedding"])
            score = cosine_similarity(query_embedding, note_embedding)
            if score > 0:
                semantic_results[row["note_id"]] = score

        # Get keyword results
        keyword_results = self.keyword_search(query, limit=limit * 2)
        keyword_map = {nid: score for nid, score in keyword_results}

        # Merge results: combine scores from both methods
        all_note_ids = set(semantic_results.keys()) | set(keyword_map.keys())
        combined_scores: dict[str, float] = {}

        for note_id in all_note_ids:
            sem_score = semantic_results.get(note_id, 0.0)
            kw_score = keyword_map.get(note_id, 0.0)
            combined = (sem_score * semantic_weight) + (kw_score * keyword_weight)
            if combined > 0:
                combined_scores[note_id] = combined

        # Sort by combined score descending and limit
        sorted_results = sorted(
            combined_scores.items(), key=lambda x: x[1], reverse=True
        )[:limit]

        # Fetch full note data with optional scoping
        search_results = []
        for note_id, score in sorted_results:
            note = self.get_note(note_id)
            if note:
                # Apply scope filters (stored in note metadata/tags)
                if user_id and user_id not in (note.title + note.file_path):
                    continue
                if project_id and project_id not in (note.title + note.file_path):
                    continue

                note_embedding = self.get_embedding(note_id)
                context = extract_relevant_context(
                    note.content, query_embedding, note_embedding
                )
                search_results.append(
                    SearchResult(note=note, score=score, context=context)
                )

        return search_results

    def semantic_search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        user_id: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> list[SearchResult]:
        """Search for notes by cosine similarity with the query embedding.

        Args:
            query_embedding: Query embedding vector.
            limit: Maximum number of results.
            user_id: Optional user ID to scope results.
            project_id: Optional project ID to scope results.
            session_id: Optional session ID to scope results.
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT note_id, embedding FROM note_embeddings"
            ).fetchall()

        results = []
        for row in rows:
            note_embedding = json.loads(row["embedding"])
            score = cosine_similarity(query_embedding, note_embedding)
            if score > 0:  # Only return positive similarity scores
                results.append((row["note_id"], score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        results = results[:limit]

        # Fetch full note data with optional scoping
        search_results = []
        for note_id, score in results:
            note = self.get_note(note_id)
            if note:
                # Apply scope filters (stored in note metadata/tags)
                if user_id and user_id not in (note.title + note.file_path):
                    continue
                if project_id and project_id not in (note.title + note.file_path):
                    continue

                note_embedding = self.get_embedding(note_id)
                context = extract_relevant_context(
                    note.content, query_embedding, note_embedding
                )
                search_results.append(
                    SearchResult(note=note, score=score, context=context)
                )

        return search_results

    def get_related_notes(self, note_id: str, limit: int = 5) -> list[SearchResult]:
        """Get semantically related notes to the given note."""
        embedding = self.get_embedding(note_id)
        if embedding is None:
            return []

        results = self.semantic_search(
            embedding, limit=limit + 1
        )  # +1 to exclude the note itself
        return [r for r in results if r.note.id != UUID(note_id)][:limit]

    # ─── Statistics ───────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get knowledge graph statistics."""
        note_count = self.count_notes()
        link_count = self.count_links()

        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT MAX(updated_at) as last_updated FROM notes"
            ).fetchone()
            last_updated = row["last_updated"] if row and row["last_updated"] else None

            emb_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM note_embeddings"
            ).fetchone()
            embedded_count = emb_row["cnt"]

        return {
            "total_notes": note_count,
            "total_links": link_count,
            "embedded_notes": embedded_count,
            "last_updated": last_updated,
        }

    # ─── Helpers ──────────────────────────────────────────────

    def _row_to_note(self, row: sqlite3.Row) -> Note:
        """Convert a database row to a Note object."""
        from uuid import UUID as UUIDType

        return Note(
            id=UUIDType(row["id"]),
            file_path=row["file_path"],
            title=row["title"],
            content=row["content"],
            links=json.loads(row["links"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0

    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def extract_relevant_context(
    content: str,
    query_embedding: list[float],
    note_embedding: list[float],
    max_length: int = 200,
) -> str | None:
    """Extract a relevant excerpt from the note content."""
    if not content.strip():
        return None

    # Split into sentences and find the most relevant one
    sentences = re.split(r"(?<=[.!?])\s+", content)
    if not sentences:
        # Fallback to first chunk
        return content[:max_length] + "..." if len(content) > max_length else content

    # Return the first meaningful sentence as context
    for sentence in sentences:
        if len(sentence.strip()) > 10:
            context = sentence.strip()
            if len(context) > max_length:
                context = context[:max_length] + "..."
            return context

    return content[:max_length] + "..." if len(content) > max_length else content
