"""FastAPI application for Gobber storage service."""

import hmac
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Histogram,
        generate_latest,
    )

    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

from gobber.knowledge_graph import KnowledgeGraph
from gobber.models import (
    AnalyticsEvent,
    CacheEntry,
    FeatureFlag,
    Role,
    UserRole,
    Webhook,
    WebhookDelivery,
)
from gobber.storage import Storage, _default_db_path

_api_key_raw = os.getenv("API_KEY")
if not _api_key_raw:
    raise RuntimeError(
        "API_KEY environment variable is not set. Refusing to start Gobber without a configured API key."
    )
API_KEY = _api_key_raw
storage = Storage(db_path=os.getenv("DB_PATH") or _default_db_path())
kg = KnowledgeGraph()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await kg.close()


# ─── App ────────────────────────────────────────────────────────

app = FastAPI(
    title="Gobber",
    description="Persistent storage service for the Evershade ecosystem",
    version="1.0.0",
    lifespan=lifespan,
)


def verify_bearer(authorization: str | None = Header(None)) -> None:
    """Verify Bearer token in Authorization header."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Use: Authorization: Bearer <key>",
        )
    if not hmac.compare_digest(token, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


# ─── Health ─────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "Gobber"}


# ─── Prometheus Metrics ─────────────────────────────────────────

if HAS_PROMETHEUS:
    gobber_http_requests_total = Counter(
        "gobber_http_requests_total",
        "Total HTTP requests to Gobber",
        ["method", "endpoint", "status"],
    )
    gobber_http_request_duration = Histogram(
        "gobber_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )

    @app.middleware("http")
    async def prometheus_middleware(request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        method = request.method
        endpoint = request.url.path
        start = time.time()
        status = "200"
        try:
            response = await call_next(request)
            status = str(response.status_code)
        except Exception:
            status = "500"
        finally:
            duration = time.time() - start
            gobber_http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
            gobber_http_request_duration.labels(method=method, endpoint=endpoint).observe(duration)
        return response

    @app.get("/metrics")
    async def prometheus_metrics():
        """Prometheus metrics endpoint for Grafana scraping."""
        return Response(
            content=generate_latest().decode("utf-8"),
            media_type=CONTENT_TYPE_LATEST,
        )


@app.get("/api/capabilities")
async def capabilities() -> dict[str, Any]:
    """Return service identification, version, and features."""
    return {
        "service": "Gobber",
        "version": "1.1.0",
        "features": [
            "storage",
            "webhooks",
            "analytics",
            "rbac",
            "feature_flags",
            "cache",
            "knowledge_graph",
            "vector_embeddings",
            "obsidian_indexing",
            "prometheus_metrics",
            "opentelemetry",
        ],
    }


# ─── Webhooks ───────────────────────────────────────────────────


@app.post("/api/webhooks")
async def create_webhook(data: dict[str, Any], authorization: str | None = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    webhook = Webhook(
        name=data["name"],
        url=data["url"],
        events=data.get("events", []),
        secret=data.get("secret"),
        is_active=data.get("is_active", True),
    )
    result = storage.create_webhook(webhook)
    return result.to_dict()


@app.get("/api/webhooks")
async def list_webhooks(active_only: bool = False, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    webhooks = storage.list_webhooks(active_only=active_only)
    return [w.to_dict() for w in webhooks]


@app.get("/api/webhooks/{webhook_id}")
async def get_webhook(webhook_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    webhook = storage.get_webhook(webhook_id)
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook.to_dict()


@app.patch("/api/webhooks/{webhook_id}")
async def update_webhook(
    webhook_id: str,
    data: dict[str, Any],
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    verify_bearer(authorization)
    webhook = storage.update_webhook(webhook_id, **data)
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook.to_dict()


@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str, authorization: str | None = Header(None)) -> dict[str, bool]:
    verify_bearer(authorization)
    deleted = storage.delete_webhook(webhook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"deleted": True}


# ─── Webhook Deliveries ─────────────────────────────────────────


@app.post("/api/webhooks/{webhook_id}/deliveries")
async def create_delivery(
    webhook_id: str,
    data: dict[str, Any],
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    verify_bearer(authorization)
    try:
        wid = uuid.UUID(webhook_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook_id format")
    delivery = WebhookDelivery(
        webhook_id=wid,
        event=data["event"],
        payload=data.get("payload", {}),
    )
    result = storage.create_delivery(delivery)
    return result.to_dict()


@app.get("/api/webhooks/{webhook_id}/deliveries")
async def list_deliveries(
    webhook_id: str,
    limit: int = 50,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    deliveries = storage.list_deliveries(webhook_id=webhook_id, limit=limit)
    return [d.to_dict() for d in deliveries]


# ─── Analytics ──────────────────────────────────────────────────


@app.post("/api/analytics/events")
async def record_event(data: dict[str, Any], authorization: str | None = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    event = AnalyticsEvent(
        event_type=data["event_type"],
        properties=data.get("properties", {}),
        service=data.get("service"),
    )
    result = storage.record_event(event)
    return result.to_dict()


@app.get("/api/analytics/events")
async def query_events(
    event_type: str | None = None,
    service: str | None = None,
    limit: int = 100,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    events = storage.query_events(event_type=event_type, service=service, limit=limit)
    return [e.to_dict() for e in events]


# ─── Feature Flags ──────────────────────────────────────────────


@app.post("/api/flags")
async def create_flag(data: dict[str, Any], authorization: str | None = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    flag = FeatureFlag(
        name=data["name"],
        is_enabled=data.get("is_enabled", False),
        description=data.get("description"),
        targeting=data.get("targeting"),
    )
    result = storage.create_feature_flag(flag)
    return result.to_dict()


@app.get("/api/flags")
async def list_flags(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    flags = storage.list_feature_flags()
    return [f.to_dict() for f in flags]


@app.get("/api/flags/{name}")
async def get_flag(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    flag = storage.get_feature_flag(name)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    return flag.to_dict()


@app.patch("/api/flags/{name}")
async def update_flag(
    name: str,
    data: dict[str, Any],
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    verify_bearer(authorization)
    flag = storage.update_feature_flag(name, **data)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    return flag.to_dict()


@app.delete("/api/flags/{name}")
async def delete_flag(name: str, authorization: str | None = Header(None)) -> dict[str, bool]:
    verify_bearer(authorization)
    deleted = storage.delete_feature_flag(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Flag not found")
    return {"deleted": True}


# ─── Cache ──────────────────────────────────────────────────────


@app.post("/api/cache")
async def set_cache(data: dict[str, Any], authorization: str | None = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    entry = CacheEntry(
        key=data["key"],
        value=data["value"],
        ttl_seconds=data.get("ttl_seconds"),
    )
    result = storage.set_cache(entry)
    return result.to_dict()


@app.get("/api/cache/{key}")
async def get_cache(key: str, authorization: str | None = Header(None)) -> dict[str, Any] | None:
    verify_bearer(authorization)
    entry = storage.get_cache(key)
    if entry is None:
        return None
    return entry.to_dict()


@app.delete("/api/cache/{key}")
async def delete_cache(key: str, authorization: str | None = Header(None)) -> dict[str, bool]:
    verify_bearer(authorization)
    deleted = storage.delete_cache(key)
    return {"deleted": deleted}


# ─── RBAC ───────────────────────────────────────────────────────


@app.post("/api/roles")
async def create_role(data: dict[str, Any], authorization: str | None = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    role = Role(
        name=data["name"],
        permissions=data.get("permissions", []),
        description=data.get("description"),
    )
    result = storage.create_role(role)
    return result.to_dict()


@app.get("/api/roles")
async def list_roles(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    roles = storage.list_roles()
    return [r.to_dict() for r in roles]


@app.get("/api/roles/{role_id}")
async def get_role(role_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    role = storage.get_role(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role.to_dict()


@app.delete("/api/roles/{role_id}")
async def delete_role(role_id: str, authorization: str | None = Header(None)) -> dict[str, bool]:
    verify_bearer(authorization)
    deleted = storage.delete_role(role_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Role not found")
    return {"deleted": True}


@app.post("/api/users/{user_id}/roles")
async def assign_role(
    user_id: str,
    data: dict[str, Any],
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    verify_bearer(authorization)
    from uuid import UUID

    try:
        role_uuid = UUID(data["role_id"])
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid role_id format: {e}")

    user_role = UserRole(user_id=user_id, role_id=role_uuid)
    result = storage.assign_role(user_role)
    return result.to_dict()


@app.get("/api/users/{user_id}/roles")
async def get_user_roles(user_id: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    roles = storage.get_user_roles(user_id)
    return [r.to_dict() for r in roles]


@app.delete("/api/users/{user_id}/roles/{role_id}")
async def revoke_role(
    user_id: str,
    role_id: str,
    authorization: str | None = Header(None),
) -> dict[str, bool]:
    verify_bearer(authorization)
    revoked = storage.revoke_role(user_id, role_id)
    return {"revoked": revoked}


# ─── Knowledge Graph ~ Vault ────────────────────────────────────


@app.post("/api/vault/index")
async def index_vault(
    data: dict[str, Any] | None = None,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    verify_bearer(authorization)
    reindex = (data or {}).get("reindex", False)
    result = await kg.index_vault(reindex=reindex)
    return result


@app.get("/api/vault/notes")
async def list_vault_notes(
    limit: int = 100,
    offset: int = 0,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    notes = kg.list_notes(limit=limit, offset=offset)
    return [n.to_dict() for n in notes]


@app.get("/api/vault/notes/{note_id}")
async def get_vault_note(note_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    note = kg.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note.to_dict()


@app.post("/api/vault/search")
async def search_vault(
    data: dict[str, Any],
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    query = data.get("query", "")
    limit = data.get("limit", 10)
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
    results = await kg.search(query, limit=limit)
    return [r.to_dict() for r in results]


@app.get("/api/vault/notes/{note_id}/links")
async def get_note_links(note_id: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    note = kg.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    links = kg.get_note_links(note_id)
    return [link.to_dict() for link in links]


@app.get("/api/vault/notes/{note_id}/related")
async def get_related_notes(
    note_id: str,
    limit: int = 5,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    note = kg.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    results = await kg.get_related_notes(note_id, limit=limit)
    return [r.to_dict() for r in results]


@app.delete("/api/vault/notes/{note_id}")
async def delete_vault_note(note_id: str, authorization: str | None = Header(None)) -> dict[str, bool]:
    verify_bearer(authorization)
    deleted = kg.delete_note(note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"deleted": True}


@app.get("/api/vault/stats")
async def get_vault_stats(authorization: str | None = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    return kg.get_stats()


# ─── Vector Embeddings ────────────────────────────────────────────


@app.post("/api/embeddings/generate")
async def generate_embedding(
    data: dict[str, Any],
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Generate an embedding vector for the given text.

    Uses Shrewd service for embedding generation with fallback to hash-based embedding.

    Args:
        data: Dict with 'text' key containing the text to embed.
        authorization: Bearer token for authentication.

    Returns:
        Dict with 'embedding' (list of floats) and 'model' used.
    """
    verify_bearer(authorization)
    text = data.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    embedding = await kg.generate_embedding(text)
    model_used = kg.embedding_model

    if embedding is None:
        # Fallback to hash-based embedding
        embedding = kg._generate_fallback_embedding(text)
        model_used = "fallback-hash"

    return {
        "embedding": embedding,
        "model": model_used,
        "dimensions": len(embedding),
    }


@app.post("/api/embeddings/search")
async def search_embeddings(
    data: dict[str, Any],
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    """Semantic search using vector embeddings.

    Converts the query to an embedding and finds similar notes.

    Args:
        data: Dict with 'query' key containing the search query.
        authorization: Bearer token for authentication.

    Returns:
        List of search results with note info and similarity scores.
    """
    verify_bearer(authorization)
    query = data.get("query", "")
    limit = data.get("limit", 10)
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    results = await kg.search(query, limit=limit)
    return [r.to_dict() for r in results]


@app.get("/api/embeddings/stats")
async def get_embedding_stats(
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Get embedding statistics.

    Returns:
        Dict with embedding count, model info, and related stats.
    """
    verify_bearer(authorization)
    stats = kg.get_stats()
    return {
        "total_notes": stats.get("total_notes", 0),
        "total_embeddings": stats.get("total_embeddings", 0),
        "embedding_model": kg.embedding_model,
        "shrewd_url": kg.shrewd_url,
    }


@app.post("/api/embeddings/batch")
async def generate_batch_embeddings(
    data: dict[str, Any],
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    """Generate embeddings for multiple texts in batch.

    Args:
        data: Dict with 'texts' key containing a list of text strings.
        authorization: Bearer token for authentication.

    Returns:
        List of dicts with 'text' and 'embedding' keys.
    """
    verify_bearer(authorization)
    texts = data.get("texts", [])
    if not texts:
        raise HTTPException(status_code=400, detail="Texts list is required")

    results = []
    for text in texts:
        embedding = await kg.generate_embedding(text)
        if embedding is None:
            embedding = kg._generate_fallback_embedding(text)
        results.append(
            {
                "text": text[:100],  # Truncate for response
                "embedding": embedding,
                "dimensions": len(embedding),
            }
        )

    return results
