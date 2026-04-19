-- 0051_dispute_and_delete_extension.sql
--
-- Dispute state machine RPC — CAS (compare-and-swap) on
-- `users.dispute_last_event_at` to neutralise out-of-order
-- `charge.dispute.*` webhooks.
--
-- === Why a CAS state machine ===
--
-- Stripe sends `charge.dispute.created`, `.closed_won`, `.closed_lost`, and
-- `.funds_withdrawn` via at-least-once delivery. The webhook transport makes
-- NO ordering guarantees: a `closed_won` that Stripe generated at t=10 can
-- arrive BEFORE the `created` at t=5 that should precede it. If the handler
-- blindly applied each event, an out-of-order late-arriving `created` would
-- flip `users.locked_at` back to NOW() on a user whose dispute Stripe
-- already resolved in their favour — a permanent, unrecoverable lock.
--
-- Security review flagged this as CRITICAL. The fix: every write is a CAS
-- against `(dispute_last_event_id, dispute_last_event_at)`:
--
--   * same `p_event_id`   → idempotent no-op (Stripe retry of the same evt)
--   * older `p_event_at`  → reject with `out_of_order`; caller (webhook)
--                           returns HTTP 5xx so Stripe retries. CAS on the
--                           timestamp guarantees the final state matches
--                           the LATEST event Stripe ever delivered.
--   * newer `p_event_at`  → apply the transition, advance the CAS tuple
--
-- The CAS columns were added by migration 0048 (Unit 1).
--
-- === Transitions ===
--
--   created          → users.locked_at = now() (only if currently NULL,
--                      so `closed_lost` then a late `created` doesn't
--                      stomp the lost-dominates-wins lock_at timestamp)
--   closed_won       → users.locked_at = NULL
--   closed_lost      → leave users.locked_at as-is (set by the earlier
--                      `created` in-order; caller must also write a
--                      compensating ledger entry via
--                      `credit_dispute_compensate_v2` — Unit 3)
--   funds_withdrawn  → audit-only (advance CAS tuple; no lock change)
--
-- === Advisory lock ===
--
-- Per-user advisory lock via `hashtextextended(p_user_id::text, 0)` — the
-- 64-bit domain adopted by the `_v2` credit RPCs (migration 0049). Keeps
-- concurrent dispute events on the same user serialised without blocking
-- other users. `hashtextextended` is PG14+ and already required by 0049.
--
-- === SECURITY DEFINER ===
--
-- `SECURITY DEFINER SET search_path = public` hardens against search_path
-- hijacking (per migration 0021's pattern) and lets the webhook handler
-- call this RPC via the service role while bypassing RLS on `users`.
--
-- Migration runner (`app/migrations/run.py`) wraps this file in its own
-- transaction; no explicit BEGIN/COMMIT needed.

-- UP

CREATE OR REPLACE FUNCTION public.apply_dispute_event(
  p_user_id    UUID,
  p_event_id   TEXT,
  p_event_at   TIMESTAMPTZ,
  p_new_status TEXT
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_current_event_id TEXT;
  v_current_event_at TIMESTAMPTZ;
  v_locked_at        TIMESTAMPTZ;
BEGIN
  -- Validate status enum up-front; fail fast on invalid input.
  IF p_new_status NOT IN ('created', 'closed_won', 'closed_lost', 'funds_withdrawn') THEN
    RAISE EXCEPTION 'invalid_dispute_status: %', p_new_status
      USING ERRCODE = 'P0001';
  END IF;

  -- Serialise concurrent dispute events for this user. 64-bit domain
  -- matches the `_v2` credit RPCs (0049), so a reserve in flight and a
  -- dispute event contend on the same lock — required for the
  -- `credit_commit_v2` → release conversion path (R4) to see a
  -- consistent `users.locked_at`.
  PERFORM pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

  -- Snapshot the current CAS tuple + locked_at.
  SELECT dispute_last_event_id, dispute_last_event_at, locked_at
    INTO v_current_event_id, v_current_event_at, v_locked_at
    FROM users
   WHERE id = p_user_id;

  -- Idempotent replay: Stripe redelivered the same event. No state change;
  -- return the same shape so the caller can treat it as success.
  IF v_current_event_id IS NOT NULL AND v_current_event_id = p_event_id THEN
    RETURN jsonb_build_object(
      'applied',    false,
      'reason',     'duplicate',
      'new_status', p_new_status,
      'locked_at',  to_jsonb(v_locked_at)
    );
  END IF;

  -- Out-of-order arrival: the persisted event is strictly newer than the
  -- incoming one. Reject so the webhook handler returns HTTP 5xx and lets
  -- Stripe retry delivery. CAS on the timestamp guarantees terminal
  -- consistency: whichever event Stripe successfully delivers with the
  -- newest `p_event_at` wins. Using strict `>` (not `>=`) so that tied
  -- timestamps with DIFFERENT event_ids are accepted as last-write-wins.
  -- The duplicate-event_id branch above already catches Stripe retries of
  -- the same event, so this branch only fires when the id differs. Tied
  -- timestamps on distinct events are real (Stripe can emit `created` +
  -- `closed_won` at the same millisecond in rare cases); accepting both
  -- is safe because closed transitions are idempotent semantically.
  IF v_current_event_at IS NOT NULL AND v_current_event_at > p_event_at THEN
    RETURN jsonb_build_object(
      'applied',    false,
      'reason',     'out_of_order',
      'new_status', p_new_status,
      'locked_at',  to_jsonb(v_locked_at)
    );
  END IF;

  -- Apply the transition. Note: we update locked_at separately from the
  -- CAS tuple so a `closed_lost` that arrives after the `created` in-order
  -- doesn't need to re-touch locked_at (keep the original lock timestamp
  -- for auditability).
  CASE p_new_status
    WHEN 'created' THEN
      -- Lock only if not already locked so a rewound-clock `created`
      -- arriving AFTER `closed_lost` (also locked) doesn't overwrite the
      -- earlier lock timestamp. The out-of-order guard above rejects the
      -- truly-out-of-order case; this belt-and-braces.
      UPDATE users
         SET locked_at = now()
       WHERE id = p_user_id
         AND locked_at IS NULL;

    WHEN 'closed_won' THEN
      UPDATE users
         SET locked_at = NULL
       WHERE id = p_user_id;

    WHEN 'closed_lost' THEN
      -- Lock stays whatever the in-order `created` set. If the caller
      -- applied `closed_lost` without a preceding `created` (e.g. Stripe
      -- skipped `created` in an unusual dispute path), set locked_at so
      -- the invariant "closed_lost => user locked" holds regardless.
      UPDATE users
         SET locked_at = COALESCE(locked_at, now())
       WHERE id = p_user_id;

    WHEN 'funds_withdrawn' THEN
      -- Audit-only. Do NOT touch locked_at — this event carries no
      -- semantic state change, only that Stripe pulled the funds back.
      NULL;
  END CASE;

  -- Advance the CAS tuple. Do this AFTER the state transition so a
  -- downstream failure (e.g. constraint violation) rolls back both.
  UPDATE users
     SET dispute_last_event_id = p_event_id,
         dispute_last_event_at = p_event_at,
         dispute_last_status   = p_new_status
   WHERE id = p_user_id;

  -- Re-read locked_at so the caller sees the effective value after the
  -- transition (esp. closed_won → NULL, created → now()).
  SELECT locked_at INTO v_locked_at
    FROM users
   WHERE id = p_user_id;

  RETURN jsonb_build_object(
    'applied',    true,
    'reason',     NULL,
    'new_status', p_new_status,
    'locked_at',  to_jsonb(v_locked_at)
  );
END;
$$;

-- DOWN:

DROP FUNCTION IF EXISTS public.apply_dispute_event(UUID, TEXT, TIMESTAMPTZ, TEXT);
