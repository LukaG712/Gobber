# Gobber

> *"I'll send all the ghosts and trinkets you collect during your adventure down the Vault for safekeeping. Check 'em out, sonny!"*
> ~ **Prof. E. Gadd**, Luigi's Mansion: Dark Moon

**Gobber** is the persistent storage service for the Evershade ecosystem. It provides a centralized data layer for webhooks, analytics, RBAC, cache, and feature flags ~ solving the in-memory data loss problem when services restart.

**Luigi's Mansion origin:** *Gobber* ~ blob-like ghosts from Luigi's Mansion: Dark Moon that absorb and store everything in their path.

## Features

- **Webhook Storage** ~ Persistent webhook definitions and delivery logs
- **Analytics** ~ Event tracking and metrics storage
- **RBAC** ~ Role-based access control data
- **Cache** ~ Distributed cache with TTL support
- **Feature Flags** ~ Dynamic feature toggles with targeting rules
- **Knowledge Graph** ~ Obsidian vault integration with semantic search

## Knowledge Graph ~ Obsidian Vault Integration

Gobber can scan an Obsidian vault, generate embeddings for each note, and perform semantic search ~ finding relevant notes by meaning rather than keywords.

### How It Works

1. **Scan** ~ Read `.md` files from your Obsidian vault directory
2. **Parse** ~ Extract note content, frontmatter titles, and `[[links]]`
3. **Embed** ~ Generate vector embeddings via Shrewd (or fallback hash-based)
4. **Search** ~ Query notes by meaning using cosine similarity ranking
5. **Traverse** ~ Follow `[[links]]` between notes to discover related context

### Quick Start

```bash
# Mount your Obsidian vault
docker compose up -d Gobber

# Or set the vault path manually
export OBSIDIAN_VAULT_PATH=/path/to/your/obsidian/vault

# Index the vault
curl -X POST "http://localhost:8085/api/vault/index?x_key=Gobber-dev-key-change-me"

# Search for notes
curl -X POST "http://localhost:8085/api/vault/search?x_key=Gobber-dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"query": "artificial intelligence"}'

# Get note links
curl "http://localhost:8085/api/vault/notes/{note_id}/links?x_key=Gobber-dev-key-change-me"

# Get related notes
curl "http://localhost:8085/api/vault/notes/{note_id}/related?x_key=Gobber-dev-key-change-me"
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/vault/index` | Index or re-index the Obsidian vault |
| `GET` | `/api/vault/notes` | List all indexed notes |
| `GET` | `/api/vault/notes/{id}` | Get a specific note |
| `POST` | `/api/vault/search` | Semantic search by query |
| `GET` | `/api/vault/notes/{id}/links` | Get graph links from a note |
| `GET` | `/api/vault/notes/{id}/related` | Get semantically related notes |
| `DELETE` | `/api/vault/notes/{id}` | Remove a note from the index |
| `GET` | `/api/vault/stats` | Indexing statistics |

## Quick Start

```bash
# With Docker
docker compose up -d Gobber

# Direct
pip install -e ".[dev]"
python -m uvicorn gobber.api:app --host 0.0.0.0 --port 8085
```

## API

- **Swagger UI:** `http://localhost:8085/docs`
- **ReDoc:** `http://localhost:8085/redoc`
- **Prometheus Metrics:** `http://localhost:8085/metrics` (no auth, internal scrape)

## Configuration

Set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `Gobber-dev-key-change-me` | API authentication key |
| `PORT` | `8085` | Server port |
| `DB_PATH` | `/app/data/gobber.db` | SQLite database path |
| `REDIS_URL` | `redis://redis:6379/1` | Redis URL for cache layer |
| `OBSIDIAN_VAULT_PATH` | `/app/vault` | Path to Obsidian vault directory |
| `SHREWD_URL` | `http://localhost:8089` | Shrewd LLM service URL for embeddings |
| `SHREWD_API_KEY` | (optional) | Shrewd API key for authentication |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Model name for embedding generation |

## ❓ FAQ

### What is Gobber's role in Evershade?

Gobber is the persistent storage service. It provides a centralized data layer for webhooks, analytics, RBAC, cache, feature flags, and knowledge graph (Obsidian vault) integration.

### How do I connect my Obsidian vault?

Set `OBSIDIAN_VAULT_PATH` to your vault directory, then call `POST /api/vault/index` to scan and embed all notes.

### What does `/api/capabilities` return?

It returns the service name, version, and features: storage, webhooks, analytics, rbac, feature_flags, cache, knowledge_graph, vector_embeddings, obsidian_indexing, prometheus_metrics, opentelemetry.

### Does Gobber use Redis?

Optionally. Redis is used for the distributed cache layer. If Redis is unavailable, Gobber falls back to in-memory cache.

### How do I backup Gobber data?

Copy the SQLite database at `DB_PATH` (default `/app/data/gobber.db`). With Docker: `docker cp gobber:/app/data/gobber.db ./gobber-backup.db`.

## License

MIT

**Repo:** [LukaG712/Gobber](https://github.com/LukaG712/Gobber)

---

> **Disclaimer:** This project is a fan-made, independent software project. It is not affiliated with, endorsed by, or in any way connected to Nintendo, Next Level Games, or any of their subsidiaries. All Luigi's Mansion trademarks and character names are property of their respective owners. Service names are used purely for thematic inspiration.
