-- Dead-letter queue for storage blobs whose DB row failed to insert AND whose
-- inline cleanup delete also failed. A nightly reclaim worker drains it.
CREATE TABLE IF NOT EXISTS orphaned_storage_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bucket TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    CONSTRAINT orphaned_storage_keys_unique UNIQUE (bucket, storage_key)
);

-- Reclaim worker picks up rows that still have budget.
CREATE INDEX IF NOT EXISTS orphaned_storage_keys_attempts_idx
    ON orphaned_storage_keys (attempts, inserted_at);

-- DOWN:
DROP INDEX IF EXISTS orphaned_storage_keys_attempts_idx;
DROP TABLE IF EXISTS orphaned_storage_keys;
