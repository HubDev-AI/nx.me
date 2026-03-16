---
status: complete
created: 2026-03-16
last_updated: 2026-03-16
---

# NXME Advisor Specification — Ada

Single source of truth for the advisor system. Stories 7-1 through 7-4 read this document.

---

## 1. Overview

Ada is a personal style advisor powered by Claude. She knows each user's face analysis results, remembers their goals, and checks in with styling tips.

Persona: `app/advisor/SOUL.md` — loaded as the system prompt.

---

## 2. Architecture

```
POST /v1/advisor/messages ─── require_feature("advisor_chat") ─── paid only
GET  /v1/advisor/messages
GET  /v1/advisor/nudges ──── all tiers
POST /v1/advisor/nudges/{id}/read
POST /v1/memories
GET  /v1/memories
DELETE /v1/memories/{id}
       │
       v
AdvisorService
├── MemoryManager ─── pgvector read/write
├── ContextBuilder ── SOUL.md + face data + memories + conversation
├── LLMAdapter ────── Claude API (port/adapter)
└── NudgeScheduler ── ARQ jobs
```

Self-contained module. Nothing outside `app/advisor/` imports from it. Enabled/disabled via `ADVISOR_ENABLED` config flag.

---

## 3. Access Control

| Feature | Free | Credits | Premium |
|---------|------|---------|---------|
| Receive nudges | Capped (3/week) | Capped (5/week) | Unlimited |
| Read nudges | Yes | Yes | Yes |
| Chat | No (402) | No (402) | Yes |
| Memories | Yes | Yes | Yes |

Enforcement: `require_feature("advisor_chat")` on chat endpoint, `EntitlementService.check("advisor_nudge")` in worker.

---

## 4. Memory System

### 4.1 Types

| Type | Created by |
|------|-----------|
| `goal` | User (POST /memories) |
| `user_note` | User (POST /memories) |
| `accepted_suggestion` | System (memory extraction) |
| `dismissed_suggestion` | System (memory extraction) |
| `analysis_insight` | System (after face analysis) |

### 4.2 Schema

```sql
CREATE TABLE user_memories (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       TEXT NOT NULL CHECK (type IN (
                 'goal', 'dismissed_suggestion', 'accepted_suggestion',
                 'user_note', 'analysis_insight')),
    content    JSONB NOT NULL,
    embedding  vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_user_memories_user_id ON user_memories(user_id);
CREATE INDEX idx_user_memories_embedding ON user_memories USING ivfflat (embedding vector_cosine_ops);
```

### 4.3 Embeddings

`text-embedding-3-small` (1536d, ~$0.00002/1K tokens). Computed from raw content text.

### 4.4 Retrieval

Fetches 15 candidates via pgvector cosine similarity, re-ranks with hybrid score, returns top 3.

```
memory_score = 0.6 * semantic_similarity + 0.3 * recency + 0.1 * importance
```

Recency: <1d → 1.0, <7d → 0.8, <30d → 0.5, older → 0.2

Importance: goal 1.0, accepted 0.9, analysis 0.8, note 0.6, dismissed 0.4

```python
async def get_relevant_memories(user_id, query, limit=3):
    embedding = await compute_embedding(query)
    candidates = supabase.rpc("match_user_memories", {
        "p_user_id": str(user_id), "p_embedding": embedding, "p_limit": 15,
    }).execute()

    scored = []
    for row in candidates.data or []:
        if row["similarity"] < 0.60:
            continue
        score = (0.6 * row["similarity"]
                 + 0.3 * recency_score(row["created_at"])
                 + 0.1 * IMPORTANCE.get(row["type"], 0.5))
        scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate
    seen, results = set(), []
    for _, row in scored:
        key = str(row["content"])[:80]
        if key not in seen:
            seen.add(key)
            results.append(row)
        if len(results) >= limit:
            break

    return results
```

RPC:
```sql
CREATE FUNCTION match_user_memories(p_user_id UUID, p_embedding vector(1536), p_limit INT)
RETURNS TABLE (id UUID, type TEXT, content JSONB, similarity FLOAT, created_at TIMESTAMPTZ)
AS $$
    SELECT id, type, content, 1 - (embedding <=> p_embedding), created_at
    FROM user_memories WHERE user_id = p_user_id
    ORDER BY embedding <=> p_embedding LIMIT p_limit;
$$ LANGUAGE sql STABLE;
```

### 4.5 Analysis snapshots

Written after each face analysis via the advisor event hook:

```python
async def write_analysis_insight(user_id, result, image_id):
    content = {
        "face_shape": result.face_shape.value,
        "symmetry_score": result.symmetry_score,
        "recommendations": [s.suggestion_text for s in result.recommendations],
    }
    embedding = await compute_embedding(
        f"{content['face_shape']} face, symmetry {content['symmetry_score']}, "
        + ", ".join(content["recommendations"])
    )
    supabase.table("user_memories").insert({
        "user_id": str(user_id), "type": "analysis_insight",
        "content": content, "embedding": embedding,
    }).execute()
```

---

## 5. Conversations

### 5.1 Schema

```sql
CREATE TABLE advisor_conversations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    summarised_at TIMESTAMPTZ,
    summary       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE advisor_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES advisor_conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'advisor')),
    content         TEXT NOT NULL,
    token_count     INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 5.2 Lifecycle

One active conversation per user. Auto-summarize after 30 messages (Haiku). Auto-new after 7 days inactive.

### 5.3 Message flow

```
[1] require_feature("advisor_chat")
[2] Get/create active conversation
[3] Build context (Section 6)
[4] Call Claude Sonnet
[5] Save messages
[6] Extract memory signals (async, Haiku)
[7] Return response
```

### 5.4 Memory extraction

After each turn, Haiku extracts signals (goals, accepted/dismissed suggestions, notes). Validated before storage:

- Goals: must contain future intent, >5 words
- Accepted: must contain confirmation marker ("tried", "did", "got")
- Deduplicated: >70% word overlap with same-type memory in last 7 days → skip

---

## 6. Context Assembly

### 6.1 What the LLM receives

```
[system] {SOUL.md}
[system] oval face, symmetry 0.87, 4 analyses
[system] new hairstyle
        curtain bangs
        not into beard
[conversation messages]
[current user message]
```

No prefixes. No labels. No structure.

```python
def build_context(soul_md, user_data, memories, conversation, message):
    messages = [
        {"role": "system", "content": soul_md},
        {"role": "system", "content": user_data},
    ]
    if memories:
        messages.append({"role": "system", "content": "\n".join(format_memory(m) for m in memories)})
    messages.extend(conversation)
    messages.append({"role": "user", "content": message})
    return messages
```

### 6.2 Memory formatting

```python
def format_memory(memory):
    return summarize_memory_content(memory.content)
```

Raw fragments only. No verbs added, no time references, no interpretation.

### 6.3 Trajectory

If 2+ accepted suggestions in the same area, 15% chance of adding a soft hint to the memory list:

```python
def maybe_add_trajectory(memories):
    accepted = [m for m in memories if m["type"] == "accepted_suggestion"]
    if len(accepted) < 2 or random.random() > 0.15:
        return memories
    # ... detect area, append hint like "going cleaner with hair"
    return memories
```

Typed as `user_note`. No analytical language.

### 6.4 Visual context

When user message contains "look at", "see my", "compare", "photo": fetch signed image URLs from Supabase Storage, pass as Claude vision content blocks.

### 6.5 Edge cases

- No memories → first-time user, no past references
- No analysis → suggest doing one, don't guess face shape
- Low symmetry (<0.50) → suggest clearer photo

---

## 7. Nudges

Ada-initiated messages. All tiers receive (capped). In-app feed, not push notifications.

### 7.1 Triggers

| Trigger | When |
|---------|------|
| Post-analysis | After face analysis completes |
| Weekly check-in | 7 days since last nudge, if goals exist |
| Progress milestone | 5th/10th analysis |
| Re-engagement | 14 days inactive |

### 7.2 Storage

```sql
CREATE TABLE advisor_nudges (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trigger    TEXT NOT NULL,
    content    TEXT NOT NULL,
    read_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 7.3 Generation

Haiku generates nudges. Entitlement checked before generation. ARQ job per nudge. Daily cron job checks eligibility.

---

## 8. LLM Adapter

```python
class LLMPort(Protocol):
    async def create_message(self, model, system, messages, max_tokens,
                             vision_content=None) -> LLMResponse: ...

class AnthropicAdapter:  # Real
class MockLLMAdapter:    # Testing
```

Config: `ADAPTER__LLM_ADAPTER` (`"mock"` or `"anthropic"`).

---

## 9. Safety

**Input:** Strip prompt injection patterns. Max 2000 chars. Rate limit: 30 messages/hour/user.

**Output:** Scan for C-2 violations (forbidden terms). One retry if detected, then generic fallback.

**Boundaries:** SOUL.md defines scope. Medical → dermatologist. Therapy → counselor. Comparisons → redirect to user's features.

---

## 10. Cost

| Action | Model | Cost |
|--------|-------|------|
| Chat message | Sonnet | ~$0.020 |
| Memory extraction | Haiku | ~$0.0001 |
| Embedding | text-embedding-3-small | ~$0.00002 |
| Nudge | Haiku | ~$0.001 |

Premium user (10 messages/day): ~$6/month. Free user: ~$0.01/month (nudges only).

**Guards:** >50 messages/day → degrade to Haiku. Context capped at 5000 tokens. Memory capped at 500 per user.

---

## 11. Post-Generation

```python
def post_check(response, recent_messages):
    if recent_messages:
        last = " ".join(recent_messages[-1].split()[:3]).lower()
        this = " ".join(response.split()[:3]).lower()
        if last == this:
            return "Start differently."

    sentences = response.count(". ") + response.count("? ") + response.count("! ") + 1
    if sentences > 3:
        return "Shorter. Say less."
    if sentences == 3:
        return "If you can say this in fewer words, do it."

    return None
```

Regenerate once. Still imperfect? Ship it.

---

## 12. Files

```
app/advisor/
    SOUL.md, service.py, context_builder.py,
    memory_manager.py, llm_adapter.py,
    nudge_scheduler.py, models.py, content_filter.py
```

---

## 13. Config

```python
ADVISOR_ENABLED: bool = True
ADVISOR_PERSONA_NAME: str = "Ada"
ADVISOR_CONTEXT_MEMORY_LIMIT: int = 3
ADVISOR_MAX_MESSAGE_LENGTH: int = 2000
ADVISOR_CHAT_RATE_LIMIT: int = 30
ADVISOR_CONVERSATION_SUMMARY_THRESHOLD: int = 30
ADVISOR_CONVERSATION_INACTIVE_DAYS: int = 7
ADAPTER__LLM_ADAPTER: str = "mock"
ANTHROPIC_API_KEY: str = ""
```

---

## 14. API Endpoints

| Endpoint | Auth | Gate | Description |
|----------|------|------|-------------|
| POST /v1/advisor/messages | JWT | `require_feature("advisor_chat")` | Send message (premium) |
| GET /v1/advisor/messages | JWT | None | Conversation history |
| GET /v1/advisor/nudges | JWT | None | Nudge feed |
| POST /v1/advisor/nudges/{id}/read | JWT | None | Mark read |
| POST /v1/memories | JWT | None | Add goal/note |
| GET /v1/memories | JWT | None | List memories |
| DELETE /v1/memories/{id} | JWT | None | Delete memory |

---

## 15. Stories

| Story | Wave | Size | Scope |
|-------|------|------|-------|
| 7-1 | 1 | S | Migration: tables + pgvector + RPC |
| 7-2 | 8 | M | AdvisorService, all endpoints, memory extraction |
| 7-3 | 9 | S | Nudge scheduler, triggers, ARQ jobs |
| 7-4 | 11 | M | Mobile UI |

---

## 16. Pluggable Design

- Nothing outside `app/advisor/` imports from it
- One integration point: `on_analysis_complete` event hook (guarded by `ADVISOR_ENABLED`)
- Disable: set `ADVISOR_ENABLED = False` → no routes, no jobs, no imports
- Remove: delete `app/advisor/`, remove hook, drop tables

---

## 17. Open Questions

1. **Embedding model:** OpenAI (better quality, vendor dependency) vs local sentence-transformers (free, lower quality)
2. **Nudge delivery:** In-app feed only (current) vs push notifications (Story 2-4 scope)
3. **Memory cap:** 500 per user — acceptable?
4. **Visual context triggers:** Keyword matching vs Haiku classifier for MVP
