"""Core knowledge graph logic: vault scanning, embedding generation, and index management."""

import asyncio
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx

from gobber.kg_models import Note, SearchResult
from gobber.kg_storage import KnowledgeGraphStorage

logger = logging.getLogger(__name__)

# Regex to extract [[links]] from Obsidian markdown
LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")

# Regex to extract YAML frontmatter
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class KnowledgeGraph:
    """Manages the Obsidian vault knowledge graph."""

    def __init__(
        self,
        vault_path: str | None = None,
        db_path: str | None = None,
        shrewd_url: str | None = None,
        shrewd_api_key: str | None = None,
        embedding_model: str = "nomic-embed-text",
    ):
        self.vault_path = Path(vault_path or os.getenv("OBSIDIAN_VAULT_PATH", ""))
        self.shrewd_url = shrewd_url or os.getenv("SHREWD_URL", "http://localhost:8089")
        self.shrewd_api_key = shrewd_api_key or os.getenv("SHREWD_API_KEY", "")
        self.embedding_model = embedding_model or os.getenv(
            "EMBEDDING_MODEL", "nomic-embed-text"
        )
        self.storage = KnowledgeGraphStorage(db_path or os.getenv("DB_PATH"))
        self._note_title_map: dict[
            str, UUID
        ] = {}  # Maps note titles to IDs for link resolution
        self._http_client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create a reusable httpx.AsyncClient for Shrewd API calls."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=60.0)
        return self._http_client

    async def close(self) -> None:
        """Close the reusable httpx client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    def scan_vault(self) -> list[Note]:
        """Scan the Obsidian vault directory for .md files and parse them."""
        if not self.vault_path.exists():
            logger.warning(f"Vault path does not exist: {self.vault_path}")
            return []

        notes = []
        md_files = list(self.vault_path.rglob("*.md"))

        for md_file in md_files:
            try:
                note = self._parse_note(md_file)
                if note:
                    notes.append(note)
            except Exception as e:
                logger.error(f"Failed to parse {md_file}: {e}")

        logger.info(f"Scanned {len(notes)} notes from {len(md_files)} .md files")
        return notes

    def _parse_note(self, file_path: Path) -> Note | None:
        """Parse a single markdown file into a Note object."""
        content = file_path.read_text(encoding="utf-8")
        relative_path = str(file_path.relative_to(self.vault_path))

        # Extract frontmatter
        title = file_path.stem
        match = FRONTMATTER_PATTERN.match(content)
        if match:
            frontmatter_str = match.group(1)
            # Simple YAML-like parsing for title
            for line in frontmatter_str.split("\n"):
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"').strip("'")
                    break

        # Extract [[links]]
        links = LINK_PATTERN.findall(content)

        # Remove frontmatter from content for cleaner storage
        clean_content = FRONTMATTER_PATTERN.sub("", content).strip()

        # Check if note already exists
        existing = self.storage.get_note_by_path(relative_path)
        now = datetime.now(UTC)

        if existing:
            return Note(
                id=existing.id,
                file_path=relative_path,
                title=title,
                content=clean_content,
                links=links,
                created_at=existing.created_at,
                updated_at=now,
            )
        else:
            return Note(
                file_path=relative_path,
                title=title,
                content=clean_content,
                links=links,
                created_at=now,
                updated_at=now,
            )

    async def generate_embedding(self, text: str) -> list[float] | None:
        """Generate an embedding vector for the given text using Shrewd service."""
        if not text.strip():
            return None

        try:
            client = self._get_client()
            headers = {}
            if self.shrewd_api_key:
                headers["X-API-Key"] = self.shrewd_api_key

            response = await client.post(
                f"{self.shrewd_url}/api/embed",
                json={
                    "text": text[:8000],  # Truncate to avoid token limits
                    "model": self.embedding_model,
                },
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("embedding", data.get("vector"))
            else:
                logger.warning(
                    f"Shrewd embedding failed: {response.status_code} {response.text}"
                )
                return None
        except Exception as e:
            logger.warning(f"Failed to generate embedding via Shrewd: {e}")
            return None

    async def generate_embeddings_batch(
        self, texts: list[str], batch_size: int = 10
    ) -> list[list[float] | None]:
        """Generate embeddings for multiple texts in a single batch request.

        Falls back to individual requests if batch endpoint is not supported.
        Returns a list of embeddings (None for failed texts).
        """
        if not texts:
            return []

        results: list[list[float] | None] = []

        try:
            client = self._get_client()
            headers = {}
            if self.shrewd_api_key:
                headers["X-API-Key"] = self.shrewd_api_key

            # Try batch endpoint first
            truncated = [t[:8000] for t in texts]
            response = await client.post(
                f"{self.shrewd_url}/api/embed/batch",
                json={
                    "texts": truncated,
                    "model": self.embedding_model,
                },
                headers=headers,
            )

            if response.status_code == 200:
                data = response.json()
                embeddings = data.get("embeddings", data.get("vectors", []))
                # Ensure we have the right number of results
                while len(embeddings) < len(texts):
                    embeddings.append(None)
                return embeddings[: len(texts)]
            else:
                logger.warning(
                    f"Shrewd batch embedding failed: {response.status_code}, falling back to individual"
                )
        except Exception as e:
            logger.warning(f"Batch embedding failed, falling back to individual: {e}")

        # Fallback: process in batches with individual requests
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            tasks = [self.generate_embedding(text) for text in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.warning(f"Embedding failed: {result}")
                    results.append(None)
                else:
                    results.append(result)

        return results

    def _generate_fallback_embedding(
        self, text: str, dimensions: int = 384
    ) -> list[float]:
        """Generate a simple hash-based fallback embedding when Shrewd is unavailable."""
        import hashlib

        words = text.lower().split()
        embedding = [0.0] * dimensions

        for word in words:
            hash_bytes = hashlib.md5(word.encode()).digest()
            for i in range(dimensions):
                embedding[i] += int(hash_bytes[i % len(hash_bytes)]) / 255.0 - 0.5

        # Normalize
        magnitude = sum(x * x for x in embedding) ** 0.5
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]

        return embedding

    async def index_vault(self, reindex: bool = False) -> dict:
        """Index the entire vault: scan, store notes, generate embeddings, resolve links."""
        if not self.vault_path.exists():
            return {
                "success": False,
                "error": f"Vault path does not exist: {self.vault_path}",
            }

        stats = {
            "notes_indexed": 0,
            "embeddings_generated": 0,
            "links_resolved": 0,
            "errors": 0,
        }

        # Scan vault
        notes = self.scan_vault()
        if not notes:
            return {"success": True, **stats}

        # Build title map for link resolution
        self._note_title_map = {}
        for note in notes:
            self._note_title_map[note.title.lower()] = note.id
            # Also map file path stems
            stem = note.file_path.replace(".md", "").lower()
            self._note_title_map[stem] = note.id

        # Store each note and resolve links
        for note in notes:
            try:
                self.storage.upsert_note(note)
                stats["notes_indexed"] += 1

                # Resolve links
                resolved_links = self._resolve_links(note)
                if resolved_links:
                    self.storage.upsert_links(note.id, resolved_links)
                    stats["links_resolved"] += len(resolved_links)

            except Exception as e:
                logger.error(f"Failed to index note {note.title}: {e}")
                stats["errors"] += 1

        # Generate embeddings in batch for efficiency
        if notes:
            try:
                texts = [note.content for note in notes]
                embeddings = await self.generate_embeddings_batch(texts)

                for note, embedding in zip(notes, embeddings):
                    if embedding is None:
                        # Fallback embedding
                        embedding = self._generate_fallback_embedding(note.content)
                        logger.info(f"Using fallback embedding for {note.title}")

                    self.storage.store_embedding(str(note.id), embedding)
                    stats["embeddings_generated"] += 1
            except Exception as e:
                logger.error(f"Batch embedding failed, falling back to individual: {e}")
                # Fallback: generate embeddings one by one
                for note in notes:
                    try:
                        embedding = await self.generate_embedding(note.content)
                        if embedding is None:
                            embedding = self._generate_fallback_embedding(note.content)
                        self.storage.store_embedding(str(note.id), embedding)
                        stats["embeddings_generated"] += 1
                    except Exception as e:
                        logger.error(
                            f"Failed to generate embedding for {note.title}: {e}"
                        )

        return {"success": True, **stats}

    def _resolve_links(self, note: Note) -> list[UUID]:
        """Resolve [[links]] to actual note IDs."""
        resolved = []
        for link_title in note.links:
            # Handle | alias syntax: [[Note Title|Display Name]]
            actual_title = link_title.split("|")[0].strip()
            lower_title = actual_title.lower()

            if lower_title in self._note_title_map:
                resolved.append(self._note_title_map[lower_title])

        return resolved

    async def search(
        self,
        query: str,
        limit: int = 10,
        user_id: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        use_hybrid: bool = True,
    ) -> list[SearchResult]:
        """Search notes using hybrid semantic + keyword matching.

        By default uses hybrid search which combines cosine similarity with
        keyword matching. Falls back to semantic-only if hybrid is disabled.

        Args:
            query: Search query text.
            limit: Maximum number of results.
            user_id: Optional user ID to scope results.
            project_id: Optional project ID to scope results.
            session_id: Optional session ID to scope results.
            use_hybrid: If True, combine semantic and keyword results.
        """
        query_embedding = await self.generate_embedding(query)
        if query_embedding is None:
            query_embedding = self._generate_fallback_embedding(query)

        if use_hybrid:
            return self.storage.hybrid_search(
                query,
                query_embedding,
                limit=limit,
                user_id=user_id,
                project_id=project_id,
                session_id=session_id,
            )

        return self.storage.semantic_search(
            query_embedding,
            limit=limit,
            user_id=user_id,
            project_id=project_id,
            session_id=session_id,
        )

    def get_note(self, note_id: str) -> Note | None:
        """Get a note by ID."""
        return self.storage.get_note(note_id)

    def list_notes(self, limit: int = 100, offset: int = 0) -> list[Note]:
        """List all indexed notes."""
        return self.storage.list_notes(limit=limit, offset=offset)

    def get_note_links(self, note_id: str) -> list[Note]:
        """Get outgoing links from a note."""
        return self.storage.get_outgoing_links(note_id)

    async def get_related_notes(
        self, note_id: str, limit: int = 5
    ) -> list[SearchResult]:
        """Get semantically related notes."""
        return self.storage.get_related_notes(note_id, limit=limit)

    def delete_note(self, note_id: str) -> bool:
        """Delete a note from the index."""
        return self.storage.delete_note(note_id)

    def get_stats(self) -> dict:
        """Get knowledge graph statistics."""
        stats = self.storage.get_stats()
        stats["vault_path"] = str(self.vault_path)
        stats["vault_exists"] = self.vault_path.exists()
        return stats
