---
title: "feat: Ollama embeddings adapter (decouple from LLM, migrate dim)"
type: feat
status: active
date: 2026-04-16
---

# feat: Ollama embeddings adapter

## Overview

Today the advisor's chat (Anthropic Claude) and embeddings (OpenAI
text-embedding-3-small at 1536 dim) live in one adapter class. To
test the advisor locally without two paid API keys, we want
embeddings via Ollama (`nomic-embed-text`, 768 dim native). Decoupling
the two concerns and adding configurable adapters is the cleanest
fix; otherwise every embedding backend ends up bolted into the LLM
adapter.

## Goals

1. New `EmbeddingPort` Protocol separates embedding inference from LLM chat.
2. Three embedding adapters: `openai`, `ollama`, `mock` — selectable via env.
3. DB column + function migrated to 768 dim.
4. Backend boots end-to-end with `ADAPTER__LLM_ADAPTER=anthropic` + `ADAPTER__EMBEDDING_ADAPTER=ollama` and a real Anthropic key + a running local Ollama.

## Non-goals

- Re-embedding existing memories (dev only — fresh start).
- Adding Ollama LLM chat adapter.
- Changing the chat model defaults or memory retrieval algorithm.
- Adding mock-Ollama for offline tests beyond the unit-level httpx mock.

## Implementation

### Unit 1 — EmbeddingPort + adapters
- `app/advisor/embedding_port.py`: Protocol with `compute_embedding(text) -> list[float]`.
- `app/advisor/adapters/embeddings/`:
  - `openai.py` — calls `openai.embeddings.create(dimensions=settings.EMBEDDING_DIMENSIONS)`.
  - `ollama.py` — calls `POST {OLLAMA_BASE_URL}/api/embeddings` via httpx.AsyncClient.
  - `mock.py` — deterministic vector of `EMBEDDING_DIMENSIONS` length, seeded from text.
- `app/api/deps.py`: `get_embedding_adapter()` selects on `ADAPTER__EMBEDDING_ADAPTER`.

### Unit 2 — Wire embeddings through MemoryManager + AdvisorService
- `MemoryManager.__init__(advisor_repo, embedding_adapter)` — drops `llm_adapter` for embeddings, takes its own port.
- `AdvisorService.__init__(advisor_repo, redis_client, llm_adapter, embedding_adapter)`.
- `get_advisor_service()` in `app/api/advisor.py` injects both adapters.
- Remove `compute_embedding` from `LLMPort`, `AnthropicAdapter`, `MockLLMAdapter`.

### Unit 3 — Config + env
- Settings: `ADAPTER__EMBEDDING_ADAPTER` (default `openai`), `OLLAMA_BASE_URL`, `OLLAMA_EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` (default `768`).
- `app/.env`: set local dev to ollama + 768.
- `app/.env.example`: document all four + add the missing `OPENAI_API_KEY`.

### Unit 4 — Migration 0020
- `app/migrations/0020_advisor_embedding_dimension.sql`:
  - `ALTER TABLE user_memories DROP COLUMN embedding;`
  - `ALTER TABLE user_memories ADD COLUMN embedding vector(768);`
  - Drop/recreate any HNSW or IVFFlat index on the column.
  - `DROP FUNCTION IF EXISTS match_user_memories(...); CREATE FUNCTION match_user_memories(p_user_id UUID, p_embedding vector(768), p_limit INT) ...`
- Existing memories lose embeddings; next read recomputes via `MemoryManager`.

### Unit 5 — Tests + verification
- Add `tests/test_embedding_adapters.py`: mock returns correct length, openai/ollama call right URLs (httpx mock).
- Update `tests/test_deps.py` with `test_embedding_adapter_*` cases (mock + ollama + openai factory selection).
- Update mock dim references (1536 → settings.EMBEDDING_DIMENSIONS).
- Run `ruff check`, `mypy` (if configured), `pytest`.

## Risks

- **Embedding dim drift.** Other callers may hardcode 1536 — search proves only `mock.py:55` and the migration. Both rewritten.
- **Migration on a populated table.** Acceptable for dev; documented as breaking change in commit message.
- **Ollama not reachable.** Adapter raises clearly so users know to start Ollama.
