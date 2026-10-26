<div align="center">

# Gobber

### Persistent Storage & Knowledge Graph

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-success.svg)]()

<p align="center">
  <strong>Centralized data layer for the Evershade ecosystem.</strong><br>
  Webhooks, analytics, RBAC, cache, feature flags, and semantic search.
</p>

</div>

---

> *"I'll send all the ghosts and trinkets you collect during your adventure down the Vault for safekeeping. Check 'em out, sonny!"*
> ~ **Prof. E. Gadd**, Luigi's Mansion: Dark Moon

**Luigi's Mansion origin:** *Gobber* ~ blob-like ghosts from Luigi's Mansion: Dark Moon that absorb and store everything in their path.

**Gobber** is the persistent storage service for the Evershade ecosystem. It provides a centralized data layer for webhooks, analytics, RBAC, cache, feature flags, and knowledge graph (Obsidian vault) integration ~ solving the in-memory data loss problem when services restart.

---

## Features

| Category | Feature | Description |
|----------|---------|-------------|
| 🔗 **Webhooks** | Persistent storage | Store webhook definitions and delivery logs in SQLite |
| 📊 **Analytics** | Event tracking | Record and query analytics events with filtering |
| 🔐 **RBAC** | Role-based access control | Manage roles, users, and permissions |
| 💾 **Cache** | Distributed cache | TTL-based cache with Redis backend (falls back to in-memory) |
| 🚩 **Feature Flags** | Dynamic toggles | Create, update, and evaluate feature flags with targeting |
| 🧠 **Knowledge Graph** | Obsidian integration | Scan Obsidian vaults, generate embeddings, and perform semantic search |
| 🔢 **Vector Embeddings** | Semantic search | Generate embeddings via Shrewd or hash-based fallback |
| 📈 **Prometheus Metrics** | Grafana scraping | Request rates and latency histograms at `/metrics` |
| 💾 **SQLite Persistence** | Survive restarts | All data persisted to SQLite database |

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

The API is available at `http://localhost:8085`.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Gobber (Port 8085)                 │
│                                                     │
│  ┌───────────┐  ┌───────────┐  ┌──────────────┐   │
│  │ Webhooks  │  │ Analytics │  │    RBAC      │   │
│  │  API      │  │   API     │  │     API      │   │
│  └─────┬─────┘  └─────┬─────┘  └──────┬───────┘   │
│        │              │               │            │
│  ┌─────┴──────────────┴───────────────┴──────┐    │
│  │         SQLite Persistent Storage         │    │
│  └───────────────────────────────────────────┘    │
│                                                     │
│  ┌───────────┐  ┌───────────┐  ┌──────────────┐   │
│  │  Cache    │  │ Feature   │  │  Knowledge   │   │
│  │  API      │  │  Flags    │  │   Graph      │   │
│  └─────┬─────┘  └───────────┘  └──────┬───────┘   │
│        │                              │            │
│        ▼                              ▼            │
│  Redis (optional)          Obsidian Vault          │
│  (falls back to memory)    + Shrewd Embeddings     │
└─────────────────────────────────────────────────────┘
```

---

## API Reference

All API endpoints require `Authorization: Bearer <API_KEY>` authentication, except `/health` and `/metrics`.

- **Swagger UI:** `http://localhost:8085/docs`
- **ReDoc:** `http://localhost:8085/redoc`

### Health & Status

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /health` | No | Basic health check |
| `GET /api/capabilities` | No | Service info and features |
| `GET /metrics` | No | Prometheus metrics for Grafana |

### Webhooks

| Endpoint | Description |
|----------|-------------|
| `POST /api/webhooks` | Create a webhook |
| `GET /api/webhooks` | List webhooks |
| `GET /api/webhooks/{id}` | Get a webhook |
| `PATCH /api/webhooks/{id}` | Update a webhook |
| `DELETE /api/webhooks/{id}` | Delete a webhook |
| `POST /api/webhooks/{id}/deliveries` | Create a webhook delivery log |
| `GET /api/webhooks/{id}/deliveries` | List webhook deliveries |

**Create a webhook:**

```bash
curl -X POST http://localhost:8085/api/webhooks \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/hook", "events": ["deployment"]}'
```

### Analytics

| Endpoint | Description |
|----------|-------------|
| `POST /api/analytics/events` | Record an analytics event |
| `GET /api/analytics/events` | Query analytics events |

**Record an event:**

```bash
curl -X POST http://localhost:8085/api/analytics/events \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"event": "deployment", "data": {"version": "1.0.0"}}'
```

### Feature Flags

| Endpoint | Description |
|----------|-------------|
| `POST /api/flags` | Create a feature flag |
| `GET /api/flags` | List feature flags |
| `GET /api/flags/{name}` | Get a feature flag |
| `PATCH /api/flags/{name}` | Update a feature flag |
| `DELETE /api/flags/{name}` | Delete a feature flag |

### Cache

| Endpoint | Description |
|----------|-------------|
| `POST /api/cache` | Set a cache entry |
| `GET /api/cache/{key}` | Get a cache entry |
| `DELETE /api/cache/{key}` | Delete a cache entry |

### RBAC

| Endpoint | Description |
|----------|-------------|
| `POST /api/roles` | Create a role |
| `GET /api/roles` | List roles |
| `GET /api/roles/{id}` | Get a role |
| `DELETE /api/roles/{id}` | Delete a role |
| `POST /api/users/{user_id}/roles` | Assign a role to a user |
| `GET /api/users/{user_id}/roles` | Get user roles |
| `DELETE /api/users/{user_id}/roles/{role_id}` | Revoke a user role |

### Knowledge Graph

Gobber can scan an Obsidian vault, generate embeddings for each note, and perform semantic search ~ finding relevant notes by meaning rather than keywords.

**How it works:**

1. **Scan** ~ Read `.md` files from your Obsidian vault directory
2. **Parse** ~ Extract note content, frontmatter titles, and `[[links]]`
3. **Embed** ~ Generate vector embeddings via Shrewd (or fallback hash-based)
4. **Search** ~ Query notes by meaning using cosine similarity ranking
5. **Traverse** ~ Follow `[[links]]` between notes to discover related context

| Endpoint | Description |
|----------|-------------|
| `POST /api/vault/index` | Index or re-index the Obsidian vault |
| `GET /api/vault/notes` | List all indexed notes |
| `GET /api/vault/notes/{id}` | Get a specific note |
| `POST /api/vault/search` | Semantic search by query |
| `GET /api/vault/notes/{id}/links` | Get graph links from a note |
| `GET /api/vault/notes/{id}/related` | Get semantically related notes |
| `DELETE /api/vault/notes/{id}` | Remove a note from the index |
| `GET /api/vault/stats` | Indexing statistics |

**Index your vault:**

```bash
curl -X POST http://localhost:8085/api/vault/index \
  -H "Authorization: Bearer $API_KEY"
```

**Search for notes:**

```bash
curl -X POST http://localhost:8085/api/vault/search \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "artificial intelligence"}'
```

### Vector Embeddings

Gobber provides standalone embedding generation and semantic search endpoints.

| Endpoint | Description |
|----------|-------------|
| `POST /api/embeddings/generate` | Generate an embedding vector for text |
| `POST /api/embeddings/search` | Semantic search using vector embeddings |
| `GET /api/embeddings/stats` | Get embedding statistics |
| `POST /api/embeddings/batch` | Generate embeddings for multiple texts |

**Generate an embedding:**

```bash
curl -X POST http://localhost:8085/api/embeddings/generate \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "artificial intelligence"}'
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | *(required)* | 🔐 Bearer token for API authentication |
| `PORT` | `8085` | Server port |
| `DB_PATH` | `/app/data/gobber.db` | SQLite database path |
| `REDIS_URL` | `redis://redis:6379/1` | Redis URL for cache layer (falls back to in-memory) |
| `OBSIDIAN_VAULT_PATH` | `/app/vault` | Path to Obsidian vault directory |
| `SHREWD_URL` | `http://localhost:8089` | Shrewd LLM service URL for embeddings |
| `SHREWD_API_KEY` | *(optional)* | Shrewd API key for authentication |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Model name for embedding generation |

## ❓ FAQ

### What is Gobber's role in Evershade?

Gobber is the persistent storage service. It provides a centralized data layer for webhooks, analytics, RBAC, cache, feature flags, and knowledge graph (Obsidian vault) integration.

### How do I connect my Obsidian vault?

Set `OBSIDIAN_VAULT_PATH` to your vault directory, then call `POST /api/vault/index` to scan and embed all notes.

### What does `/api/capabilities` return?

It returns the service name, version (1.1.0), and features: storage, webhooks, analytics, rbac, feature_flags, cache, knowledge_graph, vector_embeddings, obsidian_indexing, prometheus_metrics, opentelemetry.

### Does Gobber use Redis?

Optionally. Redis is used for the distributed cache layer. If Redis is unavailable, Gobber falls back to in-memory cache.

### How do I backup Gobber data?

Copy the SQLite database at `DB_PATH` (default `/app/data/gobber.db`). With Docker: `docker cp gobber:/app/data/gobber.db ./gobber-backup.db`.

## Support & Community

| Channel | Purpose |
|---------|---------|
| [🐛 GitHub Issues](https://github.com/LukaG712/Gobber/issues) | Bug reports and feature requests |
| [📚 Evershade Docs](https://github.com/LukaG712/Evershade) | Comprehensive guides and references |
| [💬 Discussions](https://github.com/LukaG712/Evershade/discussions) | Community discussions and Q&A |

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">

**Gobber** — Part of the Evershade Ecosystem

> ⚠️ **Disclaimer:** This project is a fan-made, independent software project. It is not affiliated with, endorsed by, or in any way connected to Nintendo, Next Level Games, or any of their subsidiaries. All Luigi's Mansion trademarks and character names are property of their respective owners. Service names are used purely for thematic inspiration.

</div>
