"""Tests for Gobber vector embeddings API."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Set API_KEY BEFORE importing the app module
os.environ["API_KEY"] = "test-api-key"

from gobber.api import app


@pytest.fixture
def api_key():
    return "test-api-key"


@pytest.fixture
def auth_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}


class TestEmbeddingGeneration:
    """Test embedding generation endpoint."""

    @pytest.mark.asyncio
    async def test_generate_embedding(self, auth_headers):
        """Should generate an embedding for text."""
        with patch("gobber.api.API_KEY", "test-api-key"):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Mock the embedding generation
                with patch("gobber.api.kg.generate_embedding", new_callable=AsyncMock) as mock_gen:
                    mock_gen.return_value = [0.1, 0.2, 0.3]
                    with patch("gobber.api.kg.embedding_model", "test-model"):
                        response = await client.post(
                            "/api/embeddings/generate",
                            json={"text": "test text"},
                            headers=auth_headers,
                        )
                        assert response.status_code == 200
                        data = response.json()
                        assert "embedding" in data
                        assert "model" in data
                        assert "dimensions" in data
                        assert data["dimensions"] == 3

    @pytest.mark.asyncio
    async def test_generate_embedding_empty_text(self, auth_headers):
        """Should return 400 for empty text."""
        with patch("gobber.api.API_KEY", "test-api-key"):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/embeddings/generate",
                    json={"text": ""},
                    headers=auth_headers,
                )
                assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_generate_embedding_missing_text(self, auth_headers):
        """Should return 400 for missing text."""
        with patch("gobber.api.API_KEY", "test-api-key"):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/embeddings/generate",
                    json={},
                    headers=auth_headers,
                )
                assert response.status_code == 400


class TestEmbeddingSearch:
    """Test embedding search endpoint."""

    @pytest.mark.asyncio
    async def test_search_embeddings(self, auth_headers):
        """Should search embeddings with a query."""
        with patch("gobber.api.API_KEY", "test-api-key"):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                with patch("gobber.api.kg.search", new_callable=AsyncMock) as mock_search:
                    mock_search.return_value = []
                    response = await client.post(
                        "/api/embeddings/search",
                        json={"query": "test query"},
                        headers=auth_headers,
                    )
                    assert response.status_code == 200
                    data = response.json()
                    assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_search_embeddings_empty_query(self, auth_headers):
        """Should return 400 for empty query."""
        with patch("gobber.api.API_KEY", "test-api-key"):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/embeddings/search",
                    json={"query": ""},
                    headers=auth_headers,
                )
                assert response.status_code == 400


class TestEmbeddingStats:
    """Test embedding stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_embedding_stats(self, auth_headers):
        """Should return embedding statistics."""
        with patch("gobber.api.API_KEY", "test-api-key"):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                with patch(
                    "gobber.api.kg.get_stats",
                    return_value={"total_notes": 10, "total_embeddings": 5},
                ):
                    with patch("gobber.api.kg.embedding_model", "test-model"):
                        with patch("gobber.api.kg.shrewd_url", "http://test"):
                            response = await client.get(
                                "/api/embeddings/stats",
                                headers=auth_headers,
                            )
                            assert response.status_code == 200
                            data = response.json()
                            assert "total_notes" in data
                            assert "total_embeddings" in data
                            assert "embedding_model" in data


class TestBatchEmbeddings:
    """Test batch embedding generation."""

    @pytest.mark.asyncio
    async def test_batch_embeddings(self, auth_headers):
        """Should generate embeddings for multiple texts."""
        with patch("gobber.api.API_KEY", "test-api-key"):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                with patch("gobber.api.kg.generate_embedding", new_callable=AsyncMock) as mock_gen:
                    mock_gen.return_value = [0.1, 0.2, 0.3]
                    response = await client.post(
                        "/api/embeddings/batch",
                        json={"texts": ["text1", "text2"]},
                        headers=auth_headers,
                    )
                    assert response.status_code == 200
                    data = response.json()
                    assert isinstance(data, list)
                    assert len(data) == 2

    @pytest.mark.asyncio
    async def test_batch_embeddings_empty(self, auth_headers):
        """Should return 400 for empty texts list."""
        with patch("gobber.api.API_KEY", "test-api-key"):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/embeddings/batch",
                    json={"texts": []},
                    headers=auth_headers,
                )
                assert response.status_code == 400
