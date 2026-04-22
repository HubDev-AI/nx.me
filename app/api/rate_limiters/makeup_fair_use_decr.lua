-- makeup_fair_use_decr.lua
-- Idempotent decrement for non-retryable / refused makeup job terminals.
-- Called by the ARQ worker after a permanent failure so the user's daily
-- budget is restored.
--
-- KEYS[1] = "makeup:quota:{user_id}"             -- per-user rolling 24h counter
-- ARGV[1] = namespaced_key                        -- jobs.idempotency_key (already namespaced)
-- ARGV[2] = user_id                               -- for txn marker key scoping
--
-- Idempotent: if the txn marker is absent (already decremented or never set),
-- this is a no-op — the counter is NOT driven negative.
--
-- Returns: 1 if a decrement happened, 0 if already idempotent no-op.

local counter_key = KEYS[1]
local namespaced_key = ARGV[1]
local user_id = ARGV[2]

local txn_key = "makeup:quota:txn:" .. user_id .. ":" .. namespaced_key

local marker = redis.call("GET", txn_key)
if not marker then
    -- Already decremented or marker expired — no-op.
    return 0
end

-- Remove the marker first, then decrement (decrement is non-fatal if counter
-- expired between the GET and here).
redis.call("DEL", txn_key)
local current = tonumber(redis.call("GET", counter_key) or "0")
if current and current > 0 then
    redis.call("DECR", counter_key)
end
return 1
