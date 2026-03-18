# NXME

AI-powered appearance improvement social platform.

## Prerequisites

- Python 3.12+
- Docker
- [Supabase CLI](https://supabase.com/docs/guides/cli/getting-started)

## Quick Start

```bash
make up
```

This starts Redis, local Supabase, runs migrations, and launches the API with hot-reload.

- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Supabase Studio: http://localhost:54323

In a second terminal, start the background worker:

```bash
make worker
```

## Commands

| Command | What it does |
|---------|-------------|
| `make up` | Start everything (first-time safe) |
| `make down` | Stop all services |
| `make reset` | Nuke everything and start fresh |
| `make migrate` | Run DB migrations |
| `make worker` | Start ARQ background worker |
| `make test` | Run tests |

## Configuration

On first `make up`, a `.env` is generated with local Supabase defaults and all adapters mocked (no external API calls). Edit `.env` to plug in real API keys for fal.ai, Stripe, AWS, or Anthropic.
