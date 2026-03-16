---
alwaysApply: false
globs: ["*.sql", "**/migrations/**"]
---
Database patterns and SQL conventions — loaded when working with .sql files, migrations, or database-related code.

# Database Patterns

## Composite Index Ordering (ESR Rule)

Follow the **ESR rule** — Equality → Sort → Range:

```sql
-- Query: WHERE tenant_id = ? AND status = 'active' ORDER BY created_at WHERE amount > 100
-- Index should be:
CREATE INDEX idx_orders_tenant_status_created_amount
  ON orders (tenant_id, status, created_at, amount);
--           ^^^^^^^^^ ^^^^^^  ^^^^^^^^^^   ^^^^^^
--           Equality  Equality   Sort       Range
```

- Leftmost columns are used first — order matters
- Equality predicates first (highest selectivity)
- Range predicates last (they stop the index scan)

## Schema Conventions

- Singular `snake_case` table names, always use `TIMESTAMPTZ` (not `TIMESTAMP`), soft deletes via `deleted_at` column, audit columns (`created_at`, `updated_at`) on every table

## Row-Level Security (RLS)

**Always enable RLS for multi-tenant tables.** No exceptions.

```sql
-- Enable RLS on the table
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- Force RLS even for table owner
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

-- Policy: users can only see their tenant's data
CREATE POLICY tenant_isolation ON orders
  USING (tenant_id = current_setting('app.tenant_id')::uuid);

-- Set tenant context at connection/transaction level
SET app.tenant_id = 'uuid-of-tenant';
```

**Rules:**
- Every multi-tenant table gets an RLS policy
- Set tenant context at the middleware/connection pool level
- Test that cross-tenant access is impossible (write a test for this!)
- Service accounts that need cross-tenant access use a separate role

## Migration Patterns

### Naming Convention

```
YYYYMMDDHHMMSS_descriptive_name.sql
```

### Rules

- **Forward-only** — never modify a published (merged/deployed) migration
- **Always include down/rollback** — every `up` migration has a corresponding `down`
- **Schema and data migrations are separate files** — don't mix `ALTER TABLE` with `UPDATE` rows
- **Test the cycle** — verify: up → seed → down → up produces a clean state
- **Idempotent when possible** — use `IF NOT EXISTS`, `IF EXISTS` guards

### Dangerous Operations

These require extra caution and possibly a multi-step migration:
- **Dropping columns** — deploy code that doesn't read the column first, then drop
- **Renaming columns** — use a multi-step: add new → backfill → update code → drop old
- **Changing column types** — may lock the table; use `ALTER ... USING` carefully
- **Adding NOT NULL to existing column** — backfill NULLs first, then add constraint
