"""Data models for Gobber storage service."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class WebhookStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class Webhook:
    def __init__(
        self,
        name: str,
        url: str,
        events: list[str],
        secret: str | None = None,
        is_active: bool = True,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ):
        self.id = id or uuid4()
        self.name = name
        self.url = url
        self.events = events
        self.secret = secret
        self.is_active = is_active
        self.created_at = created_at or datetime.now(UTC)
        self.delivery_count = 0
        self.last_delivery_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "url": self.url,
            "events": self.events,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "delivery_count": self.delivery_count,
            "last_delivery_at": self.last_delivery_at.isoformat()
            if self.last_delivery_at
            else None,
        }


class WebhookDelivery:
    def __init__(
        self,
        webhook_id: UUID,
        event: str,
        payload: dict[str, Any],
        status: WebhookStatus = WebhookStatus.PENDING,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ):
        self.id = id or uuid4()
        self.webhook_id = webhook_id
        self.event = event
        self.payload = payload
        self.status = status
        self.created_at = created_at or datetime.now(UTC)
        self.response_status: int | None = None
        self.error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "webhook_id": str(self.webhook_id),
            "event": self.event,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "response_status": self.response_status,
            "error_message": self.error_message,
        }


class AnalyticsEvent:
    def __init__(
        self,
        event_type: str,
        properties: dict[str, Any],
        service: str | None = None,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ):
        self.id = id or uuid4()
        self.event_type = event_type
        self.properties = properties
        self.service = service
        self.created_at = created_at or datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "event_type": self.event_type,
            "properties": self.properties,
            "service": self.service,
            "created_at": self.created_at.isoformat(),
        }


class FeatureFlag:
    def __init__(
        self,
        name: str,
        is_enabled: bool = False,
        description: str | None = None,
        targeting: dict[str, Any] | None = None,
        id: UUID | None = None,
        created_at: datetime | None = None,
    ):
        self.id = id or uuid4()
        self.name = name
        self.is_enabled = is_enabled
        self.description = description
        self.targeting = targeting or {}
        self.created_at = created_at or datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "is_enabled": self.is_enabled,
            "description": self.description,
            "targeting": self.targeting,
            "created_at": self.created_at.isoformat(),
        }


class CacheEntry:
    def __init__(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
        created_at: datetime | None = None,
    ):
        self.key = key
        self.value = value
        self.ttl_seconds = ttl_seconds
        self.created_at = created_at or datetime.now(UTC)
        self.expires_at = (
            self.created_at + timedelta(seconds=ttl_seconds) if ttl_seconds else None
        )

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "ttl_seconds": self.ttl_seconds,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class Role:
    def __init__(
        self,
        name: str,
        permissions: list[str],
        description: str | None = None,
        id: UUID | None = None,
    ):
        self.id = id or uuid4()
        self.name = name
        self.permissions = permissions
        self.description = description

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "permissions": self.permissions,
            "description": self.description,
        }


class UserRole:
    def __init__(
        self,
        user_id: str,
        role_id: UUID,
        id: UUID | None = None,
    ):
        self.id = id or uuid4()
        self.user_id = user_id
        self.role_id = role_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "role_id": str(self.role_id),
        }
