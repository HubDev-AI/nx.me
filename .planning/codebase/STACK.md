# Technology Stack

**Analysis Date:** 2026-03-17

## Languages

**Primary:**
- Python 3.12 - Backend API and async workers
- TypeScript 5.9 - Mobile native (React Native with Expo)
- TypeScript 5.8 - Web (Next.js 14.2)
- JavaScript - Frontend build tooling

**Secondary:**
- SQL - Database migrations and queries
- Bash - Development scripts

## Runtime

**Environment:**
- Python 3.12-slim (Docker)
- Node.js (Expo, Next.js)
- Uvicorn 0.34.0 - ASGI server for FastAPI

**Package Manager:**
- pip + requirements.txt (Python)
- npm (Node.js projects)
- Lockfiles present for all package managers

## Frameworks

**Core:**
- FastAPI 0.115.12 - REST API framework with async/await
- Uvicorn[standard] 0.34.0 - Production ASGI server (4 workers)
- Expo 55.0.7 - React Native framework (mobile: iOS/Android/web)
- Next.js 14.2.29 - React web framework (card/share page)
- React 18.3.1 - UI framework (web)
- React Native 0.83.2 - Mobile UI framework
- React 19.2.0 - UI framework (Expo)

**Testing:**
- pytest (Python) - Test framework
- Jest or Vitest (implied from ESLint config) - JavaScript testing

**Build/Dev:**
- Docker (multi-stage: base/dev/prod)
- TypeScript compiler (tsconfig.json)
- ESLint 8.57.1 - Linting (Next.js config)
- Next.js built-in build system
- Expo CLI - Mobile bundler

## Key Dependencies

**Critical - Backend:**
- Supabase 2.15.1 - Database + Auth + Storage client (PostgreSQL)
- Redis 5.2.1 - Session store, rate limiting, job queue
- ARQ 0.27.0 - Async job queue (generation processing, advisor nudges)
- PyJWT 2.10.1 - JWT token validation (Supabase auth)
- pydantic-settings 2.9.1 - Configuration management from env vars

**Critical - Image Processing:**
- Pillow 12.1.1 - Image decode/encode
- pillow-heif 0.21.0 - HEIF/AVIF support
- mediapipe 0.10.32 - Face detection/landmarks (FaceMesh)
- insightface 0.7.3 - ArcFace embeddings (identity preservation)
- onnxruntime 1.24.3 - ONNX model runtime (for ArcFace)

**Critical - External APIs:**
- fal-client 0.13.1 - Flux/InstantID image generation
- boto3 1.42.68 - AWS SDK (Rekognition for NSFW screening)
- stripe 14.4.1 - Payment processing
- anthropic (lazy import) - Claude API for advisor

**Infrastructure:**
- httpx 0.28.1 - Async HTTP client (Supabase client dependency)
- psycopg2-binary 2.9.10 - PostgreSQL adapter
- redis.asyncio - Async Redis client

**Utilities:**
- python-slugify 8.0.4 - Username slugification
- numpy 2.4.3 - Numerical operations (MediaPipe dependency)
- disposable-email-domains 0.0.128 - Email validation

## Configuration

**Environment:**
- Pydantic Settings (app/config.py) - Runtime configuration from .env
- Adapter pattern - Pluggable providers (ADAPTER__NSFW_ADAPTER, ADAPTER__IMAGE_GENERATION_ADAPTER, etc.)
- Environment-specific: development, staging, production

**Build:**
- `next.config.mjs` - Next.js configuration (image remotePatterns)
- `tailwind.config.ts` - Tailwind CSS with NXME design tokens
- `postcss.config.mjs` - PostCSS configuration for Tailwind
- `Dockerfile` - Multi-stage Python image
- `docker-compose.yml` (implied) - Local Redis service
- `.eslintrc.*` (implied) - ESLint configuration
- `babel.config.js` - Babel transpilation for Expo

## Platform Requirements

**Development:**
- Docker Desktop or Docker Engine (Redis, Supabase CLI)
- Supabase CLI for local database/auth/storage
- Python 3.12 (pyenv recommended)
- Node.js (for mobile/web tooling)
- Expo CLI (for mobile testing)

**Production:**
- Docker container runtime (Python API)
- PostgreSQL 15+ (Supabase managed database)
- Redis (managed or self-hosted)
- ARQ worker process (separate from API)
- External services: Supabase, Stripe, fal.ai, AWS Rekognition, Anthropic

**Deployment Targets:**
- Backend API: Linux containers (Vercel, Fly.io, ECS, Kubernetes)
- Mobile: iOS TestFlight, Google Play internal testing
- Web/Card: Vercel (Next.js), CloudFront (static assets)

---

*Stack analysis: 2026-03-17*
