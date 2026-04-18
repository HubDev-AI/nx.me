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

## Mobile

**iOS Simulator:**
```bash
cd mobile && npx expo run:ios      # first build (native — required for Sign-In, TikTok)
cd mobile && npx expo start        # JS-only reload after initial build
```

**Physical device:**
1. Set `API_BASE_URL=http://<your-LAN-IP>:8000` in `mobile/.env`
2. `cd mobile && npx expo run:ios` (or `run:android`)

**Android:**
```bash
cd mobile && npx expo run:android
```

## Card Web

Next.js surface for the shareable before/after card (served separately on port 3006).

```bash
make card-web-start
```

Opens on http://localhost:3006. Copy `card-web/.env.local.example` to `card-web/.env.local` and fill in values before first run.

## Commands

### Backend

| Command | What it does |
|---------|-------------|
| `make up` | Start everything (first-time safe) |
| `make down` | Stop all services |
| `make reset` | Nuke everything and start fresh |
| `make migrate` | Run DB migrations |
| `make worker` | Start ARQ background worker |
| `make test` | Run tests |

### Mobile

| Command | What it does |
|---------|-------------|
| `make mobile-ios` | Native build + run on iOS Simulator |
| `make mobile-android` | Native build + run on Android emulator |
| `make mobile-start` | JS-only dev server (after initial native build) |
| `make mobile-lint` | ESLint mobile code |

### Card Web

| Command | What it does |
|---------|-------------|
| `make card-web-start` | Next dev server on port 3006 (auto-installs deps on first run) |
| `make card-web-lint` | `next lint` on web code |

## Configuration

On first `make up`, a `.env` is generated with local Supabase defaults and all adapters mocked (no external API calls). Edit `.env` to plug in real API keys for fal.ai, Stripe, AWS, or Anthropic.
