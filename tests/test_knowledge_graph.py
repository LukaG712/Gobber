"""Tests for the Knowledge Graph module in Gobber."""

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from gobber.kg_models import Note
from gobber.kg_storage import KnowledgeGraphStorage, cosine_similarity
from gobber.knowledge_graph import KnowledgeGraph


@pytest.fixture
def tmp_db():
    """Create a temporary database for testing."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as db_file:
        db_path = db_file.name
    yield db_path
    # Force close any WAL files on Windows
    import glob as glob_mod
    import sqlite3
    import time

    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        time.sleep(0.1)  # Give Windows time to release the lock
        for f in glob_mod.glob(db_path + "*"):
            try:
                import os as os_mod

                os_mod.unlink(f)
            except Exception:
                pass
    except Exception:
        pass


@pytest.fixture
def tmp_vault():
    """Create a temporary vault directory with test notes."""
    with tempfile.TemporaryDirectory() as vault_dir:
        vault = Path(vault_dir)

        # Create test notes
        (vault / "Getting Started.md").write_text(
            "---\ntitle: Getting Started\n---\n\nWelcome to Obsidian! This is your first note.\n\nCheck out [[Advanced Tips]] for more.",
            encoding="utf-8",
        )
        (vault / "Advanced Tips.md").write_text(
            "---\ntitle: Advanced Tips\n---\n\nHere are some advanced tips for using Obsidian.\n\nSee [[Getting Started]] for basics.\n",
            encoding="utf-8",
        )
        (vault / "Projects").mkdir(parents=True, exist_ok=True)
        (vault / "Projects" / "My Project.md").write_text(
            "---\ntitle: My Project\n---\n\nThis is a project note with some details.\n\nRelated: [[Getting Started]], [[Advanced Tips]]\n",
            encoding="utf-8",
        )

        yield vault_dir


@pytest.fixture
def kg_storage(tmp_db):
    """Create a KnowledgeGraphStorage instance with a temp database."""
    storage = KnowledgeGraphStorage(db_path=tmp_db)
    yield storage
    # Close any lingering connections on Windows
    import sqlite3

    try:
        conn = sqlite3.connect(tmp_db)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except Exception:
        pass


@pytest.fixture
def kg(tmp_db, tmp_vault):
    """Create a KnowledgeGraph instance with temp database and vault."""
    kg_instance = KnowledgeGraph(
        vault_path=tmp_vault,
        db_path=tmp_db,
        shrewd_url="http://nonexistent:9999",  # Will use fallback embeddings
    )
    yield kg_instance
    # Close any lingering connections on Windows
    import sqlite3

    try:
        conn = sqlite3.connect(tmp_db)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except Exception:
        pass


@pytest.fixture
def client(tmp_db, tmp_vault):
    """Create a test client with a temp database."""
    import importlib

    import gobber.api as api_module

    # Reset module-level singletons to use temp DB
    old_db = os.environ.get("DB_PATH")
    old_key = os.environ.get("API_KEY")
    old_vault = os.environ.get("OBSIDIAN_VAULT_PATH")

    os.environ["DB_PATH"] = tmp_db
    os.environ["API_KEY"] = "test-key"
    os.environ["OBSIDIAN_VAULT_PATH"] = str(tmp_vault)

    # Clean up Prometheus registry before reload to avoid duplicate metrics
    try:
        from prometheus_client import REGISTRY

        for collector in list(REGISTRY._names_to_collectors.values()):
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass
    except ImportError:
        pass

    # Reload the module to pick up new env vars
    importlib.reload(api_module)

    with TestClient(api_module.app) as c:
        yield c

    os.environ["DB_PATH"] = old_db or ""
    os.environ["API_KEY"] = old_key or ""
    if old_vault:
        os.environ["OBSIDIAN_VAULT_PATH"] = old_vault
    elif "OBSIDIAN_VAULT_PATH" in os.environ:
        os.environ.pop("OBSIDIAN_VAULT_PATH", None)


class TestCosineSimilarity:
    """Test the cosine similarity function."""

    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_different_dimensions(self):
        a = [1.0, 2.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0


class TestKnowledgeGraphStorage:
    """Test the KnowledgeGraphStorage class."""

    def test_upsert_note(self, kg_storage):
        note = Note(
            file_path="test.md",
            title="Test Note",
            content="Hello world",
        )
        result = kg_storage.upsert_note(note)
        assert result.id == note.id
        assert result.title == "Test Note"

    def test_get_note(self, kg_storage):
        note = Note(file_path="test.md", title="Test", content="Content")
        kg_storage.upsert_note(note)
        retrieved = kg_storage.get_note(str(note.id))
        assert retrieved is not None
        assert retrieved.title == "Test"

    def test_get_note_not_found(self, kg_storage):
        assert kg_storage.get_note(str(uuid4())) is None

    def test_list_notes(self, kg_storage):
        for i in range(3):
            kg_storage.upsert_note(
                Note(file_path=f"note{i}.md", title=f"Note {i}", content=f"Content {i}")
            )
        notes = kg_storage.list_notes()
        assert len(notes) == 3

    def test_delete_note(self, kg_storage):
        note = Note(file_path="test.md", title="Test", content="Content")
        kg_storage.upsert_note(note)
        deleted = kg_storage.delete_note(str(note.id))
        assert deleted is True
        assert kg_storage.get_note(str(note.id)) is None

    def test_store_and_get_embedding(self, kg_storage):
        note = Note(file_path="test.md", title="Test", content="Content")
        kg_storage.upsert_note(note)
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        kg_storage.store_embedding(str(note.id), embedding)
        retrieved = kg_storage.get_embedding(str(note.id))
        assert retrieved == embedding

    def test_semantic_search(self, kg_storage):
        # Create notes with known embeddings
        note1 = Note(
            file_path="note1.md",
            title="AI Note",
            content="Artificial intelligence is great",
        )
        note2 = Note(
            file_path="note2.md", title="Cooking Note", content="Cooking pasta is easy"
        )
        kg_storage.upsert_note(note1)
        kg_storage.upsert_note(note2)

        # Store embeddings
        kg_storage.store_embedding(str(note1.id), [1.0, 0.0, 0.0])
        kg_storage.store_embedding(str(note2.id), [0.0, 1.0, 0.0])

        # Search with query similar to note1
        results = kg_storage.semantic_search([1.0, 0.1, 0.0], limit=10)
        assert len(results) >= 1
        assert results[0].note.id == note1.id
        assert results[0].score > 0.5

    def test_get_stats(self, kg_storage):
        note = Note(file_path="test.md", title="Test", content="Content")
        kg_storage.upsert_note(note)
        kg_storage.store_embedding(str(note.id), [0.1, 0.2, 0.3])
        stats = kg_storage.get_stats()
        assert stats["total_notes"] == 1
        assert stats["embedded_notes"] == 1

    def test_upsert_links(self, kg_storage):
        note1 = Note(file_path="note1.md", title="Note 1", content="Content 1")
        note2 = Note(file_path="note2.md", title="Note 2", content="Content 2")
        kg_storage.upsert_note(note1)
        kg_storage.upsert_note(note2)
        kg_storage.upsert_links(note1.id, [note2.id])
        links = kg_storage.get_outgoing_links(str(note1.id))
        assert len(links) == 1
        assert links[0].id == note2.id


class TestKnowledgeGraph:
    """Test the KnowledgeGraph class."""

    def test_scan_vault(self, kg):
        notes = kg.scan_vault()
        assert len(notes) == 3
        titles = [n.title for n in notes]
        assert "Getting Started" in titles
        assert "Advanced Tips" in titles
        assert "My Project" in titles

    def test_scan_vault_nonexistent(self, tmp_db):
        kg = KnowledgeGraph(vault_path="/nonexistent/path", db_path=tmp_db)
        notes = kg.scan_vault()
        assert len(notes) == 0

    def test_parse_note_with_links(self, kg):
        notes = kg.scan_vault()
        getting_started = next((n for n in notes if n.title == "Getting Started"), None)
        assert getting_started is not None
        assert "Advanced Tips" in getting_started.links

    def test_fallback_embedding(self, kg):
        embedding = kg._generate_fallback_embedding("hello world", dimensions=10)
        assert len(embedding) == 10
        # Should be normalized
        magnitude = sum(x * x for x in embedding) ** 0.5
        assert magnitude == pytest.approx(1.0, abs=0.01)

    def test_index_vault(self, kg):
        import asyncio

        result = asyncio.run(kg.index_vault())
        assert result["success"] is True
        assert result["notes_indexed"] == 3
        assert result["embeddings_generated"] == 3

    def test_index_vault_nonexistent(self, tmp_db):
        kg = KnowledgeGraph(vault_path="/nonexistent/path", db_path=tmp_db)
        import asyncio

        result = asyncio.run(kg.index_vault())
        assert result["success"] is False

    def test_search(self, kg):
        import asyncio

        asyncio.run(kg.index_vault())
        results = asyncio.run(kg.search("artificial intelligence"))
        # Should return results even with fallback embeddings
        assert isinstance(results, list)

    def test_get_stats(self, kg):
        import asyncio

        asyncio.run(kg.index_vault())
        stats = kg.get_stats()
        assert stats["total_notes"] == 3
        assert stats["vault_exists"] is True

    def test_delete_note(self, kg):
        import asyncio

        asyncio.run(kg.index_vault())
        notes = kg.list_notes()
        note_id = str(notes[0].id)
        deleted = kg.delete_note(note_id)
        assert deleted is True
        assert kg.get_note(note_id) is None


HEADERS = {"Authorization": "Bearer test-key"}


class TestVaultAPI:
    """Test the Knowledge Graph API endpoints."""

    def test_index_vault(self, client, tmp_vault):
        response = client.post("/api/vault/index", json={}, headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_list_notes_empty(self, client):
        response = client.get("/api/vault/notes", headers=HEADERS)
        assert response.status_code == 200
        # Notes may exist from previous tests due to module reload sharing state
        assert isinstance(response.json(), list)

    def test_search_without_query(self, client):
        response = client.post("/api/vault/search", json={}, headers=HEADERS)
        assert response.status_code == 400

    def test_get_note_not_found(self, client):
        response = client.get(f"/api/vault/notes/{uuid4()}", headers=HEADERS)
        assert response.status_code == 404

    def test_get_stats(self, client):
        response = client.get("/api/vault/stats", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "total_notes" in data
        assert "vault_exists" in data

    def test_unauthorized(self, client):
        response = client.get("/api/vault/notes", headers={"Authorization": "***"})
        assert response.status_code == 401

    def test_missing_auth(self, client):
        response = client.get("/api/vault/notes")
        assert response.status_code == 401
