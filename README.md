# Gobber

> *"You really got to be OCD like the worst guest at an Airbnb ~ get gold, get cash, get blings!"*
> ~ **The Dark Moon Song**, on collecting everything

**Gobber** is the persistent storage service for the Evershade ecosystem. It provides a centralized data layer for webhooks, analytics, RBAC, cache, and feature flags ~ solving the in-memory data loss problem when services restart.

**Luigi's Mansion origin:** *Gobber* ~ blob-like ghosts from Luigi's Mansion: Dark Moon that absorb and store everything in their path.

## Features

- **Webhook Storage** ~ Persistent webhook definitions and delivery logs
- **Analytics** ~ Event tracking and metrics storage
- **RBAC** ~ Role-based access control data
- **Cache** ~ Distributed cache with TTL support
- **Feature Flags** ~ Dynamic feature toggles with targeting rules

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

## Configuration

Set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `Gobber-dev-key-change-me` | API authentication key |
| `PORT` | `8085` | Server port |
| `DB_PATH` | `/app/data/gobber.db` | SQLite database path |
| `REDIS_URL` | `redis://redis:6379/1` | Redis URL for cache layer |

## License

MIT
