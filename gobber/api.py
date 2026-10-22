"""FastAPI application for Gobber storage service."""

import os
import hmac
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse

from gobber.models import (
    Webhook,
    WebhookDelivery,
    AnalyticsEvent,
    FeatureFlag,
    CacheEntry,
    Role,
    UserRole,
)
from gobber.storage import Storage
from gobber.knowledge_graph import KnowledgeGraph


# ─── App ────────────────────────────────────────────────────────

app = FastAPI(
    title="Gobber",
    description="Persistent storage service for the Evershade ecosystem",
    version="1.0.0",
)

storage = Storage(db_path=os.getenv("DB_PATH", "/app/data/gobber.db"))
API_KEY = os.getenv("API_KEY", "Gobber-dev-key-change-me")
kg = KnowledgeGraph()


def verify_bearer(authorization: Optional[str] = Header(None)) -> None:
    """Verify Bearer token in Authorization header."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Use: Authorization: Bearer <key>")
    if not hmac.compare_digest(token, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


# ─── Health ─────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "Gobber"}


# ─── Webhooks ───────────────────────────────────────────────────

@app.post("/api/webhooks")
async def create_webhook(data: dict[str, Any], authorization: Optional[str] = Header(None)) -> dict[str, Any]:
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
async def list_webhooks(active_only: bool = False, authorization: Optional[str] = Header(None)) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    webhooks = storage.list_webhooks(active_only=active_only)
    return [w.to_dict() for w in webhooks]


@app.get("/api/webhooks/{webhook_id}")
async def get_webhook(webhook_id: str, authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    webhook = storage.get_webhook(webhook_id)
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook.to_dict()


@app.patch("/api/webhooks/{webhook_id}")
async def update_webhook(
    webhook_id: str,
    data: dict[str, Any],
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    verify_bearer(authorization)
    webhook = storage.update_webhook(webhook_id, **data)
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook.to_dict()


@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str, authorization: Optional[str] = Header(None)) -> dict[str, bool]:
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
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    verify_bearer(authorization)
    delivery = WebhookDelivery(
        webhook_id=__import__("uuid").UUID(webhook_id),
        event=data["event"],
        payload=data.get("payload", {}),
    )
    result = storage.create_delivery(delivery)
    return result.to_dict()


@app.get("/api/webhooks/{webhook_id}/deliveries")
async def list_deliveries(
    webhook_id: str,
    limit: int = 50,
    authorization: Optional[str] = Header(None),
) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    deliveries = storage.list_deliveries(webhook_id=webhook_id, limit=limit)
    return [d.to_dict() for d in deliveries]


# ─── Analytics ──────────────────────────────────────────────────

@app.post("/api/analytics/events")
async def record_event(data: dict[str, Any], authorization: Optional[str] = Header(None)) -> dict[str, Any]:
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
    event_type: Optional[str] = None,
    service: Optional[str] = None,
    limit: int = 100,
    authorization: Optional[str] = Header(None),
) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    events = storage.query_events(event_type=event_type, service=service, limit=limit)
    return [e.to_dict() for e in events]


# ─── Feature Flags ──────────────────────────────────────────────

@app.post("/api/flags")
async def create_flag(data: dict[str, Any], authorization: Optional[str] = Header(None)) -> dict[str, Any]:
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
async def list_flags(authorization: Optional[str] = Header(None)) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    flags = storage.list_feature_flags()
    return [f.to_dict() for f in flags]


@app.get("/api/flags/{name}")
async def get_flag(name: str, authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    flag = storage.get_feature_flag(name)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    return flag.to_dict()


@app.patch("/api/flags/{name}")
async def update_flag(
    name: str,
    data: dict[str, Any],
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    verify_bearer(authorization)
    flag = storage.update_feature_flag(name, **data)
    if flag is None:
        raise HTTPException(status_code=404, detail="Flag not found")
    return flag.to_dict()


@app.delete("/api/flags/{name}")
async def delete_flag(name: str, authorization: Optional[str] = Header(None)) -> dict[str, bool]:
    verify_bearer(authorization)
    deleted = storage.delete_feature_flag(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Flag not found")
    return {"deleted": True}


# ─── Cache ──────────────────────────────────────────────────────

@app.post("/api/cache")
async def set_cache(data: dict[str, Any], authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    entry = CacheEntry(
        key=data["key"],
        value=data["value"],
        ttl_seconds=data.get("ttl_seconds"),
    )
    result = storage.set_cache(entry)
    return result.to_dict()


@app.get("/api/cache/{key}")
async def get_cache(key: str, authorization: Optional[str] = Header(None)) -> Optional[dict[str, Any]]:
    verify_bearer(authorization)
    entry = storage.get_cache(key)
    if entry is None:
        return None
    return entry.to_dict()


@app.delete("/api/cache/{key}")
async def delete_cache(key: str, authorization: Optional[str] = Header(None)) -> dict[str, bool]:
    verify_bearer(authorization)
    deleted = storage.delete_cache(key)
    return {"deleted": deleted}


# ─── RBAC ───────────────────────────────────────────────────────

@app.post("/api/roles")
async def create_role(data: dict[str, Any], authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    role = Role(
        name=data["name"],
        permissions=data.get("permissions", []),
        description=data.get("description"),
    )
    result = storage.create_role(role)
    return result.to_dict()


@app.get("/api/roles")
async def list_roles(authorization: Optional[str] = Header(None)) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    roles = storage.list_roles()
    return [r.to_dict() for r in roles]


@app.get("/api/roles/{role_id}")
async def get_role(role_id: str, authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    role = storage.get_role(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role.to_dict()


@app.delete("/api/roles/{role_id}")
async def delete_role(role_id: str, authorization: Optional[str] = Header(None)) -> dict[str, bool]:
    verify_bearer(authorization)
    deleted = storage.delete_role(role_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Role not found")
    return {"deleted": True}


@app.post("/api/users/{user_id}/roles")
async def assign_role(
    user_id: str,
    data: dict[str, Any],
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    verify_bearer(authorization)
    from uuid import UUID
    user_role = UserRole(user_id=user_id, role_id=UUID(data["role_id"]))
    result = storage.assign_role(user_role)
    return result.to_dict()


@app.get("/api/users/{user_id}/roles")
async def get_user_roles(user_id: str, authorization: Optional[str] = Header(None)) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    roles = storage.get_user_roles(user_id)
    return [r.to_dict() for r in roles]


@app.delete("/api/users/{user_id}/roles/{role_id}")
async def revoke_role(
    user_id: str,
    role_id: str,
    authorization: Optional[str] = Header(None),
) -> dict[str, bool]:
    verify_bearer(authorization)
    revoked = storage.revoke_role(user_id, role_id)
    return {"revoked": revoked}


# ─── Knowledge Graph ~ Vault ────────────────────────────────────

@app.post("/api/vault/index")
async def index_vault(
    data: Optional[dict[str, Any]] = None,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    verify_bearer(authorization)
    reindex = (data or {}).get("reindex", False)
    result = await kg.index_vault(reindex=reindex)
    return result


@app.get("/api/vault/notes")
async def list_vault_notes(
    limit: int = 100,
    offset: int = 0,
    authorization: Optional[str] = Header(None),
) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    notes = kg.list_notes(limit=limit, offset=offset)
    return [n.to_dict() for n in notes]


@app.get("/api/vault/notes/{note_id}")
async def get_vault_note(note_id: str, authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    note = kg.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note.to_dict()


@app.post("/api/vault/search")
async def search_vault(
    data: dict[str, Any],
    authorization: Optional[str] = Header(None),
) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    query = data.get("query", "")
    limit = data.get("limit", 10)
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
    results = await kg.search(query, limit=limit)
    return [r.to_dict() for r in results]


@app.get("/api/vault/notes/{note_id}/links")
async def get_note_links(note_id: str, authorization: Optional[str] = Header(None)) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    note = kg.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    links = kg.get_note_links(note_id)
    return [l.to_dict() for l in links]


@app.get("/api/vault/notes/{note_id}/related")
async def get_related_notes(
    note_id: str,
    limit: int = 5,
    authorization: Optional[str] = Header(None),
) -> list[dict[str, Any]]:
    verify_bearer(authorization)
    note = kg.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    results = await kg.get_related_notes(note_id, limit=limit)
    return [r.to_dict() for r in results]


@app.delete("/api/vault/notes/{note_id}")
async def delete_vault_note(note_id: str, authorization: Optional[str] = Header(None)) -> dict[str, bool]:
    verify_bearer(authorization)
    deleted = kg.delete_note(note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"deleted": True}


@app.get("/api/vault/stats")
async def get_vault_stats(authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    verify_bearer(authorization)
    return kg.get_stats()
