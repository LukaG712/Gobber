# Gobber

Persistent storage and knowledge graph. Centralized data layer for webhooks, analytics, RBAC, cache, feature flags, and semantic search.

[MIT License](LICENSE) · Python 3.10+ · FastAPI

---

Gobber is the persistent storage service for the Evershade ecosystem. It provides a centralized data layer solving the in-memory data loss problem when services restart.

**Features:**

- Persistent webhook storage and delivery logs
- Analytics event tracking with filtering
- Role-based access control (RBAC)
- TTL-based cache with Redis backend (falls back to in-memory)
- Dynamic feature flags with targeting
- Obsidian vault integration with semantic search
- Vector embeddings via Shrewd or hash-based fallback
- Prometheus metrics at `/metrics`
- SQLite persistence that survives restarts

---

## Quick Start

### With Docker

```bash
docker compose up -d Gobber
```

### Direct

```bash
pip install -e ".[dev]"
python -m uvicorn gobber.api:app --host 0.0.0.0 --port 8085
```

The API is available at `http://localhost:8085`. Swagger UI at `/docs`.

---

## API Reference

All endpoints require `Authorization: Bearer <API_KEY>` except `/health` and `/metrics`.

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /metrics` | Prometheus metrics |
| `POST /api/webhooks` | Create a webhook |
| `GET /api/webhooks` | List webhooks |
| `GET/PATCH/DELETE /api/webhooks/{id}` | Webhook CRUD |
| `POST /api/analytics/events` | Record an event |
| `GET /api/analytics/events` | Query events |
| `POST /api/flags` | Create a feature flag |
| `GET/PATCH/DELETE /api/flags/{name}` | Flag CRUD |
| `POST /api/cache` | Set cache entry |
| `GET/DELETE /api/cache/{key}` | Cache get/delete |
| `POST /api/roles` | Create a role |
| `GET/DELETE /api/roles/{id}` | Role CRUD |
| `POST /api/vault/index` | Index Obsidian vault |
| `POST /api/vault/search` | Semantic search |
| `GET /api/vault/notes` | List indexed notes |
| `POST /api/embeddings/generate` | Generate embedding |
| `POST /api/embeddings/search` | Semantic search by vector |

**Create a webhook:**

```bash
curl -X POST http://localhost:8085/api/webhooks \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/hook", "events": ["deployment"]}'
```

**Search for notes:**

```bash
curl -X POST http://localhost:8085/api/vault/search \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "artificial intelligence"}'
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | *(required)* | Bearer token for API authentication |
| `PORT` | `8085` | Server port |
| `DB_PATH` | `/app/data/gobber.db` | SQLite database path |
| `REDIS_URL` | `redis://redis:6379/1` | Redis URL for cache (falls back to memory) |
| `OBSIDIAN_VAULT_PATH` | `/app/vault` | Obsidian vault directory |
| `SHREWD_URL` | `http://localhost:8089` | Shrewd LLM service URL |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Model for embeddings |

---

## FAQ

**What is Gobber's role in Evershade?**
The persistent storage service providing webhooks, analytics, RBAC, cache, feature flags, and knowledge graph integration.

**How do I connect my Obsidian vault?**
Set `OBSIDIAN_VAULT_PATH` to your vault directory, then call `POST /api/vault/index`.

**Does Gobber use Redis?**
Optionally. Redis is used for the distributed cache layer. Falls back to in-memory if unavailable.

**How do I backup Gobber data?**
Copy the SQLite database at `DB_PATH` (default `/app/data/gobber.db`).

---

## Support & Community

| Channel | Purpose |
|---------|---------|
| [GitHub Issues](https://github.com/LukaG712/Gobber/issues) | Bug reports and feature requests |
| [Evershade Docs](https://github.com/LukaG712/Evershade) | Comprehensive guides and references |
| [Discussions](https://github.com/LukaG712/Evershade/discussions) | Community discussions and Q&A |

---

## License

This project is licensed under the [MIT License](LICENSE).

---

> **Disclaimer:** This project is a fan-made, independent software project. It is not affiliated with, endorsed by, or in any way connected to Nintendo, Next Level Games, or any of their subsidiaries. All Luigi's Mansion trademarks and character names are property of their respective owners. Service names are used purely for thematic inspiration.
