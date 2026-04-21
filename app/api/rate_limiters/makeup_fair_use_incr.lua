-- makeup_fair_use_incr.lua
-- Atomic fair-use cap check + increment for a single makeup /generate submission.
--
-- KEYS[1] = "makeup:quota:{user_id}"             -- per-user rolling 24h counter
-- ARGV[1] = namespaced_key                        -- f"makeup:{client_key}"
-- ARGV[2] = daily_cap                             -- MAKEUP_FAIR_USE_DAILY_CAP
-- ARGV[3] = txn_ttl                               -- 86400 (seconds)
-- ARGV[4] = user_id                               -- for txn marker key scoping
--
-- Returns:
--   {new_count, 0}  when charge is accepted (new_count <= cap)
--   {-1, 0}         when cap exceeded (counter rolled back; no txn marker written)

local counter_key = KEYS[1]
local namespaced_key = ARGV[1]
local cap = tonumber(ARGV[2])
local txn_ttl = tonumber(ARGV[3])
local user_id = ARGV[4]

local txn_key = "makeup:quota:txn:" .. user_id .. ":" .. namespaced_key

-- Idempotency: if the txn marker already exists this submission was already
-- charged. Return the stored counter value so the route treats it as a replay.
local existing = redis.call("GET", txn_key)
if existing then
    local current = tonumber(redis.call("GET", counter_key) or "0")
    return {current, 1}
end

-- INCR the counter and anchor the TTL on first attempt (NX flag).
local new_count = redis.call("INCR", counter_key)
redis.call("EXPIRE", counter_key, 86400, "NX")

if new_count > cap then
    -- Over cap — roll back and signal rejection.
    redis.call("DECR", counter_key)
    return {-1, 0}
end

-- Within cap — write the txn marker so the worker can decrement idempotently.
redis.call("SET", txn_key, "charged", "EX", txn_ttl)
return {new_count, 0}
